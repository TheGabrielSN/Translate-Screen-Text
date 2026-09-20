"""Orquestracao do fluxo OCR, traducao e renderizacao."""

from __future__ import annotations

from translate_screen_text.config import PipelineSettings
from translate_screen_text.contracts import OcrProvider, Renderer, TranslationProvider
from translate_screen_text.models import Frame, PipelineResult, TranslatedRegion


class TranslationPipeline:
    """Caso de uso principal, independente das bibliotecas concretas."""

    def __init__(
        self,
        ocr: OcrProvider,
        translator: TranslationProvider,
        renderer: Renderer,
        settings: PipelineSettings,
    ) -> None:
        self._ocr = ocr
        self._translator = translator
        self._renderer = renderer
        self._settings = settings

    def process(self, frame: Frame) -> PipelineResult:
        recognized_regions = tuple(self._ocr.recognize(frame))
        translated_regions = tuple(
            TranslatedRegion(
                source=region,
                translated_text=self._translator.translate(
                    region.text,
                    self._settings.source_language,
                    self._settings.target_language,
                ),
            )
            for region in recognized_regions
            if region.confidence >= self._settings.minimum_ocr_confidence
        )
        rendered_output = self._renderer.render(frame, translated_regions)

        return PipelineResult(
            frame=frame,
            recognized_regions=recognized_regions,
            translated_regions=translated_regions,
            rendered_output=rendered_output,
        )
