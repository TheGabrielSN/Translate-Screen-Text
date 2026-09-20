"""Interface HTML/CSS de controle renderizada pelo PySide6."""

from __future__ import annotations

import ctypes
import json
import logging
import re
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from threading import Thread

from PySide6.QtCore import (
    QEvent,
    QObject,
    QSettings,
    QTimer,
    QUrl,
    QUrlQuery,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
)

from translate_screen_text.capture_ui import CaptureHotkeyApplication
from translate_screen_text.control_settings import (
    CAPTURE_MODE_REGION,
    CAPTURE_MODES,
    MINIMIZE_BEHAVIORS,
    MINIMIZE_NORMAL,
    MINIMIZE_TO_TRAY,
    TARGET_LANGUAGES,
    TARGET_LANGUAGE_CODES,
    THEMES,
    THEME_DARK,
    ControlSettings,
    normalize_hotkey,
)

LOGGER = logging.getLogger(__name__)
UI_DIRECTORY = Path(__file__).with_name("ui")
APPLICATION_ICON_RELATIVE_PATH = Path("assets") / "icon.png"
WINDOWS_APP_USER_MODEL_ID = "ExceptionError.TranslateScreenText"
GITHUB_URL = QUrl("https://github.com/TheGabrielSN")
DEFAULT_TARGET_LANGUAGE = "pt-BR"
MISSING_ARGOS_MODEL_PATTERN = re.compile(
    r"O modelo Argos (?P<source>\S+) -> (?P<target>\S+) não está instalado\."
)


def missing_argos_language_pair(message: str) -> tuple[str, str] | None:
    match = MISSING_ARGOS_MODEL_PATTERN.search(message)
    if match is None:
        return None
    return match.group("source"), match.group("target")


def themed_ui_url(html_file: str, theme: str) -> QUrl:
    url = QUrl.fromLocalFile(str(UI_DIRECTORY / html_file))
    query = QUrlQuery()
    query.addQueryItem("theme", theme)
    url.setQuery(query)
    return url


def application_icon_path() -> Path | None:
    """Localiza o ícone no projeto, no pacote instalado ou no executável."""

    module_path = Path(__file__).resolve()
    candidates = [
        module_path.parent / APPLICATION_ICON_RELATIVE_PATH,
    ]
    frozen_directory = getattr(sys, "_MEIPASS", None)
    if frozen_directory is not None:
        candidates.append(
            Path(frozen_directory)
            / "translate_screen_text"
            / APPLICATION_ICON_RELATIVE_PATH
        )
    executable_directory = Path(sys.executable).resolve().parent
    candidates.extend(
        (
            executable_directory
            / "_internal"
            / "translate_screen_text"
            / APPLICATION_ICON_RELATIVE_PATH,
            executable_directory
            / "translate_screen_text"
            / APPLICATION_ICON_RELATIVE_PATH,
        )
    )

    return next((path for path in candidates if path.is_file()), None)


def load_application_icon() -> QIcon:
    icon_path = application_icon_path()
    return QIcon(str(icon_path)) if icon_path is not None else QIcon()


def application_command_prefix() -> list[str]:
    """Retorna como relançar a aplicação no Python ou no executável congelado."""

    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "translate_screen_text"]


def configure_windows_app_user_model_id() -> bool:
    """Evita que o Windows agrupe a aplicação com Python, Jupyter ou a IDE."""

    if sys.platform != "win32":
        return False

    try:
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            WINDOWS_APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        LOGGER.warning(
            "Não foi possível definir a identidade da aplicação no Windows.",
            exc_info=True,
        )
        return False

    if result != 0:
        LOGGER.warning(
            "O Windows recusou o AppUserModelID da aplicação (HRESULT=%s).",
            result,
        )
        return False
    return True


