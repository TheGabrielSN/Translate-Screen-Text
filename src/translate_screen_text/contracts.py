"""Contratos implementados pelas integracoes externas."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from translate_screen_text.models import (
    Frame,
    ScreenRegion,
    TextRegion,
    TranslatedRegion,
)


class ScreenCaptureProvider(Protocol):
    """Captura uma região da tela e devolve um frame em memória."""

    def capture(self, region: ScreenRegion) -> Frame: ...


class FrameStorage(Protocol):
    """Persiste um frame capturado e informa o caminho gerado."""

    def save(self, frame: Frame) -> Path: ...

    def delete(self, file_path: Path) -> None: ...


class OcrProvider(Protocol):
    """Localiza e reconhece textos em um frame."""

    def recognize(self, frame: Frame) -> Sequence[TextRegion]: ...


class TranslationProvider(Protocol):
    """Traduz uma unidade textual entre dois idiomas."""

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str: ...


class TranslationOverlay(Protocol):
    """Exibe regiões traduzidas sobre a área original da tela."""

    def show(
        self,
        frame: Frame,
        screen_region: ScreenRegion,
        regions: Sequence[TranslatedRegion],
    ) -> None: ...

    def hide(self) -> None: ...


class LoadingIndicator(Protocol):
    """Informa visualmente que a captura ainda esta sendo processada."""

    def show(self, screen_region: ScreenRegion, message: str) -> None: ...

    def hide(self) -> None: ...


class InputActivityMonitor(Protocol):
    """Inicia e encerra a observação de entradas globais do usuário."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


class Renderer(Protocol):
    """Compoe as traducoes sobre o frame ou outra superficie de saida."""

    def render(
        self,
        frame: Frame,
        regions: Sequence[TranslatedRegion],
    ) -> object: ...
