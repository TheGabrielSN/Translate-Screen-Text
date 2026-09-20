from __future__ import annotations

import unittest
from types import SimpleNamespace

from google.api_core.exceptions import ServiceUnavailable

from translate_screen_text.adapters.google_translation import (
    GoogleCloudTranslationProvider,
    GoogleTranslationError,
)


class FakeTranslationClient:
    def __init__(self, translated_text: str = "Novo jogo") -> None:
        self.translated_text = translated_text
        self.request = None
        self.timeout = None
        self.calls = 0

    def translate_text(self, *, request, timeout):
        self.calls += 1
        self.request = request
        self.timeout = timeout
        return SimpleNamespace(
            translations=[SimpleNamespace(translated_text=self.translated_text)]
        )


class FailingTranslationClient:
    def translate_text(self, *, request, timeout):
        raise ServiceUnavailable("serviço indisponível")


class GoogleCloudTranslationProviderTests(unittest.TestCase):
    def test_translates_plain_text_with_language_configuration(self) -> None:
        client = FakeTranslationClient()
        provider = GoogleCloudTranslationProvider(
            project_id="game-project",
            location="global",
            timeout_seconds=7,
            client=client,
        )

        translated = provider.translate("New game", "en", "pt-BR")

        self.assertEqual(translated, "Novo jogo")
        self.assertEqual(client.timeout, 7)
        self.assertEqual(
            client.request,
            {
                "parent": "projects/game-project/locations/global",
                "contents": ["New game"],
                "mime_type": "text/plain",
                "target_language_code": "pt-BR",
                "source_language_code": "en",
            },
        )

    def test_omits_source_language_when_auto_detection_is_requested(self) -> None:
        client = FakeTranslationClient()
        provider = GoogleCloudTranslationProvider("game-project", client=client)

        provider.translate("Bonjour", "auto", "pt-BR")

        self.assertNotIn("source_language_code", client.request)

    def test_wraps_google_api_errors(self) -> None:
        provider = GoogleCloudTranslationProvider(
            "game-project",
            client=FailingTranslationClient(),
        )

        with self.assertRaisesRegex(GoogleTranslationError, "recusou"):
            provider.translate("New game", "en", "pt-BR")
