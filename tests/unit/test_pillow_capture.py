from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from translate_screen_text.adapters.pillow_capture import (
    PillowScreenCapture,
    PngFrameStorage,
)
from translate_screen_text.models import Frame, ScreenRegion


class PillowScreenCaptureTests(unittest.TestCase):
    @patch("translate_screen_text.adapters.pillow_capture.ImageGrab.grab")
    def test_captures_only_selected_bounding_box(self, grab_mock) -> None:
        grab_mock.return_value = Image.new("RGB", (300, 200), "black")
        region = ScreenRegion(left=10, top=20, width=300, height=200)

        frame = PillowScreenCapture().capture(region)

        grab_mock.assert_called_once_with(bbox=(10, 20, 310, 220))
        self.assertEqual((frame.width, frame.height), (300, 200))
        self.assertEqual((frame.origin_x, frame.origin_y), (10, 20))


class PngFrameStorageTests(unittest.TestCase):
    def test_saves_pillow_image_as_png(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            frame = Frame(
                frame_id="frame-1",
                image=Image.new("RGB", (40, 30), "white"),
                width=40,
                height=30,
                captured_at=datetime(2026, 1, 1, tzinfo=UTC),
            )

            path = PngFrameStorage(Path(temporary_directory)).save(frame)

            self.assertTrue(path.is_file())
            self.assertEqual(path.suffix, ".png")
            with Image.open(path) as stored_image:
                self.assertEqual(stored_image.size, (40, 30))

            PngFrameStorage(Path(temporary_directory)).delete(path)

            self.assertFalse(path.exists())

    def test_refuses_to_delete_file_outside_capture_directory(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            temporary_path = Path(temporary_directory)
            capture_directory = temporary_path / "captures"
            capture_directory.mkdir()
            outside_file = temporary_path / "outside.png"
            outside_file.touch()

            with self.assertRaisesRegex(ValueError, "diretório configurado"):
                PngFrameStorage(capture_directory).delete(outside_file)

            self.assertTrue(outside_file.exists())
