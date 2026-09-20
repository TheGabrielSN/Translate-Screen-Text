"""Overlay transparente para exibir traduções sobre a tela capturada."""

from __future__ import annotations

import ctypes
import os
import sys
import tkinter as tk
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageTk

from translate_screen_text.models import (
    BoundingBox,
    Frame,
    ScreenRegion,
    TranslatedRegion,
)


@dataclass(frozen=True, slots=True)
class BlurredPatch:
    image: Image.Image
    left: int
    top: int


@dataclass(frozen=True, slots=True)
class TextLayout:
    text: str
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    font_size: int
    spacing: int
    bounds: tuple[int, int, int, int]

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]


MINIMUM_FONT_SIZE = 6
MAXIMUM_FONT_SIZE = 72
TEXT_STROKE_WIDTH = 1


@lru_cache(maxsize=128)
def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = (
        windows_fonts / "segoeuib.ttf",
        windows_fonts / "arialbd.ttf",
        Path("DejaVuSans-Bold.ttf"),
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    bounds = draw.textbbox(
        (0, 0),
        text,
        font=font,
        stroke_width=TEXT_STROKE_WIDTH,
    )
    return bounds[2] - bounds[0]


def _split_long_token(
    draw: ImageDraw.ImageDraw,
    token: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    maximum_width: int,
) -> list[str]:
    pieces: list[str] = []
    current = ""
    for character in token:
        candidate = current + character
        if current and _text_width(draw, candidate, font) > maximum_width:
            pieces.append(current)
            current = character
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces or [""]


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    maximum_width: int,
) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if _text_width(draw, candidate, font) <= maximum_width:
                current = candidate
                continue

            if current:
                lines.append(current)
                current = ""

            pieces = _split_long_token(draw, word, font, maximum_width)
            lines.extend(pieces[:-1])
            current = pieces[-1]

        if current:
            lines.append(current)
    return lines or [""]


def _measure_layout(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    font_size: int,
) -> TextLayout:
    spacing = max(1, round(font_size * 0.16))
    content = "\n".join(lines)
    bounds = draw.multiline_textbbox(
        (0, 0),
        content,
        font=font,
        spacing=spacing,
        align="center",
        stroke_width=TEXT_STROKE_WIDTH,
    )
    return TextLayout(
        text=content,
        font=font,
        font_size=font_size,
        spacing=spacing,
        bounds=bounds,
    )


def _truncate_layout(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    font_size: int,
    maximum_width: int,
    maximum_height: int,
) -> TextLayout:
    visible_lines = list(lines)
    layout = _measure_layout(draw, visible_lines, font, font_size)
    while len(visible_lines) > 1 and layout.height > maximum_height:
        visible_lines.pop()
        visible_lines[-1] = visible_lines[-1].rstrip("…") + "…"
        while (
            visible_lines[-1]
            and _text_width(draw, visible_lines[-1], font) > maximum_width
        ):
            content = visible_lines[-1].rstrip("…")
            visible_lines[-1] = content[:-1] + "…" if content else ""
        layout = _measure_layout(draw, visible_lines, font, font_size)

    while visible_lines and layout.width > maximum_width:
        content = visible_lines[-1].rstrip("…")
        visible_lines[-1] = content[:-1] + "…" if content else ""
        layout = _measure_layout(draw, visible_lines, font, font_size)
    return layout


def fit_text_layout(
    text: str,
    maximum_width: int,
    maximum_height: int,
) -> TextLayout:
    """Encontra o maior texto multilinha que cabe integralmente na região."""

    if maximum_width <= 0 or maximum_height <= 0:
        raise ValueError("A área disponível para o texto deve ser positiva")

    measuring_image = Image.new("L", (1, 1))
    draw = ImageDraw.Draw(measuring_image)
    largest_size = max(
        MINIMUM_FONT_SIZE,
        min(MAXIMUM_FONT_SIZE, int(maximum_height * 1.25)),
    )
    smallest_layout: TextLayout | None = None
    smallest_lines: list[str] = []
    smallest_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None

    for font_size in range(largest_size, MINIMUM_FONT_SIZE - 1, -1):
        font = _load_font(font_size)
        lines = _wrap_text(draw, text, font, maximum_width)
        layout = _measure_layout(draw, lines, font, font_size)
        if layout.width <= maximum_width and layout.height <= maximum_height:
            return layout
        smallest_layout = layout
        smallest_lines = lines
        smallest_font = font

    if smallest_layout is None or smallest_font is None:
        raise RuntimeError("Não foi possível calcular o layout do texto")
    return _truncate_layout(
        draw,
        smallest_lines,
        smallest_font,
        MINIMUM_FONT_SIZE,
        maximum_width,
        maximum_height,
    )


