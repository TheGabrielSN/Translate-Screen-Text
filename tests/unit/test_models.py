from __future__ import annotations

import unittest

from translate_screen_text.models import BoundingBox, ScreenRegion, TextRegion


class ScreenRegionTests(unittest.TestCase):
    def test_normalizes_reverse_drag_direction(self) -> None:
        region = ScreenRegion.from_points(100, 80, 20, 30)

        self.assertEqual(region.bbox, (20, 30, 100, 80))

    def test_accepts_negative_screen_coordinates(self) -> None:
        region = ScreenRegion(left=-1920, top=0, width=1920, height=1080)

        self.assertEqual(region.right, 0)

    def test_rejects_selection_without_area(self) -> None:
        with self.assertRaises(ValueError):
            ScreenRegion.from_points(10, 10, 10, 20)


class BoundingBoxTests(unittest.TestCase):
    def test_calculates_right_and_bottom_edges(self) -> None:
        box = BoundingBox(x=10, y=20, width=30, height=40)

        self.assertEqual(box.right, 40)
        self.assertEqual(box.bottom, 60)

    def test_rejects_non_positive_dimensions(self) -> None:
        with self.assertRaises(ValueError):
            BoundingBox(x=0, y=0, width=0, height=10)


class TextRegionTests(unittest.TestCase):
    def test_rejects_confidence_outside_valid_range(self) -> None:
        with self.assertRaises(ValueError):
            TextRegion(
                text="Start",
                bounding_box=BoundingBox(0, 0, 100, 20),
                confidence=1.1,
            )
