from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from translate_screen_text.capture import CaptureResult
from translate_screen_text.capture_ui import (
    CaptureHotkeyApplication,
    CaptureCommand,
    QueuedCommand,
    format_recognized_text,
)
from translate_screen_text.control_settings import CAPTURE_MODE_FULLSCREEN
from translate_screen_text.models import BoundingBox, Frame, ScreenRegion, TextRegion


class FormatRecognizedTextTests(unittest.TestCase):
    def test_prints_each_detected_region_on_its_own_line(self) -> None:
        regions = (
            TextRegion("New Game", BoundingBox(0, 0, 100, 20), 0.95),
            TextRegion("Settings", BoundingBox(0, 30, 100, 20), 0.90),
        )

        self.assertEqual(format_recognized_text(regions), "New Game\nSettings")

    def test_formats_empty_result(self) -> None:
        self.assertEqual(format_recognized_text(()), "")


class FakeScreenshotService:
    def __init__(self) -> None:
        self.deleted_result: CaptureResult | None = None

    def capture(self, region: ScreenRegion) -> CaptureResult:
        return CaptureResult(
            region=region,
            frame=Frame(
                frame_id="frame-1",
                image=object(),
                width=region.width,
                height=region.height,
                captured_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            file_path=Path("capture.png"),
        )

    def delete_capture(self, result: CaptureResult) -> None:
        self.deleted_result = result


class FakeOcrProvider:
    def recognize(self, frame: Frame) -> tuple[TextRegion, ...]:
        return (
            TextRegion("New Game", BoundingBox(0, 0, 100, 20), 0.95),
        )


class FakeTranslationProvider:
    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        return "Novo jogo"


class FakeTranslationOverlay:
    def __init__(self) -> None:
        self.show_call = None
        self.hide_calls = 0

    def show(self, frame, screen_region, regions) -> None:
        self.show_call = (frame, screen_region, tuple(regions))

    def hide(self) -> None:
        self.hide_calls += 1


class FakeInputActivityMonitor:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class FakeLoadingIndicator:
    def __init__(self) -> None:
        self.show_calls: list[tuple[ScreenRegion, str]] = []
        self.hide_calls = 0

    def show(self, screen_region: ScreenRegion, message: str) -> None:
        self.show_calls.append((screen_region, message))

    def hide(self) -> None:
        self.hide_calls += 1


class FakeRoot:
    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def after(self, _delay: int, callback) -> None:
        callback()


class CaptureLoggingTests(unittest.TestCase):
    def test_fullscreen_mode_captures_without_opening_selector(self) -> None:
        application = CaptureHotkeyApplication(
            screenshot_service=FakeScreenshotService(),
            ocr_provider=FakeOcrProvider(),
            input_activity_monitor=FakeInputActivityMonitor(),
            capture_mode=CAPTURE_MODE_FULLSCREEN,
        )
        captured_regions: list[ScreenRegion] = []
        application._root = FakeRoot()
        application._capture_region = captured_regions.append

        application._begin_selection()

        self.assertEqual(
            captured_regions,
            [ScreenRegion(0, 0, 1920, 1080)],
        )

    def test_consumes_stop_signal_created_by_control_interface(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            stop_signal = Path(temporary_directory) / "stop.signal"
            stop_signal.touch()
            application = CaptureHotkeyApplication(
                screenshot_service=FakeScreenshotService(),
                ocr_provider=FakeOcrProvider(),
                input_activity_monitor=FakeInputActivityMonitor(),
                stop_signal_file=stop_signal,
            )

            self.assertTrue(application._stop_was_requested_by_controller())
            self.assertFalse(stop_signal.exists())

    def test_logs_processing_steps_and_results(self) -> None:
        overlay = FakeTranslationOverlay()
        loading_indicator = FakeLoadingIndicator()
        screenshot_service = FakeScreenshotService()
        application = CaptureHotkeyApplication(
            screenshot_service=screenshot_service,
            ocr_provider=FakeOcrProvider(),
            translation_provider=FakeTranslationProvider(),
            translation_overlay=overlay,
            input_activity_monitor=FakeInputActivityMonitor(),
            loading_indicator=loading_indicator,
        )

        with self.assertLogs(
            "translate_screen_text.capture_ui",
            level="INFO",
        ) as captured_logs:
            application._capture_region(ScreenRegion(10, 20, 100, 40))
            self.assertIsNotNone(application._processing_thread)
            application._processing_thread.join(timeout=2)
            application._poll_processing_results()

        output = "\n".join(captured_logs.output)
        self.assertIn("[ETAPA 1/5]", output)
        self.assertIn("[ETAPA 2/5]", output)
        self.assertIn("[ETAPA 3/5]", output)
        self.assertIn("[ETAPA 4/5]", output)
        self.assertIn("[ETAPA 5/5]", output)
        self.assertIn("New Game", output)
        self.assertIn("Novo jogo", output)
        self.assertIsNotNone(overlay.show_call)
        translated_regions = overlay.show_call[2]
        self.assertEqual(len(translated_regions), 1)
        self.assertEqual(translated_regions[0].translated_text, "Novo jogo")
        self.assertIsNotNone(screenshot_service.deleted_result)
        self.assertEqual(
            loading_indicator.show_calls,
            [(ScreenRegion(10, 20, 100, 40), "Processando e traduzindo...")],
        )
        self.assertEqual(loading_indicator.hide_calls, 1)

    def test_clears_visible_overlay_after_input_activity(self) -> None:
        overlay = FakeTranslationOverlay()
        application = CaptureHotkeyApplication(
            screenshot_service=FakeScreenshotService(),
            ocr_provider=FakeOcrProvider(),
            translation_provider=FakeTranslationProvider(),
            translation_overlay=overlay,
            input_activity_monitor=FakeInputActivityMonitor(),
        )
        application._overlay_shown_at = monotonic() - 1

        with self.assertLogs(
            "translate_screen_text.capture_ui",
            level="INFO",
        ) as captured_logs:
            application._clear_overlay_after_activity(
                QueuedCommand(
                    CaptureCommand.CLEAR_OVERLAY,
                    occurred_at=monotonic(),
                    source="mouse",
                )
            )

        self.assertEqual(overlay.hide_calls, 1)
        self.assertIsNone(application._overlay_shown_at)
        self.assertIn("tela restaurada", "\n".join(captured_logs.output))

    def test_ignores_activity_that_happened_before_overlay_was_shown(self) -> None:
        overlay = FakeTranslationOverlay()
        application = CaptureHotkeyApplication(
            screenshot_service=FakeScreenshotService(),
            ocr_provider=FakeOcrProvider(),
            translation_provider=FakeTranslationProvider(),
            translation_overlay=overlay,
            input_activity_monitor=FakeInputActivityMonitor(),
        )
        shown_at = monotonic()
        application._overlay_shown_at = shown_at

        application._clear_overlay_after_activity(
            QueuedCommand(
                CaptureCommand.CLEAR_OVERLAY,
                occurred_at=shown_at - 1,
                source="teclado",
            )
        )

        self.assertEqual(overlay.hide_calls, 0)
        self.assertEqual(application._overlay_shown_at, shown_at)