def create_blurred_patch(
    image: Image.Image,
    bounding_box: BoundingBox,
    padding: int = 4,
    blur_radius: float = 7.0,
) -> BlurredPatch:
    """Recorta, amplia levemente e desfoca a região do texto original."""

    left = max(0, bounding_box.x - padding)
    top = max(0, bounding_box.y - padding)
    right = min(image.width, bounding_box.right + padding)
    bottom = min(image.height, bounding_box.bottom + padding)
    patch = image.crop((left, top, right, bottom))
    patch = patch.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    patch = ImageEnhance.Brightness(patch).enhance(0.55)
    return BlurredPatch(image=patch, left=left, top=top)


class TkTranslationOverlay:
    """Janela transparente, sempre no topo e atravessável pelo mouse."""

    TRANSPARENT_COLOR = "#010203"
    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_LAYERED = 0x00080000
    WS_EX_NOACTIVATE = 0x08000000

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._window: tk.Toplevel | None = None
        self._images: list[ImageTk.PhotoImage] = []

    def show(
        self,
        frame: Frame,
        screen_region: ScreenRegion,
        regions: Sequence[TranslatedRegion],
    ) -> None:
        if not isinstance(frame.image, Image.Image):
            raise TypeError("O overlay aceita somente frames com imagem Pillow")

        self.hide()
        if not regions:
            return

        window = tk.Toplevel(self._root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(background=self.TRANSPARENT_COLOR)
        window.geometry(
            f"{screen_region.width}x{screen_region.height}"
            f"{screen_region.left:+d}{screen_region.top:+d}"
        )

        try:
            window.attributes("-transparentcolor", self.TRANSPARENT_COLOR)
        except tk.TclError:
            pass

        canvas = tk.Canvas(
            window,
            width=screen_region.width,
            height=screen_region.height,
            background=self.TRANSPARENT_COLOR,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        self._window = window
        self._images = []
        for translated_region in regions:
            self._draw_blurred_background(canvas, frame.image, translated_region)
        for translated_region in regions:
            self._draw_translated_text(canvas, translated_region)

        window.update_idletasks()
        self._enable_click_through(window)
        window.lift()

    def hide(self) -> None:
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
        self._window = None
        self._images.clear()

    def _draw_blurred_background(
        self,
        canvas: tk.Canvas,
        image: Image.Image,
        translated_region: TranslatedRegion,
    ) -> None:
        box = translated_region.source.bounding_box
        patch = create_blurred_patch(image, box)
        photo = ImageTk.PhotoImage(patch.image, master=canvas)
        self._images.append(photo)
        canvas.create_image(
            patch.left,
            patch.top,
            image=photo,
            anchor=tk.NW,
        )

    def _draw_translated_text(
        self,
        canvas: tk.Canvas,
        translated_region: TranslatedRegion,
    ) -> None:
        box = translated_region.source.bounding_box
        text_image = Image.new("RGBA", (box.width, box.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_image)
        horizontal_margin = 4
        vertical_margin = 2
        maximum_width = max(1, box.width - horizontal_margin * 2)
        maximum_height = max(1, box.height - vertical_margin * 2)
        layout = fit_text_layout(
            translated_region.translated_text,
            maximum_width,
            maximum_height,
        )
        text_x = (box.width - layout.width) / 2 - layout.bounds[0]
        text_y = (box.height - layout.height) / 2 - layout.bounds[1]
        draw.multiline_text(
            (text_x, text_y),
            layout.text,
            fill="#ffffff",
            font=layout.font,
            spacing=layout.spacing,
            align="center",
            stroke_width=TEXT_STROKE_WIDTH,
            stroke_fill="#000000",
        )

        photo = ImageTk.PhotoImage(text_image, master=canvas)
        self._images.append(photo)
        canvas.create_image(
            box.x,
            box.y,
            image=photo,
            anchor=tk.NW,
        )

    @classmethod
    def _enable_click_through(cls, window: tk.Toplevel) -> None:
        if sys.platform != "win32":
            return

        try:
            window_handle = ctypes.windll.user32.GetParent(window.winfo_id())
            current_style = ctypes.windll.user32.GetWindowLongW(
                window_handle,
                cls.GWL_EXSTYLE,
            )
            ctypes.windll.user32.SetWindowLongW(
                window_handle,
                cls.GWL_EXSTYLE,
                current_style
                | cls.WS_EX_LAYERED
                | cls.WS_EX_TRANSPARENT
                | cls.WS_EX_TOOLWINDOW
                | cls.WS_EX_NOACTIVATE,
            )
        except (AttributeError, OSError):
            pass
