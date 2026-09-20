"""Indicador visual exibido durante o OCR e a traducao."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from translate_screen_text.models import ScreenRegion


class TkLoadingIndicator:
    """Janela sempre no topo com uma barra de progresso indeterminada."""

    WINDOW_WIDTH = 320
    WINDOW_HEIGHT = 92

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._window: tk.Toplevel | None = None
        self._progress: ttk.Progressbar | None = None

    def show(self, screen_region: ScreenRegion, message: str) -> None:
        self.hide()

        width = min(self.WINDOW_WIDTH, max(200, screen_region.width))
        height = self.WINDOW_HEIGHT
        left = screen_region.left + (screen_region.width - width) // 2
        top = screen_region.top + (screen_region.height - height) // 2

        window = tk.Toplevel(self._root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.94)
        window.geometry(f"{width}x{height}{left:+d}{top:+d}")
        window.configure(background="#101820")

        label = tk.Label(
            window,
            text=message,
            background="#101820",
            foreground="white",
            font=("Segoe UI", 11, "bold"),
        )
        label.pack(padx=20, pady=(16, 10))

        progress = ttk.Progressbar(
            window,
            mode="indeterminate",
            length=max(160, width - 40),
        )
        progress.pack(padx=20, pady=(0, 16))
        progress.start(12)

        self._window = window
        self._progress = progress
        window.lift()
        window.update_idletasks()

    def hide(self) -> None:
        progress = self._progress
        window = self._window
        self._progress = None
        self._window = None

        if progress is not None:
            progress.stop()
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass
