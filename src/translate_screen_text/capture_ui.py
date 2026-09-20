"""Hotkey global e seleção visual da região de captura."""

from __future__ import annotations

import ctypes
import logging
import signal
import sys
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread, current_thread, main_thread
from time import monotonic
from types import FrameType

from pynput import keyboard

from translate_screen_text.capture import CaptureResult, ScreenshotService
from translate_screen_text.contracts import (
    InputActivityMonitor,
    LoadingIndicator,
    OcrProvider,
    TranslationOverlay,
    TranslationProvider,
)
from translate_screen_text.control_settings import (
    CAPTURE_MODE_FULLSCREEN,
    CAPTURE_MODE_REGION,
    CAPTURE_MODES,
)
from translate_screen_text.models import (
    Frame,
    ScreenRegion,
    TextRegion,
    TranslatedRegion,
)

SelectionCallback = Callable[[ScreenRegion | None], None]
LOGGER = logging.getLogger(__name__)


def format_recognized_text(regions: tuple[TextRegion, ...]) -> str:
    """Formata as regiões reconhecidas para exibição inicial no terminal."""

    return "\n".join(region.text for region in regions)


class CaptureState(Enum):
    IDLE = auto()
    SELECTING = auto()
    CAPTURING = auto()
    STOPPED = auto()


class CaptureCommand(Enum):
    SELECT = auto()
    STOP = auto()
    CLEAR_OVERLAY = auto()
    UPDATE_HOTKEY = auto()
    UPDATE_TARGET_LANGUAGE = auto()


@dataclass(frozen=True, slots=True)
class QueuedCommand:
    command: CaptureCommand
    occurred_at: float
    source: str = ""
    value: str = ""


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    """Resultado produzido pela thread de OCR e traducao."""

    capture_result: CaptureResult
    recognized_regions: tuple[TextRegion, ...] = ()
    translated_regions: tuple[TranslatedRegion, ...] = ()
    error: Exception | None = None


def enable_dpi_awareness() -> None:
    """Mantém coordenadas do mouse e pixels alinhados no Windows."""

    if sys.platform != "win32":
        return

    try:
        per_monitor_aware_v2 = ctypes.c_void_p(-4)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(per_monitor_aware_v2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass


class TkRegionSelector:
    """Overlay simples para selecionar uma área do monitor principal."""

    MINIMUM_SIZE = 5

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._window: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._callback: SelectionCallback | None = None
        self._start_local: tuple[int, int] | None = None
        self._start_screen: tuple[int, int] | None = None
        self._rectangle_id: int | None = None

    @property
    def active(self) -> bool:
        return self._window is not None

    def show(self, callback: SelectionCallback) -> bool:
        if self.active:
            return False

        self._callback = callback
        width = self._root.winfo_screenwidth()
        height = self._root.winfo_screenheight()

        window = tk.Toplevel(self._root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.35)
        window.geometry(f"{width}x{height}+0+0")
        window.configure(cursor="crosshair")

        canvas = tk.Canvas(
            window,
            width=width,
            height=height,
            background="#101820",
            highlightthickness=0,
            cursor="crosshair",
        )
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_text(
            width // 2,
            36,
            text="Arraste para selecionar a área • Esc para cancelar",
            fill="white",
            font=("Segoe UI", 16, "bold"),
        )

        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        window.bind("<Escape>", self._on_cancel)
        window.protocol("WM_DELETE_WINDOW", self.cancel)

        self._window = window
        self._canvas = canvas
        window.lift()
        window.grab_set()
        window.after_idle(window.focus_force)
        return True

    def cancel(self) -> None:
        if self.active:
            self._finish(None)

    def _on_press(self, event: tk.Event) -> None:
        if self._canvas is None:
            return

        self._start_local = (event.x, event.y)
        self._start_screen = (event.x_root, event.y_root)
        if self._rectangle_id is not None:
            self._canvas.delete(self._rectangle_id)
        self._rectangle_id = self._canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#00e5ff",
            width=3,
        )

    def _on_drag(self, event: tk.Event) -> None:
        if (
            self._canvas is None
            or self._rectangle_id is None
            or self._start_local is None
        ):
            return

        start_x, start_y = self._start_local
        self._canvas.coords(
            self._rectangle_id,
            start_x,
            start_y,
            event.x,
            event.y,
        )

    def _on_release(self, event: tk.Event) -> None:
        if self._start_screen is None:
            return

        start_x, start_y = self._start_screen
        try:
            region = ScreenRegion.from_points(
                start_x,
                start_y,
                event.x_root,
                event.y_root,
            )
        except ValueError:
            self._finish(None)
            return

        if (
            region.width < self.MINIMUM_SIZE
            or region.height < self.MINIMUM_SIZE
        ):
            self._finish(None)
            return

        self._finish(region)

    def _on_cancel(self, _event: tk.Event) -> None:
        self.cancel()

    def _finish(self, region: ScreenRegion | None) -> None:
        callback = self._callback
        window = self._window

        self._window = None
        self._canvas = None
        self._callback = None
        self._start_local = None
        self._start_screen = None
        self._rectangle_id = None

        if window is not None:
            try:
                window.grab_release()
            except tk.TclError:
                pass
            window.withdraw()
            window.update_idletasks()
            window.destroy()

        if callback is not None:
            callback(region)


