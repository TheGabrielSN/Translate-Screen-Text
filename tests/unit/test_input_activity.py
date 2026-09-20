from __future__ import annotations

import unittest
from unittest.mock import patch

from translate_screen_text.adapters.input_activity import (
    GlobalInputActivityMonitor,
    XInputState,
    controller_snapshot,
)


class ControllerSnapshotTests(unittest.TestCase):
    def test_ignores_trigger_and_stick_noise_inside_deadzones(self) -> None:
        state = XInputState()
        state.gamepad.left_trigger = 20
        state.gamepad.right_trigger = 29
        state.gamepad.left_thumb_x = 7000
        state.gamepad.left_thumb_y = -7000
        state.gamepad.right_thumb_x = 8000
        state.gamepad.right_thumb_y = -8000

        self.assertEqual(controller_snapshot(state), (0, 0, 0, 0, 0, 0, 0))

    def test_preserves_meaningful_controller_activity(self) -> None:
        state = XInputState()
        state.gamepad.buttons = 0x1000
        state.gamepad.left_trigger = 80
        state.gamepad.left_thumb_x = 12000

        snapshot = controller_snapshot(state)

        self.assertEqual(snapshot[0], 0x1000)
        self.assertGreater(snapshot[1], 0)
        self.assertGreater(snapshot[3], 0)


class GlobalInputActivityMonitorTests(unittest.TestCase):
    def test_mouse_listener_reports_only_clicks(self) -> None:
        activities: list[str] = []
        monitor = GlobalInputActivityMonitor(activities.append)

        with (
            patch(
                "translate_screen_text.adapters.input_activity.keyboard.Listener"
            ) as keyboard_listener,
            patch(
                "translate_screen_text.adapters.input_activity.mouse.Listener"
            ) as mouse_listener,
            patch.object(monitor._controller_monitor, "start"),
        ):
            monitor.start()

        mouse_callbacks = mouse_listener.call_args.kwargs
        self.assertEqual(set(mouse_callbacks), {"on_click"})
        mouse_callbacks["on_click"](10, 20, object(), True)
        self.assertEqual(activities, ["mouse"])
        keyboard_listener.return_value.start.assert_called_once_with()
