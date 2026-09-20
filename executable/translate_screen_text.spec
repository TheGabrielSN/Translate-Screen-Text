# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


EXECUTABLE_ROOT = Path(SPECPATH)
PROJECT_ROOT = EXECUTABLE_ROOT.parent
SOURCE_ROOT = PROJECT_ROOT / "src"
MODEL_DIRECTORY = EXECUTABLE_ROOT / "build" / "argos_models"

if not MODEL_DIRECTORY.is_dir():
    raise SystemExit(
        "Modelo Argos ausente. Execute executable/prepare_argos_model.py antes do build."
    )

datas = [
    (
        str(PROJECT_ROOT / "src" / "translate_screen_text" / "ui"),
        "translate_screen_text/ui",
    ),
    (
        str(PROJECT_ROOT / "src" / "translate_screen_text" / "assets"),
        "translate_screen_text/assets",
    ),
    (str(MODEL_DIRECTORY), "argos_models"),
]
binaries = []
hiddenimports = []

for package_name in ("argostranslate", "rapidocr", "ctranslate2", "onnxruntime"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

analysis = Analysis(
    [str(PROJECT_ROOT / "src" / "translate_screen_text" / "frozen_entry.py")],
    pathex=[str(SOURCE_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="TranslateScreenText",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(EXECUTABLE_ROOT / "assets" / "icon.ico"),
)

distribution = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TranslateScreenText",
)
