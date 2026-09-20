from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from translate_screen_text.adapters.argos_translation import (
    ArgosTranslationError,
    ArgosTranslationProvider,
    DefaultArgosBackend,
    bundled_argos_models_directory,
    register_bundled_argos_models,
)


class FakeArgosBackend:
    def __init__(
        self,
        installed: bool = True,
        model_available: bool = True,
    ) -> None:
        self.installed = installed
        self.model_available = model_available
        self.install_calls: list[tuple[str, str]] = []
        self.translation_call: tuple[str, str, str] | None = None

    def has_translation(self, source: str, target: str) -> bool:
        return self.installed

    def install_translation(self, source: str, target: str) -> bool:
        self.install_calls.append((source, target))
        if self.model_available:
            self.installed = True
        return self.model_available

    def translate(self, text: str, source: str, target: str) -> str:
        self.translation_call = (text, source, target)
        return "Novo jogo"


class ArgosTranslationProviderTests(unittest.TestCase):
    def test_translates_with_installed_model_and_normalizes_pt_br(self) -> None:
        backend = FakeArgosBackend()
        provider = ArgosTranslationProvider(backend=backend)

        translated = provider.translate("New game", "en", "pt-BR")

        self.assertEqual(translated, "Novo jogo")
        self.assertEqual(backend.translation_call, ("New game", "en", "pb"))

    def test_installs_missing_model_when_requested(self) -> None:
        backend = FakeArgosBackend(installed=False)
        provider = ArgosTranslationProvider(
            install_missing_model=True,
            backend=backend,
        )

        provider.prepare_languages("en", "pt-BR")

        self.assertEqual(backend.install_calls, [("en", "pb")])

    def test_explains_how_to_install_missing_model(self) -> None:
        provider = ArgosTranslationProvider(
            backend=FakeArgosBackend(installed=False)
        )

        with self.assertRaisesRegex(
            ArgosTranslationError,
            "--argos-install-model",
        ):
            provider.prepare_languages("en", "pt-BR")

    def test_rejects_automatic_source_language(self) -> None:
        provider = ArgosTranslationProvider(backend=FakeArgosBackend())

        with self.assertRaisesRegex(ArgosTranslationError, "automaticamente"):
            provider.translate("New game", "auto", "pt-BR")


class DefaultArgosBackendTests(unittest.TestCase):
    def test_registers_bundled_models_before_user_models(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            bundle_root = Path(temporary_directory)
            model_directory = bundle_root / "argos_models" / "translate-en_pb"
            model_directory.mkdir(parents=True)
            (model_directory / "metadata.json").write_text(
                json.dumps({"from_code": "en", "to_code": "pb"}),
                encoding="utf-8",
            )
            settings = SimpleNamespace(package_dirs=[bundle_root / "user-models"])

            with patch(
                "translate_screen_text.adapters.argos_translation."
                "bundled_argos_models_directory",
                return_value=bundle_root / "argos_models",
            ):
                registered = register_bundled_argos_models(settings)

        self.assertTrue(registered)
        self.assertEqual(
            settings.package_dirs[0],
            bundle_root / "argos_models",
        )

    def test_finds_bundled_model_with_metadata(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            bundle_root = Path(temporary_directory)
            model_directory = bundle_root / "argos_models" / "translate-en_pb"
            model_directory.mkdir(parents=True)
            (model_directory / "metadata.json").write_text("{}", encoding="utf-8")

            result = bundled_argos_models_directory([bundle_root])

        self.assertEqual(result, bundle_root / "argos_models")

    def test_clears_installed_language_cache_after_install(self) -> None:
        model_path = object()
        package = SimpleNamespace(
            from_code="en",
            to_code="pb",
            download=Mock(return_value=model_path),
        )
        package_module = SimpleNamespace(
            update_package_index=Mock(),
            get_available_packages=Mock(return_value=[package]),
            install_from_path=Mock(),
        )
        get_installed_languages = Mock()
        translate_module = SimpleNamespace(
            get_installed_languages=get_installed_languages
        )
        backend = DefaultArgosBackend()

        with (
            patch.object(
                backend,
                "_package_module",
                return_value=package_module,
            ),
            patch.object(
                backend,
                "_translate_module",
                return_value=translate_module,
            ),
        ):
            installed = backend.install_translation("en", "pb")

        self.assertTrue(installed)
        package_module.install_from_path.assert_called_once_with(model_path)
        get_installed_languages.cache_clear.assert_called_once_with()
