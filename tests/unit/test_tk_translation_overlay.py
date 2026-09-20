from __future__ import annotations

import unittest

from PIL import Image

from translate_screen_text.adapters.tk_translation_overlay import (
    create_blurred_patch,
    fit_text_layout,
)
from translate_screen_text.models import BoundingBox


class CreateBlurredPatchTests(unittest.TestCase):
    def test_adds_padding_without_exceeding_image_bounds(self) -> None:
        image = Image.new("RGB", (100, 80), "white")

        patch = create_blurred_patch(
            image,
            BoundingBox(x=2, y=3, width=30, height=20),
            padding=5,
        )

        self.assertEqual((patch.left, patch.top), (0, 0))
        self.assertEqual(patch.image.size, (37, 28))

    def test_preserves_region_position_inside_image(self) -> None:
        image = Image.new("RGB", (100, 80), "white")

        patch = create_blurred_patch(
            image,
            BoundingBox(x=20, y=15, width=30, height=20),
            padding=4,
        )

        self.assertEqual((patch.left, patch.top), (16, 11))
        self.assertEqual(patch.image.size, (38, 28))


class FitTextLayoutTests(unittest.TestCase):
    def test_wraps_and_reduces_long_translation_to_fit_region(self) -> None:
        layout = fit_text_layout(
            "Esta é uma tradução consideravelmente mais longa",
            maximum_width=120,
            maximum_height=42,
        )

        self.assertIn("\n", layout.text)
        self.assertLessEqual(layout.width, 120)
        self.assertLessEqual(layout.height, 42)

    def test_keeps_short_text_on_one_line_when_it_fits(self) -> None:
        layout = fit_text_layout(
            "Jogar",
            maximum_width=160,
            maximum_height=40,
        )

        self.assertNotIn("\n", layout.text)
        self.assertLessEqual(layout.width, 160)
        self.assertLessEqual(layout.height, 40)

    def test_splits_a_long_word_without_spaces(self) -> None:
        layout = fit_text_layout(
            "CONFIGURAÇÕESAVANÇADAS",
            maximum_width=70,
            maximum_height=40,
        )

        self.assertIn("\n", layout.text)
        self.assertLessEqual(layout.width, 70)
        self.assertLessEqual(layout.height, 40)
