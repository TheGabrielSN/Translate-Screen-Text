"""Modelos compartilhados pelo pipeline de traducao."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class ScreenRegion:
    """Região retangular em coordenadas absolutas da tela."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width e height devem ser positivos")

    @classmethod
    def from_points(
        cls,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> ScreenRegion:
        """Cria uma região independentemente da direção do arraste."""

        left = min(start_x, end_x)
        top = min(start_y, end_y)
        return cls(
            left=left,
            top=top,
            width=abs(end_x - start_x),
            height=abs(end_y - start_y),
        )

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Retorna o formato (left, top, right, bottom)."""

        return (self.left, self.top, self.right, self.bottom)


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Retangulo de uma regiao, em pixels, relativo ao frame capturado."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise ValueError("x e y nao podem ser negativos")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width e height devem ser positivos")

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True, slots=True)
class Frame:
    """Imagem de entrada e metadados necessarios para posicionamento."""

    frame_id: int | str
    image: object = field(repr=False)
    width: int
    height: int
    origin_x: int = 0
    origin_y: int = 0
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width e height do frame devem ser positivos")


@dataclass(frozen=True, slots=True)
class TextRegion:
    """Texto reconhecido pelo OCR em uma regiao da imagem."""

    text: str
    bounding_box: BoundingBox
    confidence: float

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("text nao pode ser vazio")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence deve estar entre 0 e 1")


@dataclass(frozen=True, slots=True)
class TranslatedRegion:
    """Regiao reconhecida acompanhada do texto no idioma de destino."""

    source: TextRegion
    translated_text: str

    def __post_init__(self) -> None:
        if not self.translated_text.strip():
            raise ValueError("translated_text nao pode ser vazio")


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Resultado observavel de uma execucao completa."""

    frame: Frame
    recognized_regions: tuple[TextRegion, ...]
    translated_regions: tuple[TranslatedRegion, ...]
    rendered_output: object = field(repr=False)
