"""Configuracoes independentes de interface e infraestrutura."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PipelineSettings:
    """Opcoes usadas em uma execucao do pipeline."""

    source_language: str
    target_language: str
    minimum_ocr_confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.source_language.strip():
            raise ValueError("source_language nao pode ser vazio")
        if not self.target_language.strip():
            raise ValueError("target_language nao pode ser vazio")
        if not 0.0 <= self.minimum_ocr_confidence <= 1.0:
            raise ValueError("minimum_ocr_confidence deve estar entre 0 e 1")
