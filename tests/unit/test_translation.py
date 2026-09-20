from __future__ import annotations

import unittest

from translate_screen_text.translation import CachedTranslationProvider


class FakeTranslationProvider:
    def __init__(self) -> None:
        self.calls = 0

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        self.calls += 1
        return "Novo jogo"


class CachedTranslationProviderTests(unittest.TestCase):
    def test_reuses_translation_for_identical_request(self) -> None:
        delegate = FakeTranslationProvider()
        provider = CachedTranslationProvider(delegate)

        first = provider.translate("New game", "en", "pt-BR")
        second = provider.translate("New game", "en", "pt-BR")

        self.assertEqual(first, "Novo jogo")
        self.assertEqual(second, "Novo jogo")
        self.assertEqual(delegate.calls, 1)
