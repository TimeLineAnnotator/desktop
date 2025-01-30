# -*- mode: python ; coding: utf-8 -*-
import argparse
import platform

from pathlib import Path

from tilia.constants import APP_NAME, VERSION

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true")
options = parser.parse_args()

options = parser.parse_args()

if platform.system() == 'Windows':
    platform_suffix = 'win'
elif platform.system() == 'Darwin':
    platform_suffix = 'mac'
elif platform.system() == 'Linux':  # catch all other nix platforms
    platform_suffix = 'linux'  # this must be after the Mac Darwin check, b/c Darwin is also posix
else:
    platform_suffix = platform.system()

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
        name=f"{APP_NAME.lower()}-{VERSION}-{platform_suffix}",
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
        name=f"{APP_NAME.lower()}-{VERSION}-{platform_suffix}",
	    console=False,
        embed_manifest=True,
        icon=Path("tilia", "ui", "img", "main_icon.ico").resolve().__str__(),
    )
    app = BUNDLE(
        exe,
        name=f"{APP_NAME.lower()}-{VERSION}-{platform_suffix}.app",
        icon=Path("tilia", "ui", "img", "main_icon.ico").resolve().__str__(),
        version=VERSION,
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
