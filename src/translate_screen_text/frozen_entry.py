"""Entrada do executável gerado pelo PyInstaller."""

from __future__ import annotations

import sys

from translate_screen_text.cli import main

VERIFY_BUNDLED_ARGOS_ARGUMENT = "--verify-bundled-argos"


def _verify_bundled_argos() -> int:
    """Exercita uma tradução real para validar o artefato empacotado."""

    try:
        from translate_screen_text.adapters.argos_translation import (
            ArgosTranslationProvider,
        )

        translated = ArgosTranslationProvider().translate(
            "New game",
            "en",
            "pt-BR",
        )
        return 0 if translated.strip() else 1
    except Exception:
        return 1


def frozen_main() -> int:
    arguments = sys.argv[1:] or ["capture"]
    if arguments == [VERIFY_BUNDLED_ARGOS_ARGUMENT]:
        return _verify_bundled_argos()
    return main(arguments)


if __name__ == "__main__":
    raise SystemExit(frozen_main())
