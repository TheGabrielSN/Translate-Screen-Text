"""Serviços auxiliares independentes do provedor de tradução."""

from __future__ import annotations

from translate_screen_text.contracts import TranslationProvider


class CachedTranslationProvider:
    """Evita chamadas repetidas ao provedor durante a execução atual."""

    def __init__(self, provider: TranslationProvider) -> None:
        self._provider = provider
        self._cache: dict[tuple[str, str, str], str] = {}

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        key = (text, source_language, target_language)
        cached_translation = self._cache.get(key)
        if cached_translation is not None:
            return cached_translation

        translated_text = self._provider.translate(
            text,
            source_language,
            target_language,
        )
        self._cache[key] = translated_text
        return translated_text
