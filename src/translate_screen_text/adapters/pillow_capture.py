"""Captura e armazenamento de imagens usando Pillow."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageGrab

from translate_screen_text.models import Frame, ScreenRegion


class PillowScreenCapture:
    """Implementação de captura para o monitor principal."""

    def capture(self, region: ScreenRegion) -> Frame:
        captured_at = datetime.now(UTC)
        image = ImageGrab.grab(bbox=region.bbox)
        return Frame(
            frame_id=uuid4().hex,
            image=image,
            width=image.width,
            height=image.height,
            origin_x=region.left,
            origin_y=region.top,
            captured_at=captured_at,
        )


class PngFrameStorage:
    """Salva frames Pillow como PNG em um diretório configurado."""

    def __init__(self, output_directory: Path) -> None:
        self._output_directory = output_directory

    def save(self, frame: Frame) -> Path:
        if not isinstance(frame.image, Image.Image):
            raise TypeError("PngFrameStorage aceita somente imagens Pillow")

        self._output_directory.mkdir(parents=True, exist_ok=True)
        timestamp = frame.captured_at.astimezone(UTC).strftime("%Y%m%d_%H%M%S_%f")
        safe_frame_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(frame.frame_id))[:12]
        file_path = self._output_directory / (
            f"capture_{timestamp}_{safe_frame_id or uuid4().hex[:12]}.png"
        )
        frame.image.save(file_path, format="PNG")
        return file_path.resolve()

    def delete(self, file_path: Path) -> None:
        output_directory = self._output_directory.resolve()
        target = file_path.resolve()
        if target.parent != output_directory or target.suffix.lower() != ".png":
            raise ValueError(
                "A captura só pode ser excluída dentro do diretório configurado"
            )
        target.unlink(missing_ok=True)