class ControlPreferences:
    """Persiste as preferências entre execuções por meio do QSettings."""

    def __init__(self, storage: QSettings | None = None) -> None:
        self._storage = (
            storage
            if storage is not None
            else QSettings("ExceptionError", "TranslateScreenText")
        )

    def load(
        self,
        default_hotkey: str,
        default_language: str,
        default_capture_mode: str = CAPTURE_MODE_REGION,
    ) -> ControlSettings:
        stored_hotkey = str(
            self._storage.value("capture_hotkey", default_hotkey)
        )
        stored_language = str(
            self._storage.value("target_language", default_language)
        )
        minimize_behavior = str(
            self._storage.value("minimize_behavior", MINIMIZE_NORMAL)
        )
        theme = str(self._storage.value("theme", THEME_DARK))
        capture_mode = str(
            self._storage.value("capture_mode", default_capture_mode)
        )

        try:
            stored_hotkey = normalize_hotkey(stored_hotkey)
        except ValueError:
            stored_hotkey = normalize_hotkey(default_hotkey)
        if stored_language not in TARGET_LANGUAGE_CODES:
            stored_language = (
                default_language
                if default_language in TARGET_LANGUAGE_CODES
                else "pt-BR"
            )
        if minimize_behavior not in MINIMIZE_BEHAVIORS:
            minimize_behavior = MINIMIZE_NORMAL
        if theme not in THEMES:
            theme = THEME_DARK
        if capture_mode not in CAPTURE_MODES:
            capture_mode = (
                default_capture_mode
                if default_capture_mode in CAPTURE_MODES
                else CAPTURE_MODE_REGION
            )

        return ControlSettings(
            capture_hotkey=stored_hotkey,
            target_language=stored_language,
            minimize_behavior=minimize_behavior,
            theme=theme,
            capture_mode=capture_mode,
        )

    def save(self, settings: ControlSettings) -> None:
        self._storage.setValue("capture_hotkey", settings.capture_hotkey)
        self._storage.setValue("target_language", settings.target_language)
        self._storage.setValue("minimize_behavior", settings.minimize_behavior)
        self._storage.setValue("theme", settings.theme)
        self._storage.setValue("capture_mode", settings.capture_mode)
        self._storage.sync()


