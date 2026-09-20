from __future__ import annotations

import unittest

from translate_screen_text.adapters.google_url_translation import (
    GoogleUrlTranslationError,
    GoogleUrlTranslationProvider,
)


class FakeResponse:
    def __init__(self, payload=None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.url = None
        self.params = None
        self.timeout = None

    def get(self, url: str, *, params, timeout: float) -> FakeResponse:
        self.url = url
        self.params = params
        self.timeout = timeout
        return self.response


class GoogleUrlTranslationProviderTests(unittest.TestCase):
    def test_translates_using_query_parameters_and_normalizes_pt_br(self) -> None:
        client = FakeHttpClient(
            FakeResponse([[['Novo ', 'New '], ['jogo', 'game']]])
        )
        provider = GoogleUrlTranslationProvider(
            timeout_seconds=7,
            http_client=client,
        )

        translated = provider.translate("New game", "en", "pt-BR")

        self.assertEqual(translated, "Novo jogo")
        self.assertEqual(client.url, provider.ENDPOINT)
        self.assertEqual(
            client.params,
            {
                "client": "gtx",
                "sl": "en",
                "tl": "pt",
                "dt": "t",
                "q": "New game",
            },
        )
        self.assertEqual(client.timeout, 7)

    def test_preserves_auto_source_language(self) -> None:
        client = FakeHttpClient(FakeResponse([[['Olá', 'Bonjour']]]))
        provider = GoogleUrlTranslationProvider(http_client=client)

        provider.translate("Bonjour", "auto", "pt-BR")

        self.assertEqual(client.params["sl"], "auto")

    def test_reports_rate_limit(self) -> None:
        provider = GoogleUrlTranslationProvider(
            http_client=FakeHttpClient(FakeResponse(status_code=429))
        )

        with self.assertRaisesRegex(GoogleUrlTranslationError, "HTTP 429"):
            provider.translate("New game", "en", "pt-BR")

    def test_rejects_an_unexpected_response(self) -> None:
        provider = GoogleUrlTranslationProvider(
            http_client=FakeHttpClient(FakeResponse({"unexpected": True}))
        )

        with self.assertRaisesRegex(GoogleUrlTranslationError, "válida"):
            provider.translate("New game", "en", "pt-BR")
