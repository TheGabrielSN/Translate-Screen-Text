"""Monitoramento global de teclado, mouse e controles XInput."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from threading import Event, Thread

from pynput import keyboard, mouse

InputActivityCallback = Callable[[str], None]


class XInputGamepad(ctypes.Structure):
    _fields_ = (
        ("buttons", ctypes.c_ushort),
        ("left_trigger", ctypes.c_ubyte),
        ("right_trigger", ctypes.c_ubyte),
        ("left_thumb_x", ctypes.c_short),
        ("left_thumb_y", ctypes.c_short),
        ("right_thumb_x", ctypes.c_short),
        ("right_thumb_y", ctypes.c_short),
    )


class XInputState(ctypes.Structure):
    _fields_ = (
        ("packet_number", ctypes.c_ulong),
        ("gamepad", XInputGamepad),
    )


ControllerSnapshot = tuple[int, int, int, int, int, int, int]


def controller_snapshot(state: XInputState) -> ControllerSnapshot:
    """Normaliza o estado e elimina pequenos ruídos dos analógicos."""

    gamepad = state.gamepad

    def trigger(value: int) -> int:
        return 0 if value < 30 else value // 8

    def axis(value: int, deadzone: int) -> int:
        return 0 if abs(value) < deadzone else value // 2048

    return (
        int(gamepad.buttons),
        trigger(int(gamepad.left_trigger)),
        trigger(int(gamepad.right_trigger)),
        axis(int(gamepad.left_thumb_x), 7849),
        axis(int(gamepad.left_thumb_y), 7849),
        axis(int(gamepad.right_thumb_x), 8689),
        axis(int(gamepad.right_thumb_y), 8689),
    )


class XInputControllerMonitor:
    """Observa até quatro controles compatíveis com XInput no Windows."""

    POLL_INTERVAL_SECONDS = 0.05
    ERROR_SUCCESS = 0

    def __init__(self, callback: InputActivityCallback) -> None:
        self._callback = callback
        self._get_state = self._load_get_state()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._previous_states: dict[int, ControllerSnapshot] = {}

    @property
    def available(self) -> bool:
        return self._get_state is not None

    def start(self) -> None:
        if not self.available or self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name="xinput-activity-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._poll()
            self._stop_event.wait(self.POLL_INTERVAL_SECONDS)

    def _poll(self) -> None:
        if self._get_state is None:
            return

        for controller_index in range(4):
            state = XInputState()
            result = self._get_state(controller_index, ctypes.byref(state))
            if result != self.ERROR_SUCCESS:
                self._previous_states.pop(controller_index, None)
                continue

            snapshot = controller_snapshot(state)
            previous = self._previous_states.get(controller_index)
            self._previous_states[controller_index] = snapshot
            if previous is None:
                continue
            if snapshot != previous or any(snapshot):
                self._callback("controle")

    @staticmethod
    def _load_get_state():
        if sys.platform != "win32":
            return None

        for library_name in ("xinput1_4", "xinput9_1_0", "xinput1_3"):
            try:
                library = ctypes.WinDLL(library_name)
                get_state = library.XInputGetState
                get_state.argtypes = [
                    ctypes.c_ulong,
                    ctypes.POINTER(XInputState),
                ]
                get_state.restype = ctypes.c_ulong
                return get_state
            except (AttributeError, OSError):
                continue
        return None


class GlobalInputActivityMonitor:
    """Unifica eventos globais de teclado, mouse e controle."""

    def __init__(self, callback: InputActivityCallback) -> None:
        self._callback = callback
        self._keyboard_listener: keyboard.Listener | None = None
        self._mouse_listener: mouse.Listener | None = None
        self._controller_monitor = XInputControllerMonitor(callback)

    def start(self) -> None:
        if self._keyboard_listener is not None:
            return

        self._keyboard_listener = keyboard.Listener(
            on_press=lambda _key: self._callback("teclado"),
            on_release=lambda _key: self._callback("teclado"),
        )
        self._mouse_listener = mouse.Listener(
            on_click=lambda _x, _y, _button, _pressed: self._callback("mouse"),
        )
        self._keyboard_listener.start()
        self._mouse_listener.start()
        self._controller_monitor.start()

    def stop(self) -> None:
        listeners = (self._keyboard_listener, self._mouse_listener)
        for listener in listeners:
            if listener is not None:
                listener.stop()
        for listener in listeners:
            if listener is not None:
                listener.join(timeout=1)

        self._keyboard_listener = None
        self._mouse_listener = None
        self._controller_monitor.stop()
