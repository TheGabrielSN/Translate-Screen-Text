"""Implementação do contrato de OCR usando RapidOCR."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from math import ceil, floor
from typing import Any

from PIL import Image
from rapidocr import RapidOCR

from translate_screen_text.models import BoundingBox, Frame, TextRegion

OcrEngine = Callable[..., Any]


class RapidOcrProvider:
    """Detecta e reconhece linhas de texto em imagens Pillow."""

    def __init__(
        self,
        minimum_confidence: float = 0.5,
        engine: OcrEngine | None = None,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence deve estar entre 0 e 1")

        self._minimum_confidence = minimum_confidence
        self._engine = engine or RapidOCR(
            params={"Global.log_level": "warning"}
        )

    def recognize(self, frame: Frame) -> Sequence[TextRegion]:
        if not isinstance(frame.image, Image.Image):
            raise TypeError("RapidOcrProvider aceita somente imagens Pillow")

        result = self._engine(
            frame.image,
            text_score=self._minimum_confidence,
        )
        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or texts is None or scores is None:
            return ()

        regions: list[TextRegion] = []
        for polygon, text, score in zip(boxes, texts, scores):
            normalized_text = str(text).strip()
            confidence = float(score)
            if not normalized_text or confidence < self._minimum_confidence:
                continue

            bounding_box = self._polygon_to_bounding_box(
                polygon,
                frame.width,
                frame.height,
            )
            if bounding_box is None:
                continue

            regions.append(
                TextRegion(
                    text=normalized_text,
                    bounding_box=bounding_box,
                    confidence=max(0.0, min(1.0, confidence)),
                )
            )

        return tuple(regions)

    @staticmethod
    def _polygon_to_bounding_box(
        polygon: Any,
        image_width: int,
        image_height: int,
    ) -> BoundingBox | None:
        try:
            x_coordinates = [float(point[0]) for point in polygon]
            y_coordinates = [float(point[1]) for point in polygon]
        except (IndexError, TypeError, ValueError):
            return None

        if not x_coordinates or not y_coordinates:
            return None

        raw_left = floor(min(x_coordinates))
        raw_top = floor(min(y_coordinates))
        raw_right = ceil(max(x_coordinates))
        raw_bottom = ceil(max(y_coordinates))

        if (
            raw_right <= 0
            or raw_bottom <= 0
            or raw_left >= image_width
            or raw_top >= image_height
        ):
            return None

        left = max(0, raw_left)
        top = max(0, raw_top)
        right = min(image_width, raw_right)
        bottom = min(image_height, raw_bottom)
        if right <= left or bottom <= top:
            return None

        return BoundingBox(
            x=left,
            y=top,
            width=right - left,
            height=bottom - top,
        )
