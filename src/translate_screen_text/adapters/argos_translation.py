"""Tradução local e offline com Argos Translate."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol


BUNDLED_MODELS_DIRECTORY = "argos_models"


def bundled_argos_models_directory(
    search_roots: Sequence[Path] | None = None,
) -> Path | None:
    """Localiza modelos incorporados ao build sem substituir os do usuário."""

    if search_roots is None:
        roots: list[Path] = []
        frozen_directory = getattr(sys, "_MEIPASS", None)
        if frozen_directory is not None:
            roots.append(Path(frozen_directory))
        executable_directory = Path(sys.executable).resolve().parent
        roots.extend(
            (
                executable_directory,
                executable_directory / "_internal",
                Path(__file__).resolve().parents[3] / "executable" / "build",
            )
        )
    else:
        roots = list(search_roots)

    for root in roots:
        candidate = root / BUNDLED_MODELS_DIRECTORY
        if candidate.is_dir() and any(candidate.glob("*/metadata.json")):
            return candidate
    return None


def register_bundled_argos_models(settings_module: Any | None = None) -> bool:
    """Adiciona o modelo empacotado à busca do Argos, preservando downloads."""

    model_directory = bundled_argos_models_directory()
    if model_directory is None:
        return False
    if settings_module is None:
        import argostranslate.settings as settings_module

    configured_directories = [Path(path) for path in settings_module.package_dirs]
    if model_directory not in configured_directories:
        settings_module.package_dirs.insert(0, model_directory)
    return True


class ArgosTranslationError(RuntimeError):
    """Erro compreensível da integração com Argos Translate."""


class ArgosBackend(Protocol):
    def has_translation(self, source: str, target: str) -> bool: ...

    def install_translation(self, source: str, target: str) -> bool: ...

    def translate(self, text: str, source: str, target: str) -> str: ...


class DefaultArgosBackend:
    """Encapsula os módulos do Argos e adia seu carregamento pesado."""

    def has_translation(self, source: str, target: str) -> bool:
        translate_module = self._translate_module()
        languages = {
            language.code: language
            for language in translate_module.get_installed_languages()
        }
        source_language = languages.get(source)
        target_language = languages.get(target)
        if source_language is None or target_language is None:
            return False
        return source_language.get_translation(target_language) is not None

    def install_translation(self, source: str, target: str) -> bool:
        package_module = self._package_module()
        package_module.update_package_index()
        package = next(
            (
                candidate
                for candidate in package_module.get_available_packages()
                if candidate.from_code == source and candidate.to_code == target
            ),
            None,
        )
        if package is None:
            return False

        package_module.install_from_path(package.download())
        self._translate_module().get_installed_languages.cache_clear()
        return True

    def translate(self, text: str, source: str, target: str) -> str:
        return self._translate_module().translate(text, source, target)

    @staticmethod
    def _package_module() -> Any:
        register_bundled_argos_models()
        import argostranslate.package

        return argostranslate.package

    @staticmethod
    def _translate_module() -> Any:
        register_bundled_argos_models()
        import argostranslate.translate

        return argostranslate.translate


class ArgosTranslationProvider:
    """Traduz com modelos instalados localmente pelo Argos Translate."""

    _LANGUAGE_ALIASES = {
        "pt-br": "pb",
        "pt_br": "pb",
        "pt-pt": "pt",
        "pt_pt": "pt",
    }

    def __init__(
        self,
        install_missing_model: bool = False,
        backend: ArgosBackend | None = None,
    ) -> None:
        self._install_missing_model = install_missing_model
        self._backend = backend or DefaultArgosBackend()
        self._prepared_pairs: set[tuple[str, str]] = set()

    def prepare_languages(
        self,
        source_language: str,
        target_language: str,
    ) -> None:
        source, target = self._validated_languages(
            source_language,
            target_language,
        )
        pair = (source, target)
        if pair in self._prepared_pairs:
            return

        try:
            is_installed = self._backend.has_translation(source, target)
        except Exception as error:
            raise ArgosTranslationError(
                "Não foi possível carregar os modelos instalados do Argos."
            ) from error

        if not is_installed and self._install_missing_model:
            try:
                was_installed = self._backend.install_translation(source, target)
            except Exception as error:
                raise ArgosTranslationError(
                    f"Não foi possível baixar o modelo Argos {source} -> {target}."
                ) from error

            if not was_installed:
                raise ArgosTranslationError(
                    f"O Argos não oferece um modelo direto para {source} -> {target}."
                )

            try:
                is_installed = self._backend.has_translation(source, target)
            except Exception as error:
                raise ArgosTranslationError(
                    "O modelo foi instalado, mas não pôde ser carregado pelo Argos."
                ) from error

        if not is_installed:
            raise ArgosTranslationError(
                f"O modelo Argos {source} -> {target} não está instalado. "
                "Execute novamente com --argos-install-model."
            )

        self._prepared_pairs.add(pair)

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        if not text.strip():
            raise ValueError("text não pode ser vazio")

        self.prepare_languages(source_language, target_language)
        source, target = self._validated_languages(
            source_language,
            target_language,
        )
        try:
            translated_text = self._backend.translate(text, source, target)
        except Exception as error:
            raise ArgosTranslationError(
                f"O Argos não conseguiu traduzir de {source} para {target}."
            ) from error

        if not isinstance(translated_text, str) or not translated_text.strip():
            raise ArgosTranslationError("O Argos retornou uma tradução vazia")
        return translated_text.strip()

    @classmethod
    def _validated_languages(
        cls,
        source_language: str,
        target_language: str,
    ) -> tuple[str, str]:
        if not source_language.strip():
            raise ValueError("source_language não pode ser vazio")
        if not target_language.strip():
            raise ValueError("target_language não pode ser vazio")

        source = cls._normalize_language(source_language)
        target = cls._normalize_language(target_language)
        if source == "auto":
            raise ArgosTranslationError(
                "O Argos não detecta automaticamente o idioma. "
                "Informe --source-language."
            )
        return source, target

    @classmethod
    def _normalize_language(cls, language: str) -> str:
        normalized = language.strip().lower()
        return cls._LANGUAGE_ALIASES.get(normalized, normalized)
