"""Ponto de entrada da linha de comando."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from translate_screen_text import __version__
from translate_screen_text.contracts import TranslationProvider
from translate_screen_text.control_settings import (
    CAPTURE_MODE_FULLSCREEN,
    CAPTURE_MODE_REGION,
)

LOGGER = logging.getLogger(__name__)
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def confidence_value(raw_value: str) -> float:
    try:
        value = float(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("a confiança deve ser um número") from error

    if not 0.0 <= value <= 1.0:
        raise argparse.ArgumentTypeError("a confiança deve estar entre 0 e 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="translate-screen",
        description="Traduz textos reconhecidos em imagens de jogos.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    capture_parser = subparsers.add_parser(
        "capture",
        help="aguarda F6 e captura uma região ou a tela inteira",
    )
    capture_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/captures"),
        help="diretório dos arquivos PNG (padrão: output/captures)",
    )
    capture_parser.add_argument(
        "--hotkey",
        default="<f6>",
        help="hotkey no formato do pynput (padrão: <f6>)",
    )
    capture_parser.add_argument(
        "--capture-mode",
        choices=(CAPTURE_MODE_REGION, CAPTURE_MODE_FULLSCREEN),
        default=CAPTURE_MODE_REGION,
        help=(
            "modo de captura: selecionar região ou tela inteira "
            "(padrão: region)"
        ),
    )
    capture_parser.add_argument(
        "--ocr-confidence",
        type=confidence_value,
        default=0.5,
        help="confiança mínima do OCR entre 0 e 1 (padrão: 0.5)",
    )
    capture_parser.add_argument(
        "--source-language",
        default="en",
        help="idioma do texto original ou 'auto' (padrão: en)",
    )
    capture_parser.add_argument(
        "--target-language",
        default="pt-BR",
        help="idioma da tradução (padrão: pt-BR)",
    )
    capture_parser.add_argument(
        "--translator",
        choices=("google-cloud", "google-url", "argos"),
        default="argos",
        help="provedor de tradução (padrão: argos)",
    )
    capture_parser.add_argument(
        "--argos-install-model",
        action="store_true",
        help="baixa e instala o modelo Argos ausente antes da captura",
    )
    capture_parser.add_argument(
        "--google-project",
        default=os.getenv("GOOGLE_CLOUD_PROJECT"),
        help="ID do projeto Google Cloud; usa GOOGLE_CLOUD_PROJECT por padrão",
    )
    capture_parser.add_argument(
        "--google-location",
        default="global",
        help="localização da API Google Cloud (padrão: global)",
    )
    capture_parser.add_argument(
        "--ocr-only",
        action="store_true",
        help="executa somente captura e OCR, sem chamar a API de tradução",
    )
    capture_parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="nível de detalhamento dos logs (padrão: INFO)",
    )
    capture_parser.add_argument(
        "--headless",
        action="store_true",
        help="executa sem a interface de controle PySide6",
    )
    capture_parser.add_argument(
        "--stop-signal-file",
        type=Path,
        help=argparse.SUPPRESS,
    )
    capture_parser.add_argument(
        "--error-signal-file",
        type=Path,
        help=argparse.SUPPRESS,
    )
    capture_parser.set_defaults(handler=_run_capture)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    handler = getattr(arguments, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    configure_logging(arguments.log_level)
    return handler(arguments)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format=LOG_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def _run_capture(arguments: argparse.Namespace) -> int:
    if not arguments.headless:
        try:
            from translate_screen_text.control_ui import run_control_interface

            return run_control_interface(
                _capture_worker_arguments(arguments),
                default_hotkey=arguments.hotkey,
                default_target_language=arguments.target_language,
                default_capture_mode=arguments.capture_mode,
            )
        except Exception as error:
            LOGGER.error("Não foi possível iniciar a interface: %s", error)
            LOGGER.debug("Detalhes da falha da interface", exc_info=True)
            return 1

    from translate_screen_text.adapters.pillow_capture import (
        PillowScreenCapture,
        PngFrameStorage,
    )
    from translate_screen_text.adapters.rapidocr_provider import RapidOcrProvider
    from translate_screen_text.capture import ScreenshotService
    from translate_screen_text.capture_ui import CaptureHotkeyApplication

    try:
        LOGGER.info(
            "Inicializando captura com o provedor de tradução '%s'.",
            "desabilitado" if arguments.ocr_only else arguments.translator,
        )
        translation_provider = _build_translation_provider(arguments)

        service = ScreenshotService(
            capture_provider=PillowScreenCapture(),
            storage=PngFrameStorage(arguments.output_dir),
        )
        application = CaptureHotkeyApplication(
            screenshot_service=service,
            ocr_provider=RapidOcrProvider(
                minimum_confidence=arguments.ocr_confidence
            ),
            translation_provider=translation_provider,
            source_language=arguments.source_language,
            target_language=arguments.target_language,
            capture_hotkey=arguments.hotkey,
            capture_mode=arguments.capture_mode,
            stop_signal_file=arguments.stop_signal_file,
        )
        return application.run()
    except Exception as error:
        _write_error_signal(arguments.error_signal_file, error)
        LOGGER.error("Não foi possível iniciar a captura: %s", error)
        LOGGER.debug("Detalhes da falha de inicialização", exc_info=True)
        return 1


def _write_error_signal(file_path: Path | None, error: Exception) -> None:
    """Comunica ao processo da interface a causa da falha do capturador."""

    if file_path is None:
        return
    try:
        file_path.write_text(str(error), encoding="utf-8")
    except OSError as signal_error:
        LOGGER.warning(
            "Não foi possível comunicar a falha para a interface: %s",
            signal_error,
        )


def _capture_worker_arguments(arguments: argparse.Namespace) -> list[str]:
    """Reconstrói os argumentos imutáveis usados pelo processo de captura."""

    worker_arguments = [
        "capture",
        "--headless",
        "--output-dir",
        str(arguments.output_dir),
        "--ocr-confidence",
        str(arguments.ocr_confidence),
        "--source-language",
        arguments.source_language,
        "--translator",
        arguments.translator,
        "--google-location",
        arguments.google_location,
        "--log-level",
        arguments.log_level,
    ]
    if arguments.argos_install_model:
        worker_arguments.append("--argos-install-model")
    if arguments.google_project:
        worker_arguments.extend(("--google-project", arguments.google_project))
    if arguments.ocr_only:
        worker_arguments.append("--ocr-only")
    return worker_arguments


def _build_translation_provider(
    arguments: argparse.Namespace,
) -> TranslationProvider | None:
    if arguments.ocr_only:
        return None

    from translate_screen_text.translation import CachedTranslationProvider

    if arguments.translator == "google-url":
        from translate_screen_text.adapters.google_url_translation import (
            GoogleUrlTranslationProvider,
        )

        return CachedTranslationProvider(GoogleUrlTranslationProvider())

    if arguments.translator == "argos":
        from translate_screen_text.adapters.argos_translation import (
            ArgosTranslationProvider,
        )

        if arguments.argos_install_model:
            LOGGER.info(
                "Preparando o modelo Argos; o primeiro download pode demorar."
            )
        provider = ArgosTranslationProvider(
            install_missing_model=arguments.argos_install_model
        )
        provider.prepare_languages(
            arguments.source_language,
            arguments.target_language,
        )
        return CachedTranslationProvider(provider)

    if not arguments.google_project:
        raise ValueError(
            "Informe --google-project ou defina GOOGLE_CLOUD_PROJECT para usar "
            "google-cloud. Use --translator argos para tradução local, "
            "--translator google-url para tradução por URL sem credenciais "
            "ou --ocr-only para executar sem tradução."
        )

    from translate_screen_text.adapters.google_translation import (
        GoogleCloudTranslationProvider,
    )

    return CachedTranslationProvider(
        GoogleCloudTranslationProvider(
            project_id=arguments.google_project,
            location=arguments.google_location,
        )
    )
