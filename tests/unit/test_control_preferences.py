from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QSettings, QUrlQuery

from translate_screen_text.control_settings import (
    CAPTURE_MODE_FULLSCREEN,
    CAPTURE_MODE_REGION,
    THEME_DARK,
    THEME_LIGHT,
)
from translate_screen_text.control_ui import (
    WINDOWS_APP_USER_MODEL_ID,
    ControlPreferences,
    application_icon_path,
    application_command_prefix,
    configure_windows_app_user_model_id,
    missing_argos_language_pair,
    themed_ui_url,
)


class ControlPreferencesTests(unittest.TestCase):
    def test_frozen_application_relaunches_its_own_executable(self) -> None:
        with (
            patch(
                "translate_screen_text.control_ui.sys.frozen",
                True,
                create=True,
            ),
            patch(
                "translate_screen_text.control_ui.sys.executable",
                r"C:\Apps\TranslateScreenText.exe",
            ),
        ):
            command = application_command_prefix()

        self.assertEqual(command, [r"C:\Apps\TranslateScreenText.exe"])

    def test_configures_a_unique_windows_application_identity(self) -> None:
        with (
            patch("translate_screen_text.control_ui.sys.platform", "win32"),
            patch(
                "translate_screen_text.control_ui.ctypes.windll",
                create=True,
            ) as windll,
        ):
            windll.shell32.SetCurrentProcessExplicitAppUserModelID.return_value = 0

            configured = configure_windows_app_user_model_id()

        self.assertTrue(configured)
        windll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(
            WINDOWS_APP_USER_MODEL_ID
        )

    def test_finds_application_png_icon(self) -> None:
        icon_path = application_icon_path()

        self.assertIsNotNone(icon_path)
        self.assertEqual(icon_path.name, "icon.png")
        self.assertEqual(icon_path.parent.name, "assets")

    def test_extracts_missing_argos_language_pair(self) -> None:
        message = (
            "O modelo Argos en -> fr não está instalado. "
            "Execute novamente com --argos-install-model."
        )

        self.assertEqual(
            missing_argos_language_pair(message),
            ("en", "fr"),
        )

    def test_ignores_unrelated_capture_error(self) -> None:
        self.assertIsNone(
            missing_argos_language_pair("Falha ao acessar o Google Translate")
        )

    def test_adds_selected_theme_to_html_url(self) -> None:
        url = themed_ui_url("main.html", THEME_LIGHT)

        self.assertEqual(
            QUrlQuery(url).queryItemValue("theme"),
            THEME_LIGHT,
        )

    def test_uses_dark_theme_by_default(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            storage = QSettings(
                str(Path(temporary_directory) / "settings.ini"),
                QSettings.Format.IniFormat,
            )

            settings = ControlPreferences(storage).load("<f6>", "pt-BR")

            self.assertEqual(settings.theme, THEME_DARK)
            self.assertEqual(settings.capture_mode, CAPTURE_MODE_REGION)

    def test_persists_selected_light_theme(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            storage = QSettings(
                str(Path(temporary_directory) / "settings.ini"),
                QSettings.Format.IniFormat,
            )
            preferences = ControlPreferences(storage)
            settings = preferences.load("<f6>", "pt-BR")
            preferences.save(replace(settings, theme=THEME_LIGHT))

            reloaded = preferences.load("<f6>", "pt-BR")

            self.assertEqual(reloaded.theme, THEME_LIGHT)

    def test_persists_fullscreen_capture_mode(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            storage = QSettings(
                str(Path(temporary_directory) / "settings.ini"),
                QSettings.Format.IniFormat,
            )
            preferences = ControlPreferences(storage)
            settings = preferences.load("<f6>", "pt-BR")
            preferences.save(
                replace(settings, capture_mode=CAPTURE_MODE_FULLSCREEN)
            )

            reloaded = preferences.load("<f6>", "pt-BR")

            self.assertEqual(
                reloaded.capture_mode,
                CAPTURE_MODE_FULLSCREEN,
            )
