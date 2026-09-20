"""Configurações e validações usadas pela interface de controle."""

from __future__ import annotations

from dataclasses import dataclass

from pynput import keyboard

MINIMIZE_NORMAL = "normal"
MINIMIZE_TO_TRAY = "tray"
MINIMIZE_BEHAVIORS = frozenset({MINIMIZE_NORMAL, MINIMIZE_TO_TRAY})

THEME_DARK = "dark"
THEME_LIGHT = "light"
THEMES = frozenset({THEME_DARK, THEME_LIGHT})

CAPTURE_MODE_REGION = "region"
CAPTURE_MODE_FULLSCREEN = "fullscreen"
CAPTURE_MODES = frozenset({CAPTURE_MODE_REGION, CAPTURE_MODE_FULLSCREEN})

TARGET_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("Português (Brasil)", "pt-BR"),
    ("Inglês", "en"),
    ("Espanhol", "es"),
    ("Francês", "fr"),
    ("Alemão", "de"),
    ("Italiano", "it"),
    ("Japonês", "ja"),
    ("Coreano", "ko"),
    ("Chinês simplificado", "zh-CN"),
)
TARGET_LANGUAGE_CODES = frozenset(code for _label, code in TARGET_LANGUAGES)

_KEY_ALIASES = {
    "control": "ctrl",
    "escape": "esc",
    "return": "enter",
    "del": "delete",
    "pgup": "page_up",
    "pgdn": "page_down",
}
_NAMED_KEYS = {
    "alt",
    "alt_gr",
    "backspace",
    "caps_lock",
    "cmd",
    "ctrl",
    "delete",
    "down",
    "end",
    "enter",
    "esc",
    "home",
    "insert",
    "left",
    "media_next",
    "media_play_pause",
    "media_previous",
    "media_volume_down",
    "media_volume_mute",
    "media_volume_up",
    "num_lock",
    "page_down",
    "page_up",
    "pause",
    "print_screen",
    "right",
    "scroll_lock",
    "shift",
    "space",
    "tab",
    "up",
}


@dataclass(frozen=True, slots=True)
class ControlSettings:
    capture_hotkey: str
    target_language: str
    minimize_behavior: str = MINIMIZE_NORMAL
    theme: str = THEME_DARK
    capture_mode: str = CAPTURE_MODE_REGION

    def __post_init__(self) -> None:
        normalize_hotkey(self.capture_hotkey)
        if self.target_language not in TARGET_LANGUAGE_CODES:
            raise ValueError("Idioma de destino não suportado")
        if self.minimize_behavior not in MINIMIZE_BEHAVIORS:
            raise ValueError("Comportamento de minimizar inválido")
        if self.theme not in THEMES:
            raise ValueError("Tema inválido")
        if self.capture_mode not in CAPTURE_MODES:
            raise ValueError("Modo de captura inválido")


def normalize_hotkey(raw_hotkey: str) -> str:
    """Converte entradas amigáveis, como Ctrl+Shift+G, para o pynput."""

    raw_tokens = [token.strip().lower() for token in raw_hotkey.split("+")]
    if not raw_tokens or any(not token for token in raw_tokens):
        raise ValueError("Informe um atalho válido")

    normalized_tokens: list[str] = []
    for raw_token in raw_tokens:
        token = raw_token.removeprefix("<").removesuffix(">")
        token = _KEY_ALIASES.get(token, token)
        is_function_key = (
            token.startswith("f")
            and token[1:].isdigit()
            and 1 <= int(token[1:]) <= 24
        )
        if token in _NAMED_KEYS or is_function_key:
            normalized_tokens.append(f"<{token}>")
        elif len(token) == 1:
            normalized_tokens.append(token)
        else:
            raise ValueError(f"Tecla não reconhecida: {raw_token}")

    normalized = "+".join(normalized_tokens)
    try:
        keyboard.HotKey.parse(normalized)
    except (TypeError, ValueError) as error:
        raise ValueError("Informe um atalho válido") from error
    return normalized
