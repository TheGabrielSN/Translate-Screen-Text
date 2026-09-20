"""Caso de uso para captura e persistência de uma região da tela."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from translate_screen_text.contracts import FrameStorage, ScreenCaptureProvider
from translate_screen_text.models import Frame, ScreenRegion


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """Resultado de uma captura salva em disco."""

    region: ScreenRegion
    frame: Frame
    file_path: Path


class ScreenshotService:
    """Coordena a captura sem conhecer Pillow ou a interface gráfica."""

    def __init__(
        self,
        capture_provider: ScreenCaptureProvider,
        storage: FrameStorage,
    ) -> None:
        self._capture_provider = capture_provider
        self._storage = storage

    def capture(self, region: ScreenRegion) -> CaptureResult:
        frame = self._capture_provider.capture(region)
        file_path = self._storage.save(frame)
        return CaptureResult(region=region, frame=frame, file_path=file_path)

    def delete_capture(self, result: CaptureResult) -> None:
        """Remove o arquivo persistido depois que ele deixa de ser necessário."""

        self._storage.delete(result.file_path)
