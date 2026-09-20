from __future__ import annotations

import unittest
from collections.abc import Sequence

from translate_screen_text.config import PipelineSettings
from translate_screen_text.models import Frame, TextRegion, TranslatedRegion
from translate_screen_text.models import BoundingBox
from translate_screen_text.pipeline import TranslationPipeline


class FakeOcr:
    def recognize(self, frame: Frame) -> Sequence[TextRegion]:
        return (
            TextRegion("Play", BoundingBox(10, 20, 100, 30), 0.95),
            TextRegion("noise", BoundingBox(10, 60, 100, 30), 0.20),
        )


class FakeTranslator:
    def __init__(self) -> None:
        self.received_texts: list[str] = []

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        self.received_texts.append(text)
        return {"Play": "Jogar"}[text]


class FakeRenderer:
    def __init__(self) -> None:
        self.received_regions: tuple[TranslatedRegion, ...] = ()

    def render(
        self,
        frame: Frame,
        regions: Sequence[TranslatedRegion],
    ) -> object:
        self.received_regions = tuple(regions)
        return "rendered-image"


class TranslationPipelineTests(unittest.TestCase):
    def test_processes_only_regions_above_confidence_threshold(self) -> None:
        translator = FakeTranslator()
        renderer = FakeRenderer()
        pipeline = TranslationPipeline(
            ocr=FakeOcr(),
            translator=translator,
            renderer=renderer,
            settings=PipelineSettings(
                source_language="en",
                target_language="pt-BR",
                minimum_ocr_confidence=0.5,
            ),
        )
        frame = Frame(frame_id=1, image=object(), width=1920, height=1080)

        result = pipeline.process(frame)

        self.assertEqual(len(result.recognized_regions), 2)
        self.assertEqual(len(result.translated_regions), 1)
        self.assertEqual(result.translated_regions[0].translated_text, "Jogar")
        self.assertEqual(translator.received_texts, ["Play"])
        self.assertEqual(renderer.received_regions, result.translated_regions)
        self.assertEqual(result.rendered_output, "rendered-image")