class CaptureRuntime(QObject):
    """Gerencia o processo isolado que executa captura, OCR e tradução."""

    stopped = Signal()
    failed = Signal(str)

    POLL_INTERVAL_MS = 250

    def __init__(
        self,
        worker_arguments: Sequence[str],
        capture_hotkey: str,
        target_language: str,
        capture_mode: str = CAPTURE_MODE_REGION,
    ) -> None:
        super().__init__()
        self._worker_arguments = tuple(worker_arguments)
        self._capture_hotkey = capture_hotkey
        self._target_language = target_language
        self._capture_mode = capture_mode
        self._process: subprocess.Popen[bytes] | None = None
        self._stop_signal_file: Path | None = None
        self._error_signal_file: Path | None = None
        self._install_argos_model_once = False
        self._expected_stop = False
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self.POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_process)

    @property
    def uses_argos(self) -> bool:
        return self._worker_argument_value("--translator") == "argos"

    @property
    def source_language(self) -> str:
        return self._worker_argument_value("--source-language") or "en"

    def _worker_argument_value(self, option: str) -> str | None:
        try:
            index = self._worker_arguments.index(option)
            return self._worker_arguments[index + 1]
        except (ValueError, IndexError):
            return None

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return

        self._expected_stop = False
        self._stop_signal_file = (
            Path(tempfile.gettempdir())
            / f"translate-screen-text-{uuid.uuid4().hex}.stop"
        )
        self._error_signal_file = self._stop_signal_file.with_suffix(".error")
        command = [
            *application_command_prefix(),
            *self._worker_arguments,
            "--hotkey",
            self._capture_hotkey,
            "--target-language",
            self._target_language,
            "--capture-mode",
            self._capture_mode,
            "--stop-signal-file",
            str(self._stop_signal_file),
            "--error-signal-file",
            str(self._error_signal_file),
        ]
        if (
            self._install_argos_model_once
            and "--argos-install-model" not in command
        ):
            command.append("--argos-install-model")
        self._install_argos_model_once = False
        LOGGER.info("Iniciando processo de captura em segundo plano.")
        try:
            self._process = subprocess.Popen(command)
        except OSError as error:
            self._process = None
            self._cleanup_signal_files()
            self.failed.emit(str(error))
            self.stopped.emit()
            return
        self._poll_timer.start()

    def stop(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            self._cleanup_signal_files()
            return

        self._expected_stop = True
        self._poll_timer.stop()
        if self._stop_signal_file is not None:
            self._stop_signal_file.touch(exist_ok=True)

    def wait(self, timeout_seconds: float = 3.0) -> None:
        process = self._process
        if process is None:
            return
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            LOGGER.warning(
                "O capturador não encerrou no prazo; finalizando o processo."
            )
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        finally:
            self._process = None
            self._cleanup_signal_files()

    def update_hotkey(self, hotkey: str) -> None:
        if hotkey == self._capture_hotkey:
            return
        self.stop()
        self.wait()
        self._capture_hotkey = hotkey
        self.start()

    def update_target_language(self, target_language: str) -> None:
        self.update_configuration(target_language, self._capture_mode)

    def update_capture_mode(self, capture_mode: str) -> None:
        self.update_configuration(self._target_language, capture_mode)

    def update_configuration(
        self,
        target_language: str,
        capture_mode: str,
    ) -> None:
        if (
            target_language == self._target_language
            and capture_mode == self._capture_mode
            and self._process is not None
            and self._process.poll() is None
        ):
            return
        self.stop()
        self.wait()
        self._target_language = target_language
        self._capture_mode = capture_mode
        self.start()

    def install_missing_argos_model(self) -> None:
        """Reinicia uma vez permitindo que o Argos baixe o modelo ausente."""

        self.stop()
        self.wait()
        self._install_argos_model_once = True
        self.start()

    @Slot()
    def _poll_process(self) -> None:
        process = self._process
        if process is None:
            self._poll_timer.stop()
            return
        return_code = process.poll()
        if return_code is None:
            return

        self._poll_timer.stop()
        self._process = None
        error_message = self._read_error_signal()
        self._cleanup_signal_files()
        if self._expected_stop:
            return
        if return_code != 0:
            self.failed.emit(
                error_message
                or f"O processo de captura foi encerrado com código {return_code}."
            )
        else:
            self.stopped.emit()

    def _read_error_signal(self) -> str:
        if self._error_signal_file is None:
            return ""
        try:
            return self._error_signal_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _cleanup_signal_files(self) -> None:
        for signal_file in (self._stop_signal_file, self._error_signal_file):
            if signal_file is None:
                continue
            try:
                signal_file.unlink(missing_ok=True)
            except OSError:
                LOGGER.debug("Não foi possível limpar o sinal temporário")
        self._stop_signal_file = None
        self._error_signal_file = None


class MainBridge(QObject):
    """Ponte entre o JavaScript da tela principal e o Python."""

    stateChanged = Signal(str, str, str, str)
    feedback = Signal(str, bool)

    def __init__(self, window: ControlWindow) -> None:
        super().__init__(window)
        self._window = window

    @Slot()
    def requestState(self) -> None:
        settings = self._window.settings
        self.stateChanged.emit(
            settings.capture_hotkey,
            settings.target_language,
            settings.minimize_behavior,
            settings.theme,
        )

    @Slot(str)
    def applyHotkey(self, raw_hotkey: str) -> None:
        try:
            normalized = normalize_hotkey(raw_hotkey)
            if normalized == CaptureHotkeyApplication.QUIT_HOTKEY:
                raise ValueError("Esse atalho está reservado para encerrar a aplicação")
            self._window.apply_hotkey(normalized)
        except ValueError as error:
            self.feedback.emit(str(error), True)
            return

        self.feedback.emit(f"Atalho alterado para {normalized}.", False)
        self.requestState()

    @Slot()
    def openInformation(self) -> None:
        self._window.open_information()

    @Slot()
    def openSettings(self) -> None:
        self._window.open_settings()

    @Slot()
    def openGithub(self) -> None:
        QDesktopServices.openUrl(GITHUB_URL)


class ArgosModelService(QObject):
    """Verifica ou instala modelos Argos sem bloquear a interface Qt."""

    finished = Signal(bool, str)

    def prepare(
        self,
        source_language: str,
        target_language: str,
        install_missing_model: bool,
    ) -> None:
        Thread(
            target=self._prepare,
            args=(
                source_language,
                target_language,
                install_missing_model,
            ),
            name="argos-model-preparation",
            daemon=True,
        ).start()

    def _prepare(
        self,
        source_language: str,
        target_language: str,
        install_missing_model: bool,
    ) -> None:
        from translate_screen_text.adapters.argos_translation import (
            ArgosTranslationProvider,
        )

        try:
            provider = ArgosTranslationProvider(
                install_missing_model=install_missing_model
            )
            provider.prepare_languages(source_language, target_language)
        except Exception as error:
            self.finished.emit(False, str(error))
            return
        self.finished.emit(True, "")


class SettingsBridge(QObject):
    """Ponte da tela modal de configurações."""

    stateReady = Signal(str, str, str, str, str)
    feedback = Signal(str, bool)
    busyChanged = Signal(bool)

    def __init__(
        self,
        dialog: SettingsDialog,
        window: ControlWindow,
        model_service: ArgosModelService | None = None,
    ) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._window = window
        self._model_service = (
            model_service
            if model_service is not None
            else ArgosModelService(window)
        )
        self._model_service.finished.connect(self._model_prepared)
        self._pending_settings: tuple[str, str, str, str] | None = None
        self._installing_model = False
        self._busy = False

    @Slot()
    def requestState(self) -> None:
        settings = self._window.settings
        languages = [
            {"label": label, "code": code}
            for label, code in TARGET_LANGUAGES
        ]
        self.stateReady.emit(
            settings.minimize_behavior,
            settings.target_language,
            json.dumps(languages, ensure_ascii=False),
            settings.theme,
            settings.capture_mode,
        )

    @Slot(str, str, str, str)
    def saveSettings(
        self,
        minimize_behavior: str,
        target_language: str,
        theme: str,
        capture_mode: str,
    ) -> None:
        if self._busy:
            return
        try:
            ControlSettings(
                capture_hotkey=self._window.settings.capture_hotkey,
                target_language=target_language,
                minimize_behavior=minimize_behavior,
                theme=theme,
                capture_mode=capture_mode,
            )
        except ValueError as error:
            self.feedback.emit(str(error), True)
            return

        self._pending_settings = (
            minimize_behavior,
            target_language,
            theme,
            capture_mode,
        )
        language_changed = target_language != self._window.settings.target_language
        if self._window.runtime.uses_argos and language_changed:
            self._set_busy(True)
            self.feedback.emit("Verificando o modelo Argos selecionado...", False)
            self._model_service.prepare(
                self._window.runtime.source_language,
                target_language,
                install_missing_model=False,
            )
            return
        self._commit_and_close()

    @Slot(bool, str)
    def _model_prepared(self, success: bool, error_message: str) -> None:
        if self._pending_settings is None:
            return
        if success:
            self._commit_and_close()
            return

        if self._installing_model:
            self._installing_model = False
            self._pending_settings = None
            self._set_busy(False)
            self.feedback.emit(error_message, True)
            return

        language_pair = missing_argos_language_pair(error_message)
        if language_pair is None:
            self._pending_settings = None
            self._set_busy(False)
            self.feedback.emit(error_message, True)
            return

        self._set_busy(False)
        source, target = language_pair
        answer = QMessageBox.question(
            self._dialog,
            "Modelo Argos não instalado",
            (
                f"O modelo de tradução Argos {source} → {target} não está "
                "instalado.\n\nDeseja baixar e instalar esse modelo agora?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._installing_model = True
            self._set_busy(True)
            self.feedback.emit(
                f"Instalando o modelo Argos {source} → {target}...",
                False,
            )
            self._model_service.prepare(
                self._window.runtime.source_language,
                self._pending_settings[1],
                install_missing_model=True,
            )
            return

        (
            minimize_behavior,
            _target_language,
            theme,
            capture_mode,
        ) = self._pending_settings
        self._pending_settings = (
            minimize_behavior,
            DEFAULT_TARGET_LANGUAGE,
            theme,
            capture_mode,
        )
        self.feedback.emit(
            "Instalação cancelada. Idioma restaurado para Português (Brasil).",
            False,
        )
        self._commit_and_close()

    def _commit_and_close(self) -> None:
        if self._pending_settings is None:
            return
        (
            minimize_behavior,
            target_language,
            theme,
            capture_mode,
        ) = self._pending_settings
        try:
            self._window.apply_settings(
                minimize_behavior=minimize_behavior,
                target_language=target_language,
                theme=theme,
                capture_mode=capture_mode,
            )
        except ValueError as error:
            self._pending_settings = None
            self._set_busy(False)
            self.feedback.emit(str(error), True)
            return
        self._pending_settings = None
        self._installing_model = False
        self._set_busy(False)
        self._dialog.accept()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busyChanged.emit(busy)

    @Slot()
    def closeDialog(self) -> None:
        if not self._busy:
            self._dialog.reject()


class HtmlDialog(QDialog):
    """Base fixa para janelas secundárias renderizadas em HTML."""

    def __init__(
        self,
        parent: QMainWindow,
        title: str,
        html_file: str,
        theme: str,
        width: int,
        height: int,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setFixedSize(width, height)
        self._view = QWebEngineView(self)
        self._view.setGeometry(0, 0, width, height)
        self._html_url = themed_ui_url(html_file, theme)


class InformationDialog(HtmlDialog):
    def __init__(self, parent: QMainWindow, theme: str) -> None:
        super().__init__(
            parent,
            title="Como funciona",
            html_file="information.html",
            theme=theme,
            width=650,
            height=560,
        )
        self._theme = theme
        self._view.loadFinished.connect(self._apply_current_theme)
        self._view.setUrl(self._html_url)

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self._apply_current_theme(True)

    @Slot(bool)
    def _apply_current_theme(self, loaded: bool) -> None:
        if not loaded:
            return
        theme = json.dumps(self._theme)
        self._view.page().runJavaScript(
            f"document.documentElement.dataset.theme = {theme};"
        )


class SettingsDialog(HtmlDialog):
    def __init__(self, parent: ControlWindow) -> None:
        super().__init__(
            parent,
            title="Configurações",
            html_file="settings.html",
            theme=parent.settings.theme,
            width=650,
            height=650,
        )
        self._bridge = SettingsBridge(self, parent)
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("settingsBridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        self._view.setUrl(self._html_url)


class ControlWindow(QMainWindow):
    """Janela principal da aplicação e proprietária do encerramento global."""

    def __init__(
        self,
        runtime: CaptureRuntime,
        preferences: ControlPreferences,
        settings: ControlSettings,
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._preferences = preferences
        self._settings = settings
        self._closing = False
        self._information_dialog: InformationDialog | None = None
        self._settings_dialog: SettingsDialog | None = None

        self._apply_native_theme(settings.theme)

        self.setWindowTitle("Translate Screen Text")
        application = QApplication.instance()
        if application is not None and not application.windowIcon().isNull():
            self.setWindowIcon(application.windowIcon())
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setFixedSize(760, 570)

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)
        self._bridge = MainBridge(self)
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        self._view.setUrl(themed_ui_url("main.html", settings.theme))

        self._tray = self._create_tray_icon()
        self._runtime.failed.connect(self._handle_runtime_failure)
        self._runtime.stopped.connect(self._capture_stopped)

    @property
    def settings(self) -> ControlSettings:
        return self._settings

    @property
    def runtime(self) -> CaptureRuntime:
        return self._runtime

    def apply_hotkey(self, hotkey: str) -> None:
        self._settings = replace(self._settings, capture_hotkey=hotkey)
        self._preferences.save(self._settings)
        self._runtime.update_hotkey(hotkey)

    def apply_settings(
        self,
        minimize_behavior: str,
        target_language: str,
        theme: str,
        capture_mode: str,
    ) -> None:
        if minimize_behavior not in MINIMIZE_BEHAVIORS:
            raise ValueError("Comportamento de minimizar inválido")
        if target_language not in TARGET_LANGUAGE_CODES:
            raise ValueError("Idioma de destino não suportado")
        if theme not in THEMES:
            raise ValueError("Tema inválido")
        if capture_mode not in CAPTURE_MODES:
            raise ValueError("Modo de captura inválido")

        language_changed = target_language != self._settings.target_language
        capture_mode_changed = capture_mode != self._settings.capture_mode
        theme_changed = theme != self._settings.theme
        self._settings = replace(
            self._settings,
            minimize_behavior=minimize_behavior,
            target_language=target_language,
            theme=theme,
            capture_mode=capture_mode,
        )
        self._preferences.save(self._settings)
        if language_changed or capture_mode_changed:
            self._runtime.update_configuration(target_language, capture_mode)
        if theme_changed:
            self._apply_native_theme(theme)
            if self._information_dialog is not None:
                self._information_dialog.apply_theme(theme)
        self._bridge.requestState()

    def open_information(self) -> None:
        if self._information_dialog is None:
            self._information_dialog = InformationDialog(
                self,
                self._settings.theme,
            )
            self._information_dialog.finished.connect(
                self._clear_information_dialog
            )
        self._information_dialog.show()
        self._information_dialog.raise_()
        self._information_dialog.activateWindow()

    def open_settings(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self)
            self._settings_dialog.finished.connect(self._clear_settings_dialog)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    @staticmethod
    def _apply_native_theme(theme: str) -> None:
        application = QApplication.instance()
        if application is None:
            return
        color_scheme = (
            Qt.ColorScheme.Dark
            if theme == THEME_DARK
            else Qt.ColorScheme.Light
        )
        application.styleHints().setColorScheme(color_scheme)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() is QEvent.Type.WindowStateChange
            and self.isMinimized()
            and self._settings.minimize_behavior == MINIMIZE_TO_TRAY
            and self._tray.isSystemTrayAvailable()
        ):
            QTimer.singleShot(0, self._hide_in_tray)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            event.accept()
            return

        self._closing = True
        self._tray.hide()
        self._runtime.stop()
        self._runtime.wait()
        event.accept()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    @Slot()
    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot()
    def close_application(self) -> None:
        self.close()

    def _create_tray_icon(self) -> QSystemTrayIcon:
        application = QApplication.instance()
        icon = application.windowIcon()
        if icon.isNull():
            icon = application.style().standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon
            )
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip("Translate Screen Text")

        menu = QMenu(self)
        restore_action = QAction("Abrir", menu)
        restore_action.triggered.connect(self.restore_from_tray)
        close_action = QAction("Encerrar", menu)
        close_action.triggered.connect(self.close_application)
        menu.addAction(restore_action)
        menu.addSeparator()
        menu.addAction(close_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        return tray

    @Slot(QSystemTrayIcon.ActivationReason)
    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.restore_from_tray()

    def _hide_in_tray(self) -> None:
        self.hide()
        self._tray.showMessage(
            "Translate Screen Text",
            "A captura continua ativa na bandeja do Windows.",
            QSystemTrayIcon.MessageIcon.Information,
            2500,
        )

    @Slot(str)
    def _handle_runtime_failure(self, message: str) -> None:
        language_pair = missing_argos_language_pair(message)
        if language_pair is not None:
            self._handle_missing_argos_model(*language_pair)
            return

        QMessageBox.critical(
            self,
            "Falha na captura",
            f"Não foi possível manter o capturador em execução:\n{message}",
        )
        self.close()

    def _handle_missing_argos_model(self, source: str, target: str) -> None:
        answer = QMessageBox.question(
            self,
            "Modelo Argos não instalado",
            (
                f"O modelo de tradução Argos {source} → {target} não está "
                "instalado.\n\nDeseja baixar e instalar esse modelo agora?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._bridge.feedback.emit(
                f"Instalando o modelo Argos {source} → {target}...",
                False,
            )
            self._runtime.install_missing_argos_model()
            return

        if self._settings.target_language == DEFAULT_TARGET_LANGUAGE:
            self._bridge.feedback.emit(
                "O modelo Argos não foi instalado; a captura está pausada.",
                True,
            )
            return

        self._settings = replace(
            self._settings,
            target_language=DEFAULT_TARGET_LANGUAGE,
        )
        self._preferences.save(self._settings)
        self._bridge.requestState()
        self._bridge.feedback.emit(
            "Instalação cancelada. Idioma restaurado para Português (Brasil).",
            False,
        )
        self._runtime.update_target_language(DEFAULT_TARGET_LANGUAGE)

    @Slot()
    def _capture_stopped(self) -> None:
        if not self._closing:
            self.close()

    @Slot(int)
    def _clear_information_dialog(self, _result: int) -> None:
        if self._information_dialog is not None:
            self._information_dialog.deleteLater()
        self._information_dialog = None

    @Slot(int)
    def _clear_settings_dialog(self, _result: int) -> None:
        if self._settings_dialog is not None:
            self._settings_dialog.deleteLater()
        self._settings_dialog = None


def run_control_interface(
    worker_arguments: Sequence[str],
    default_hotkey: str,
    default_target_language: str,
    default_capture_mode: str = CAPTURE_MODE_REGION,
) -> int:
    """Inicializa a central PySide6 e mantém a captura ativa em paralelo."""

    configure_windows_app_user_model_id()
    qt_application = QApplication.instance() or QApplication(sys.argv[:1])
    qt_application.setApplicationName("Translate Screen Text")
    qt_application.setOrganizationName("ExceptionError")
    qt_application.setQuitOnLastWindowClosed(False)
    application_icon = load_application_icon()
    if application_icon.isNull():
        LOGGER.warning("Ícone da aplicação não encontrado em assets/icon.png.")
    else:
        qt_application.setWindowIcon(application_icon)

    preferences = ControlPreferences()
    settings = preferences.load(
        default_hotkey,
        default_target_language,
        default_capture_mode,
    )
    runtime = CaptureRuntime(
        worker_arguments,
        capture_hotkey=settings.capture_hotkey,
        target_language=settings.target_language,
        capture_mode=settings.capture_mode,
    )
    window = ControlWindow(runtime, preferences, settings)
    window.show()
    QTimer.singleShot(0, runtime.start)

    exit_code = qt_application.exec()
    runtime.stop()
    runtime.wait()
    return exit_code
