"""Tradução pela URL interna e não documentada do Google Translate."""

from __future__ import annotations

from typing import Any, Protocol

import requests
from requests import Response
from requests.exceptions import RequestException


class GoogleUrlTranslationError(RuntimeError):
    """Erro compreensível da integração por URL com o Google Translate."""


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> Response: ...


class GoogleUrlTranslationProvider:
    """Traduz por um endpoint público não oficial, sem credenciais."""

    ENDPOINT = "https://translate.googleapis.com/translate_a/single"
    _LANGUAGE_ALIASES = {
        "pt-br": "pt",
        "pt-pt": "pt",
    }

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        http_client: HttpClient = requests,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        if not text.strip():
            raise ValueError("text não pode ser vazio")
        if not source_language.strip():
            raise ValueError("source_language não pode ser vazio")
        if not target_language.strip():
            raise ValueError("target_language não pode ser vazio")

        params = {
            "client": "gtx",
            "sl": self._normalize_language(source_language),
            "tl": self._normalize_language(target_language),
            "dt": "t",
            "q": text,
        }

        try:
            response = self._http_client.get(
                self.ENDPOINT,
                params=params,
                timeout=self._timeout_seconds,
            )
            if response.status_code == 429:
                raise GoogleUrlTranslationError(
                    "O Google limitou as requisições deste IP (HTTP 429)."
                )
            response.raise_for_status()
            payload = response.json()
        except GoogleUrlTranslationError:
            raise
        except (RequestException, ValueError) as error:
            raise GoogleUrlTranslationError(
                "Não foi possível consultar a URL do Google Translate."
            ) from error

        translated_text = self._extract_translation(payload)
        if not translated_text:
            raise GoogleUrlTranslationError(
                "A URL do Google Translate não retornou uma tradução válida."
            )
        return translated_text

    @staticmethod
    def _extract_translation(payload: Any) -> str:
        try:
            segments = payload[0]
        except (IndexError, KeyError, TypeError):
            return ""
        if not isinstance(segments, list):
            return ""

        translated_segments: list[str] = []
        for segment in segments:
            if (
                isinstance(segment, list)
                and segment
                and isinstance(segment[0], str)
            ):
                translated_segments.append(segment[0])
        return "".join(translated_segments).strip()

    @classmethod
    def _normalize_language(cls, language: str) -> str:
        normalized = language.strip()
        return cls._LANGUAGE_ALIASES.get(normalized.lower(), normalized)
