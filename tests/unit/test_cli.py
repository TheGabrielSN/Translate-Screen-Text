from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from translate_screen_text.cli import (
    _build_translation_provider,
    _capture_worker_arguments,
    _write_error_signal,
    build_parser,
)


class CliTests(unittest.TestCase):
    def test_capture_command_defaults(self) -> None:
        arguments = build_parser().parse_args(["capture"])

        self.assertEqual(arguments.hotkey, "<f6>")
        self.assertEqual(arguments.capture_mode, "region")
        self.assertEqual(arguments.output_dir, Path("output/captures"))
        self.assertEqual(arguments.ocr_confidence, 0.5)
        self.assertEqual(arguments.source_language, "en")
        self.assertEqual(arguments.target_language, "pt-BR")
        self.assertEqual(arguments.translator, "argos")
        self.assertFalse(arguments.argos_install_model)
        self.assertEqual(arguments.google_location, "global")
        self.assertFalse(arguments.ocr_only)
        self.assertEqual(arguments.log_level, "INFO")
        self.assertFalse(arguments.headless)
        self.assertTrue(callable(arguments.handler))

    def test_rejects_ocr_confidence_outside_valid_range(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["capture", "--ocr-confidence", "1.5"])

    def test_accepts_google_url_translator(self) -> None:
        arguments = build_parser().parse_args(
            ["capture", "--translator", "google-url"]
        )

        self.assertEqual(arguments.translator, "google-url")
        self.assertIsNotNone(_build_translation_provider(arguments))

    def test_accepts_argos_translator_and_model_install_option(self) -> None:
        arguments = build_parser().parse_args(
            ["capture", "--translator", "argos", "--argos-install-model"]
        )

        self.assertEqual(arguments.translator, "argos")
        self.assertTrue(arguments.argos_install_model)

    def test_accepts_fullscreen_capture_mode(self) -> None:
        arguments = build_parser().parse_args(
            ["capture", "--capture-mode", "fullscreen"]
        )

        self.assertEqual(arguments.capture_mode, "fullscreen")

    def test_builds_headless_worker_without_mutable_ui_settings(self) -> None:
        arguments = build_parser().parse_args(
            ["capture", "--translator", "google-url"]
        )

        worker_arguments = _capture_worker_arguments(arguments)

        self.assertIn("--headless", worker_arguments)
        self.assertNotIn("--hotkey", worker_arguments)
        self.assertNotIn("--target-language", worker_arguments)
        self.assertNotIn("--capture-mode", worker_arguments)

    def test_writes_capture_error_for_control_interface(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            error_file = Path(temporary_directory) / "capture.error"

            _write_error_signal(error_file, RuntimeError("modelo ausente"))

            self.assertEqual(
                error_file.read_text(encoding="utf-8"),
                "modelo ausente",
            )
