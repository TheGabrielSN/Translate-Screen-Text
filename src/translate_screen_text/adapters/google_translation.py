"""Tradução de texto usando Google Cloud Translation v3."""

from __future__ import annotations

from typing import Any

from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import translate_v3


class GoogleTranslationError(RuntimeError):
    """Erro compreensível da integração com Google Cloud Translation."""


class GoogleCloudTranslationProvider:
    """Implementa tradução síncrona com Application Default Credentials."""

    def __init__(
        self,
        project_id: str,
        location: str = "global",
        timeout_seconds: float = 10.0,
        client: Any | None = None,
    ) -> None:
        if not project_id.strip():
            raise ValueError("project_id não pode ser vazio")
        if not location.strip():
            raise ValueError("location não pode ser vazio")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo")

        self._parent = f"projects/{project_id}/locations/{location}"
        self._timeout_seconds = timeout_seconds

        try:
            self._client = client or translate_v3.TranslationServiceClient()
        except DefaultCredentialsError as error:
            raise GoogleTranslationError(
                "Credenciais do Google Cloud não encontradas. Execute "
                "'gcloud auth application-default login' ou configure "
                "GOOGLE_APPLICATION_CREDENTIALS."
            ) from error

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

        request: dict[str, object] = {
            "parent": self._parent,
            "contents": [text],
            "mime_type": "text/plain",
            "target_language_code": target_language,
        }
        if source_language.lower() != "auto":
            request["source_language_code"] = source_language

        try:
            response = self._client.translate_text(
                request=request,
                timeout=self._timeout_seconds,
            )
        except DefaultCredentialsError as error:
            raise GoogleTranslationError(
                "As credenciais configuradas para o Google Cloud são inválidas."
            ) from error
        except GoogleAPICallError as error:
            raise GoogleTranslationError(
                f"A API do Google Cloud Translation recusou a requisição: {error}"
            ) from error

        if not response.translations:
            raise GoogleTranslationError("A API não retornou uma tradução")

        translated_text = response.translations[0].translated_text.strip()
        if not translated_text:
            raise GoogleTranslationError("A API retornou uma tradução vazia")
        return translated_text
