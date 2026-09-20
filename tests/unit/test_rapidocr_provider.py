from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any

from PIL import Image

from translate_screen_text.adapters.rapidocr_provider import RapidOcrProvider
from translate_screen_text.models import Frame


@dataclass
class FakeRapidOcrOutput:
    boxes: Any
    txts: Any
    scores: Any


class FakeRapidOcrEngine:
    def __init__(self, output: FakeRapidOcrOutput) -> None:
        self.output = output
        self.received_image: object | None = None
        self.received_text_score: float | None = None

    def __call__(self, image: object, *, text_score: float) -> FakeRapidOcrOutput:
        self.received_image = image
        self.received_text_score = text_score
        return self.output


class RapidOcrProviderTests(unittest.TestCase):
    def test_converts_ocr_output_to_text_regions(self) -> None:
        output = FakeRapidOcrOutput(
            boxes=(
                ((-3, 10), (100, 8), (102, 30), (0, 32)),
                ((10, 50), (90, 50), (90, 70), (10, 70)),
            ),
            txts=("  Start Game  ", "noise"),
            scores=(0.98, 0.20),
        )
        engine = FakeRapidOcrEngine(output)
        provider = RapidOcrProvider(minimum_confidence=0.5, engine=engine)
        image = Image.new("RGB", (200, 100), "white")
        frame = Frame(frame_id=1, image=image, width=200, height=100)

        regions = provider.recognize(frame)

        self.assertIs(engine.received_image, image)
        self.assertEqual(engine.received_text_score, 0.5)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].text, "Start Game")
        self.assertEqual(regions[0].confidence, 0.98)
        self.assertEqual(regions[0].bounding_box.x, 0)
        self.assertEqual(regions[0].bounding_box.y, 8)
        self.assertEqual(regions[0].bounding_box.width, 102)
        self.assertEqual(regions[0].bounding_box.height, 24)

    def test_returns_empty_tuple_when_ocr_finds_no_text(self) -> None:
        engine = FakeRapidOcrEngine(FakeRapidOcrOutput(None, None, None))
        provider = RapidOcrProvider(engine=engine)
        frame = Frame(
            frame_id=1,
            image=Image.new("RGB", (20, 20), "white"),
            width=20,
            height=20,
        )

        self.assertEqual(provider.recognize(frame), ())

    def test_rejects_non_pillow_images(self) -> None:
        provider = RapidOcrProvider(
            engine=FakeRapidOcrEngine(FakeRapidOcrOutput(None, None, None))
        )
        frame = Frame(frame_id=1, image=object(), width=20, height=20)

        with self.assertRaises(TypeError):
            provider.recognize(frame)
