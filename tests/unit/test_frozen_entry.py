from __future__ import annotations

import unittest
from unittest.mock import patch

from translate_screen_text.frozen_entry import (
    VERIFY_BUNDLED_ARGOS_ARGUMENT,
    frozen_main,
)


class FrozenEntryTests(unittest.TestCase):
    def test_runs_bundled_argos_verification(self) -> None:
        with (
            patch(
                "translate_screen_text.frozen_entry.sys.argv",
                ["app.exe", VERIFY_BUNDLED_ARGOS_ARGUMENT],
            ),
            patch(
                "translate_screen_text.frozen_entry._verify_bundled_argos",
                return_value=0,
            ) as verify,
        ):
            exit_code = frozen_main()

        self.assertEqual(exit_code, 0)
        verify.assert_called_once_with()

    def test_opens_capture_interface_when_executable_has_no_arguments(self) -> None:
        with (
            patch("translate_screen_text.frozen_entry.sys.argv", ["app.exe"]),
            patch(
                "translate_screen_text.frozen_entry.main",
                return_value=0,
            ) as main,
        ):
            exit_code = frozen_main()

        self.assertEqual(exit_code, 0)
        main.assert_called_once_with(["capture"])

    def test_preserves_worker_arguments_when_executable_relaunches_itself(self) -> None:
        arguments = ["capture", "--headless", "--translator", "argos"]
        with (
            patch(
                "translate_screen_text.frozen_entry.sys.argv",
                ["app.exe", *arguments],
            ),
            patch(
                "translate_screen_text.frozen_entry.main",
                return_value=0,
            ) as main,
        ):
            frozen_main()

        main.assert_called_once_with(arguments)