class CaptureHotkeyApplication:
    """Executa o seletor no thread principal e escuta hotkeys em segundo plano."""

    POLL_INTERVAL_MS = 40
    OVERLAY_DISMISS_DELAY_MS = 150
    QUIT_HOTKEY = "<ctrl>+<shift>+q"

    def __init__(
        self,
        screenshot_service: ScreenshotService,
        ocr_provider: OcrProvider,
        translation_provider: TranslationProvider | None = None,
        translation_overlay: TranslationOverlay | None = None,
        source_language: str = "en",
        target_language: str = "pt-BR",
        capture_hotkey: str = "<f6>",
        input_activity_monitor: InputActivityMonitor | None = None,
        loading_indicator: LoadingIndicator | None = None,
        stop_signal_file: Path | None = None,
        capture_mode: str = CAPTURE_MODE_REGION,
    ) -> None:
        if capture_mode not in CAPTURE_MODES:
            raise ValueError("Modo de captura inválido")
        self._screenshot_service = screenshot_service
        self._ocr_provider = ocr_provider
        self._translation_provider = translation_provider
        self._translation_overlay = translation_overlay
        self._source_language = source_language
        self._target_language = target_language
        self._capture_hotkey = capture_hotkey
        self._capture_mode = capture_mode
        self._commands: SimpleQueue[QueuedCommand] = SimpleQueue()
        self._processing_results: SimpleQueue[ProcessingResult] = SimpleQueue()
        self._state = CaptureState.IDLE
        self._root: tk.Tk | None = None
        self._selector: TkRegionSelector | None = None
        self._listener: keyboard.GlobalHotKeys | None = None
        self._input_activity_monitor = input_activity_monitor
        self._loading_indicator = loading_indicator
        self._processing_thread: Thread | None = None
        self._stop_signal_file = stop_signal_file
        self._overlay_shown_at: float | None = None
        self._overlay_clear_pending = Event()
        self._previous_sigint_handler: signal.Handlers | None = None

    def run(self) -> int:
        enable_dpi_awareness()
        root = tk.Tk()
        root.withdraw()
        self._root = root
        self._selector = TkRegionSelector(root)
        if self._translation_overlay is None:
            from translate_screen_text.adapters.tk_translation_overlay import (
                TkTranslationOverlay,
            )

            self._translation_overlay = TkTranslationOverlay(root)
        if self._loading_indicator is None:
            from translate_screen_text.adapters.tk_loading_indicator import (
                TkLoadingIndicator,
            )

            self._loading_indicator = TkLoadingIndicator(root)
        if self._input_activity_monitor is None:
            from translate_screen_text.adapters.input_activity import (
                GlobalInputActivityMonitor,
            )

            self._input_activity_monitor = GlobalInputActivityMonitor(
                self._enqueue_input_activity
            )

        self._start_hotkey_listener()
        self._input_activity_monitor.start()
        if current_thread() is main_thread():
            self._install_sigint_handler()
        root.after(self.POLL_INTERVAL_MS, self._poll_commands)

        capture_action = (
            "capturar a tela inteira"
            if self._capture_mode == CAPTURE_MODE_FULLSCREEN
            else "selecionar uma área"
        )
        LOGGER.info(
            "Captura ativa: pressione %s para %s.",
            self._capture_hotkey,
            capture_action,
        )
        LOGGER.info(
            "Para encerrar, pressione %s ou Ctrl+C.",
            self.QUIT_HOTKEY,
        )

        try:
            root.mainloop()
        finally:
            self._shutdown()
        return 0

    def _enqueue_selection(self) -> None:
        self._commands.put(
            QueuedCommand(CaptureCommand.SELECT, occurred_at=monotonic())
        )

    def _enqueue_stop(self) -> None:
        self._commands.put(
            QueuedCommand(CaptureCommand.STOP, occurred_at=monotonic())
        )

    def request_stop(self) -> None:
        """Solicita encerramento seguro a partir de outra interface ou thread."""

        self._enqueue_stop()

    def configure(
        self,
        capture_hotkey: str,
        target_language: str,
        capture_mode: str = CAPTURE_MODE_REGION,
    ) -> None:
        """Define valores iniciais antes de iniciar os listeners globais."""

        if self._listener is not None:
            raise RuntimeError("A aplicação já foi iniciada")
        if capture_mode not in CAPTURE_MODES:
            raise ValueError("Modo de captura inválido")
        self._capture_hotkey = capture_hotkey
        self._target_language = target_language
        self._capture_mode = capture_mode

    def update_capture_hotkey(self, capture_hotkey: str) -> None:
        self._commands.put(
            QueuedCommand(
                CaptureCommand.UPDATE_HOTKEY,
                occurred_at=monotonic(),
                value=capture_hotkey,
            )
        )

    def update_target_language(self, target_language: str) -> None:
        self._commands.put(
            QueuedCommand(
                CaptureCommand.UPDATE_TARGET_LANGUAGE,
                occurred_at=monotonic(),
                value=target_language,
            )
        )

    def _enqueue_input_activity(self, source: str) -> None:
        shown_at = self._overlay_shown_at
        if shown_at is None or self._overlay_clear_pending.is_set():
            return

        occurred_at = monotonic()
        if occurred_at <= shown_at:
            return
        self._overlay_clear_pending.set()
        self._commands.put(
            QueuedCommand(
                CaptureCommand.CLEAR_OVERLAY,
                occurred_at=occurred_at,
                source=source,
            )
        )

    def _poll_commands(self) -> None:
        if self._root is None or self._state is CaptureState.STOPPED:
            return

        if self._stop_was_requested_by_controller():
            LOGGER.info("Encerramento solicitado pela interface de controle.")
            self._state = CaptureState.STOPPED
            self._root.quit()
            return

        try:
            while True:
                queued_command = self._commands.get_nowait()
                if queued_command.command is CaptureCommand.SELECT:
                    self._begin_selection()
                elif queued_command.command is CaptureCommand.STOP:
                    LOGGER.info("Encerramento solicitado pelo usuário.")
                    self._state = CaptureState.STOPPED
                    self._root.quit()
                    return
                elif queued_command.command is CaptureCommand.CLEAR_OVERLAY:
                    self._clear_overlay_after_activity(queued_command)
                elif queued_command.command is CaptureCommand.UPDATE_HOTKEY:
                    self._replace_capture_hotkey(queued_command.value)
                elif queued_command.command is CaptureCommand.UPDATE_TARGET_LANGUAGE:
                    self._target_language = queued_command.value
                    LOGGER.info(
                        "Idioma de destino alterado para %s.",
                        self._target_language,
                    )
        except Empty:
            pass

        self._poll_processing_results()

        self._root.after(self.POLL_INTERVAL_MS, self._poll_commands)

    def _stop_was_requested_by_controller(self) -> bool:
        stop_signal_file = self._stop_signal_file
        if stop_signal_file is None or not stop_signal_file.exists():
            return False
        try:
            stop_signal_file.unlink(missing_ok=True)
        except OSError:
            LOGGER.debug("Não foi possível remover o sinal de encerramento")
        return True

    def _start_hotkey_listener(self) -> None:
        self._listener = keyboard.GlobalHotKeys(
            {
                self._capture_hotkey: self._enqueue_selection,
                self.QUIT_HOTKEY: self._enqueue_stop,
            }
        )
        self._listener.start()

    def _replace_capture_hotkey(self, capture_hotkey: str) -> None:
        if capture_hotkey == self._capture_hotkey:
            return

        listener = self._listener
        if listener is not None:
            listener.stop()
            listener.join(timeout=1)
            self._listener = None
        self._capture_hotkey = capture_hotkey
        self._start_hotkey_listener()
        LOGGER.info("Atalho de captura alterado para %s.", self._capture_hotkey)

    def _begin_selection(self) -> None:
        if self._state is not CaptureState.IDLE or self._root is None:
            LOGGER.debug(
                "Solicitação de captura ignorada no estado %s.",
                self._state.name,
            )
            return

        if self._translation_overlay is not None:
            self._translation_overlay.hide()
        if self._loading_indicator is not None:
            self._loading_indicator.hide()
        self._overlay_shown_at = None
        self._overlay_clear_pending.clear()

        if self._capture_mode == CAPTURE_MODE_FULLSCREEN:
            region = ScreenRegion(
                left=0,
                top=0,
                width=self._root.winfo_screenwidth(),
                height=self._root.winfo_screenheight(),
            )
            LOGGER.info("[ETAPA 1/5] Captura da tela inteira solicitada.")
            self._state = CaptureState.CAPTURING
            self._root.after(
                self.OVERLAY_DISMISS_DELAY_MS,
                lambda: self._capture_region(region),
            )
            return

        if self._selector is None:
            LOGGER.debug("Seletor de região indisponível.")
            return
        LOGGER.info("[ETAPA 1/5] Selecione a área da tela que será capturada.")
        self._state = CaptureState.SELECTING
        if not self._selector.show(self._selection_finished):
            self._state = CaptureState.IDLE

    def _selection_finished(self, region: ScreenRegion | None) -> None:
        if self._state is CaptureState.STOPPED:
            return

        if region is None:
            LOGGER.info("[ETAPA 1/5] Seleção cancelada; nenhuma captura realizada.")
            self._state = CaptureState.IDLE
            return

        self._state = CaptureState.CAPTURING
        if self._root is not None:
            self._root.after(
                self.OVERLAY_DISMISS_DELAY_MS,
                lambda: self._capture_region(region),
            )

    def _capture_region(self, region: ScreenRegion) -> None:
        try:
            LOGGER.info(
                "[ETAPA 1/5] Capturando região x=%d, y=%d, largura=%d, altura=%d.",
                region.left,
                region.top,
                region.width,
                region.height,
            )
            result = self._screenshot_service.capture(region)
            LOGGER.info("[ETAPA 1/5] Captura salva em: %s", result.file_path)

            if self._loading_indicator is not None:
                message = (
                    "Processando imagem..."
                    if self._translation_provider is None
                    else "Processando e traduzindo..."
                )
                self._loading_indicator.show(result.region, message)
                LOGGER.info(
                    "Indicador de carregamento exibido durante o processamento."
                )

            self._processing_thread = Thread(
                target=self._process_capture,
                args=(result,),
                name="capture-processing",
                daemon=True,
            )
            self._processing_thread.start()
        except Exception as error:
            LOGGER.error("Não foi possível processar a captura: %s", error)
            LOGGER.debug("Detalhes da falha de processamento", exc_info=True)
            if self._loading_indicator is not None:
                self._loading_indicator.hide()
            self._state = CaptureState.IDLE

    def _process_capture(self, result: CaptureResult) -> None:
        """Executa operações demoradas sem bloquear o loop visual do Tkinter."""

        try:
            LOGGER.info("[ETAPA 2/5] Iniciando reconhecimento de texto (OCR).")
            recognized_regions = tuple(self._ocr_provider.recognize(result.frame))
            recognized_text = format_recognized_text(recognized_regions)
            if not recognized_text:
                LOGGER.warning(
                    "[ETAPA 2/5] OCR concluído sem detectar texto; "
                    "a tradução não será executada."
                )
                processing_result = ProcessingResult(
                    capture_result=result,
                    recognized_regions=recognized_regions,
                )
            else:
                LOGGER.info(
                    "[ETAPA 2/5] OCR concluído: %d região(ões) de texto detectada(s).",
                    len(recognized_regions),
                )
                LOGGER.info("[ETAPA 2/5] Texto detectado:\n%s", recognized_text)
                translated_regions = self._translate_and_log(recognized_regions)
                processing_result = ProcessingResult(
                    capture_result=result,
                    recognized_regions=recognized_regions,
                    translated_regions=translated_regions,
                )
        except Exception as error:
            processing_result = ProcessingResult(
                capture_result=result,
                error=error,
            )

        self._processing_results.put(processing_result)

    def _poll_processing_results(self) -> None:
        try:
            while True:
                self._complete_processing(self._processing_results.get_nowait())
        except Empty:
            pass

    def _complete_processing(self, result: ProcessingResult) -> None:
        """Finaliza o fluxo visual no thread principal do Tkinter."""

        if self._loading_indicator is not None:
            self._loading_indicator.hide()
        self._processing_thread = None

        try:
            if self._state is CaptureState.STOPPED:
                return
            if result.error is not None:
                LOGGER.error(
                    "Não foi possível processar a captura: %s",
                    result.error,
                )
                LOGGER.debug(
                    "Detalhes da falha de processamento",
                    exc_info=(
                        type(result.error),
                        result.error,
                        result.error.__traceback__,
                    ),
                )
                return
            if not result.recognized_regions:
                return

            overlay_was_shown = self._show_translation_overlay(
                result.capture_result.frame,
                result.capture_result.region,
                result.translated_regions,
            )
            if overlay_was_shown:
                self._delete_processed_capture(result.capture_result)
        finally:
            if self._state is not CaptureState.STOPPED:
                self._state = CaptureState.IDLE

    def _translate_and_log(
        self,
        recognized_regions: tuple[TextRegion, ...],
    ) -> tuple[TranslatedRegion, ...]:
        if self._translation_provider is None:
            LOGGER.info(
                "[ETAPA 3/5] Tradução desabilitada; processamento finalizado no OCR."
            )
            return ()

        LOGGER.info(
            "[ETAPA 3/5] Traduzindo %d região(ões) de %s para %s.",
            len(recognized_regions),
            self._source_language,
            self._target_language,
        )
        translated_regions = tuple(
            TranslatedRegion(
                source=region,
                translated_text=self._translation_provider.translate(
                    region.text,
                    self._source_language,
                    self._target_language,
                ),
            )
            for region in recognized_regions
        )
        LOGGER.info(
            "[ETAPA 3/5] Tradução concluída (%s):\n%s",
            self._target_language,
            "\n".join(region.translated_text for region in translated_regions),
        )
        return translated_regions

    def _show_translation_overlay(
        self,
        frame: Frame,
        screen_region: ScreenRegion,
        translated_regions: tuple[TranslatedRegion, ...],
    ) -> bool:
        if not translated_regions or self._translation_overlay is None:
            return False

        LOGGER.info(
            "[ETAPA 4/5] Aplicando blur e exibindo %d tradução(ões) sobre a tela.",
            len(translated_regions),
        )
        self._translation_overlay.show(
            frame,
            screen_region,
            translated_regions,
        )
        self._overlay_shown_at = monotonic()
        self._overlay_clear_pending.clear()
        LOGGER.info("[ETAPA 4/5] Overlay de tradução exibido.")
        return True

    def _delete_processed_capture(self, result: CaptureResult) -> None:
        LOGGER.info(
            "[ETAPA 5/5] Excluindo captura temporária: %s",
            result.file_path,
        )
        try:
            self._screenshot_service.delete_capture(result)
        except Exception as error:
            LOGGER.warning(
                "[ETAPA 5/5] Não foi possível excluir a captura temporária: %s",
                error,
            )
            LOGGER.debug("Detalhes da falha de exclusão", exc_info=True)
            return
        LOGGER.info("[ETAPA 5/5] Captura temporária excluída.")

    def _clear_overlay_after_activity(self, queued_command: QueuedCommand) -> None:
        self._overlay_clear_pending.clear()
        shown_at = self._overlay_shown_at
        if shown_at is None or queued_command.occurred_at <= shown_at:
            return
        if self._translation_overlay is not None:
            self._translation_overlay.hide()
        self._overlay_shown_at = None
        LOGGER.info(
            "Overlay removido após atividade de %s; tela restaurada.",
            queued_command.source,
        )

    def _install_sigint_handler(self) -> None:
        self._previous_sigint_handler = signal.getsignal(signal.SIGINT)

        def handle_sigint(_signum: int, _frame: FrameType | None) -> None:
            self._enqueue_stop()

        signal.signal(signal.SIGINT, handle_sigint)

    def _shutdown(self) -> None:
        LOGGER.info("Encerrando a aplicação de captura.")
        self._state = CaptureState.STOPPED
        if self._translation_overlay is not None:
            self._translation_overlay.hide()
        if self._loading_indicator is not None:
            self._loading_indicator.hide()
        self._overlay_shown_at = None
        self._overlay_clear_pending.clear()
        if self._selector is not None:
            self._selector.cancel()
        if self._listener is not None:
            listener = self._listener
            listener.stop()
            listener.join(timeout=1)
            self._listener = None
        if self._input_activity_monitor is not None:
            self._input_activity_monitor.stop()
        if self._previous_sigint_handler is not None:
            signal.signal(signal.SIGINT, self._previous_sigint_handler)
            self._previous_sigint_handler = None
        if self._root is not None:
            try:
                self._root.destroy()
            except tk.TclError:
                pass
            self._root = None
        self._selector = None
        if self._stop_signal_file is not None:
            try:
                self._stop_signal_file.unlink(missing_ok=True)
            except OSError:
                LOGGER.debug("Não foi possível limpar o sinal de encerramento")
