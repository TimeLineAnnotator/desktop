# -*- mode: python ; coding: utf-8 -*-
import argparse

from pathlib import Path

import tilia.constants

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true")
options = parser.parse_args()

options = parser.parse_args()

a = Analysis(
    ["./tilia/main.py"],
    pathex=[],
    binaries=None,
    datas=[
        ("./README.md", "."),
        ("./LICENSE", "."),
        ("./tilia/ui/img", "./tilia/ui/img/"),
        ("./tilia/ui/fonts", "./tilia/ui/fonts/"),
        ("./tilia/media/player/youtube.html", "./tilia/media/player/"),
        ("./tilia/media/player/youtube.css", "./tilia/media/player/"),
    ],
    hiddenimports=[],
    hookspath=None,
    runtime_hooks=None,
    excludes=None,
)

pyz = PYZ(a.pure)

if options.debug:
    exe = EXE(
        pyz,
        a.scripts,
        name="tilia-" + tilia.constants.VERSION,
        console=True,
        embed_manifest=True,
        exclude_binaries=True,
        icon=Path("tilia", "ui", "img", "main_icon.ico").resolve().__str__(),
    )

    coll = COLLECT(exe, a.datas, a.binaries, name="TiLiA")
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.datas,
        a.binaries,
        name="tilia-" + tilia.constants.VERSION,
	    console=False,
        embed_manifest=True,
        icon=Path("tilia", "ui", "img", "main_icon.ico").resolve().__str__(),
    )
    app = BUNDLE(
        exe,
        name='TiLiA.app',
        icon=Path("tilia", "ui", "img", "main_icon.ico").resolve().__str__(),
        version=tilia.constants.VERSION,
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
            'CFBundleDocumentTypes': [
                {
                    'CFBundleTypeName': 'My File Format',
                    'CFBundleTypeIconFile': 'MyFileIcon.icns',
                    'LSItemContentTypes': ['com.example.myformat'],
                    'LSHandlerRank': 'Owner'
                    }
                ]
            },
    )



