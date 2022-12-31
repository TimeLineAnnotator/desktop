# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

a = Analysis(
    ["../tilia/main.py"],
    pathex=[],
    binaries=[],
    datas=[("../tilia/ui/img", "ui/img/"), ("./ffmpeg", "ffmpeg/")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=True,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [("v", None, "OPTION")],
    exclude_binaries=True,
    name="TiLiA",
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    embed_manifest=True,
    icon=str(Path(Path().resolve().parent, "tilia", "ui", "img", "main_icon.ico")),
)

coll = COLLECT(
    exe,
    a.datas,
    a.binaries,
    a.zipfiles,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TiLia",
)
