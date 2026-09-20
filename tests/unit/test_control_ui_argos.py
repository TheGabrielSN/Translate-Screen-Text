from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

from translate_screen_text.control_settings import (
    CAPTURE_MODE_FULLSCREEN,
    ControlSettings,
)
from translate_screen_text.control_ui import ControlWindow, SettingsBridge


class FakeSignal:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def emit(self, *arguments: object) -> None:
        self.calls.append(arguments)


class FakeBridge:
    def __init__(self) -> None:
        self.feedback = FakeSignal()
        self.state_requests = 0

    def requestState(self) -> None:
        self.state_requests += 1


class FakePreferences:
    def __init__(self) -> None:
        self.saved_settings: ControlSettings | None = None

    def save(self, settings: ControlSettings) -> None:
        self.saved_settings = settings


class FakeRuntime:
    def __init__(self) -> None:
        self.install_calls = 0
        self.target_updates: list[str] = []

    def install_missing_argos_model(self) -> None:
        self.install_calls += 1

    def update_target_language(self, language: str) -> None:
        self.target_updates.append(language)


class FakeDialog(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.accept_calls = 0
        self.reject_calls = 0

    def accept(self) -> None:
        self.accept_calls += 1

    def reject(self) -> None:
        self.reject_calls += 1


class FakeModelService(QObject):
    finished = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.prepare_calls: list[tuple[str, str, bool]] = []

    def prepare(
        self,
        source: str,
        target: str,
        install_missing_model: bool,
    ) -> None:
        self.prepare_calls.append(
            (source, target, install_missing_model)
        )


class FakeSettingsRuntime:
    uses_argos = True
    source_language = "en"


class FakeSettingsWindow:
    def __init__(self) -> None:
        self.settings = ControlSettings("<f6>", "pt-BR")
        self.runtime = FakeSettingsRuntime()
        self.applied_settings: list[tuple[str, str, str, str]] = []

    def apply_settings(
        self,
        minimize_behavior: str,
        target_language: str,
        theme: str,
        capture_mode: str,
    ) -> None:
        self.applied_settings.append(
            (minimize_behavior, target_language, theme, capture_mode)
        )
        self.settings = replace(
            self.settings,
            minimize_behavior=minimize_behavior,
            target_language=target_language,
            theme=theme,
            capture_mode=capture_mode,
        )


class MissingArgosModelUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = FakeBridge()
        self.preferences = FakePreferences()
        self.runtime = FakeRuntime()
        self.window = SimpleNamespace(
            _bridge=self.bridge,
            _preferences=self.preferences,
            _runtime=self.runtime,
            _settings=ControlSettings("<f6>", "fr"),
        )

    def test_installs_selected_model_when_user_confirms(self) -> None:
        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            ControlWindow._handle_missing_argos_model(
                self.window,
                "en",
                "fr",
            )

        self.assertEqual(self.runtime.install_calls, 1)
        self.assertEqual(self.runtime.target_updates, [])

    def test_restores_pt_br_when_user_declines(self) -> None:
        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.No,
        ):
            ControlWindow._handle_missing_argos_model(
                self.window,
                "en",
                "fr",
            )

        self.assertEqual(self.window._settings.target_language, "pt-BR")
        self.assertEqual(self.runtime.target_updates, ["pt-BR"])
        self.assertEqual(
            self.preferences.saved_settings.target_language,
            "pt-BR",
        )
        self.assertEqual(self.bridge.state_requests, 1)


class ArgosModelValidationBeforeSaveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dialog = FakeDialog()
        self.window = FakeSettingsWindow()
        self.model_service = FakeModelService()
        self.bridge = SettingsBridge(
            self.dialog,
            self.window,
            model_service=self.model_service,
        )

    def _save_french(self) -> None:
        self.bridge.saveSettings(
            "normal",
            "fr",
            "dark",
            CAPTURE_MODE_FULLSCREEN,
        )

    def test_closes_only_after_confirming_installed_model(self) -> None:
        self._save_french()

        self.assertEqual(
            self.model_service.prepare_calls,
            [("en", "fr", False)],
        )
        self.assertEqual(self.dialog.accept_calls, 0)

        self.model_service.finished.emit(True, "")

        self.assertEqual(self.dialog.accept_calls, 1)
        self.assertEqual(self.window.settings.target_language, "fr")
        self.assertEqual(
            self.window.settings.capture_mode,
            CAPTURE_MODE_FULLSCREEN,
        )

    def test_installs_model_before_closing_when_user_confirms(self) -> None:
        self._save_french()
        missing_model = (
            "O modelo Argos en -> fr não está instalado. "
            "Execute novamente com --argos-install-model."
        )

        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            self.model_service.finished.emit(False, missing_model)

        self.assertEqual(self.dialog.accept_calls, 0)
        self.assertEqual(
            self.model_service.prepare_calls[-1],
            ("en", "fr", True),
        )

        self.model_service.finished.emit(True, "")

        self.assertEqual(self.dialog.accept_calls, 1)
        self.assertEqual(self.window.settings.target_language, "fr")

    def test_restores_pt_br_before_closing_when_user_declines(self) -> None:
        self._save_french()
        missing_model = (
            "O modelo Argos en -> fr não está instalado. "
            "Execute novamente com --argos-install-model."
        )

        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.No,
        ):
            self.model_service.finished.emit(False, missing_model)

        self.assertEqual(self.dialog.accept_calls, 1)
        self.assertEqual(self.window.settings.target_language, "pt-BR")
