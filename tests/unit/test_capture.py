from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from translate_screen_text.capture import ScreenshotService
from translate_screen_text.models import Frame, ScreenRegion


class FakeCaptureProvider:
    def __init__(self) -> None:
        self.received_region: ScreenRegion | None = None

    def capture(self, region: ScreenRegion) -> Frame:
        self.received_region = region
        return Frame(
            frame_id="frame-1",
            image=object(),
            width=region.width,
            height=region.height,
            origin_x=region.left,
            origin_y=region.top,
            captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


class FakeStorage:
    def __init__(self) -> None:
        self.received_frame: Frame | None = None
        self.deleted_path: Path | None = None

    def save(self, frame: Frame) -> Path:
        self.received_frame = frame
        return Path("capture.png")

    def delete(self, file_path: Path) -> None:
        self.deleted_path = file_path


class ScreenshotServiceTests(unittest.TestCase):
    def test_captures_and_stores_selected_region(self) -> None:
        provider = FakeCaptureProvider()
        storage = FakeStorage()
        service = ScreenshotService(provider, storage)
        region = ScreenRegion(left=10, top=20, width=300, height=200)

        result = service.capture(region)

        self.assertEqual(provider.received_region, region)
        self.assertIs(storage.received_frame, result.frame)
        self.assertEqual(result.file_path, Path("capture.png"))
        self.assertEqual(result.frame.origin_x, 10)
        self.assertEqual(result.frame.origin_y, 20)

        service.delete_capture(result)

        self.assertEqual(storage.deleted_path, Path("capture.png"))
