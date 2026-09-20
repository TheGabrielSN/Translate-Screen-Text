from __future__ import annotations

import unittest

from translate_screen_text.control_settings import (
    CAPTURE_MODE_FULLSCREEN,
    MINIMIZE_TO_TRAY,
    THEME_DARK,
    THEME_LIGHT,
    ControlSettings,
    normalize_hotkey,
)


class NormalizeHotkeyTests(unittest.TestCase):
    def test_normalizes_single_function_key(self) -> None:
        self.assertEqual(normalize_hotkey("F8"), "<f8>")

    def test_normalizes_key_combination(self) -> None:
        self.assertEqual(
            normalize_hotkey("Control + Shift + G"),
            "<ctrl>+<shift>+g",
        )

    def test_rejects_unknown_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "não reconhecida"):
            normalize_hotkey("tecla-inexistente")


class ControlSettingsTests(unittest.TestCase):
    def test_accepts_tray_and_supported_language(self) -> None:
        settings = ControlSettings("<f6>", "pt-BR", MINIMIZE_TO_TRAY)

        self.assertEqual(settings.minimize_behavior, MINIMIZE_TO_TRAY)
        self.assertEqual(settings.theme, THEME_DARK)

    def test_accepts_light_theme(self) -> None:
        settings = ControlSettings(
            "<f6>",
            "pt-BR",
            theme=THEME_LIGHT,
        )

        self.assertEqual(settings.theme, THEME_LIGHT)

    def test_accepts_fullscreen_capture_mode(self) -> None:
        settings = ControlSettings(
            "<f6>",
            "pt-BR",
            capture_mode=CAPTURE_MODE_FULLSCREEN,
        )

        self.assertEqual(settings.capture_mode, CAPTURE_MODE_FULLSCREEN)

    def test_rejects_unknown_language(self) -> None:
        with self.assertRaisesRegex(ValueError, "não suportado"):
            ControlSettings("<f6>", "idioma-inexistente")

    def test_rejects_unknown_theme(self) -> None:
        with self.assertRaisesRegex(ValueError, "Tema inválido"):
            ControlSettings("<f6>", "pt-BR", theme="system")

    def test_rejects_unknown_capture_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "Modo de captura inválido"):
            ControlSettings("<f6>", "pt-BR", capture_mode="window")
