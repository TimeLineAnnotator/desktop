# -*- mode: python ; coding: utf-8 -*-
import argparse
import platform
import dotenv

from pathlib import Path

from tilia.constants import APP_NAME, VERSION

# Parse build options
parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true")
options = parser.parse_args()

options = parser.parse_args()

# Set platform suffix
if platform.system() == 'Windows':
    platform_suffix = 'win'
elif platform.system() == 'Darwin':
    platform_suffix = 'mac'
elif platform.system() == 'Linux':
    platform_suffix = 'linux'
else:
    platform_suffix = platform.system()

# Set enviroment to production
dotenv.set_key(".env", "ENVIRONMENT", "prod")

# Build executable
a = Analysis(
    ["./tilia/main.py"],
    pathex=[],
    binaries=None,
    datas=[
        ("./README.md", "."),
        ("./LICENSE", "."),
        ("./.env", "."),
        ("./tilia/ui/img", "./tilia/ui/img/"),
        ("./tilia/ui/fonts", "./tilia/ui/fonts/"),
        ("./tilia/media/player/youtube.html", "./tilia/media/player/"),
        ("./tilia/media/player/youtube.css", "./tilia/media/player/"),
        ("./tilia/parsers/score/svg_maker.html", "./tilia/parsers/score/"),
        ("./tilia/parsers/score/timewise_to_partwise.xsl", "./tilia/parsers/score/"),
    ],
    hiddenimports=[],
    hookspath=None,
    runtime_hooks=None,
    excludes=None,
)

pyz = PYZ(a.pure)

icon_path = Path("tilia", "ui", "img", "main_icon.ico").resolve().__str__()
executable_basename = f"{APP_NAME.lower()}-{VERSION}-{platform_suffix}"

if options.debug:
    exe = EXE(
        pyz,
        a.scripts,
        name=executable_basename,
        console=True,
        embed_manifest=True,
        exclude_binaries=True,
        icon=icon_path,
    )

    coll = COLLECT(exe, a.datas, a.binaries, name="TiLiA")
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.datas,
        a.binaries,
        name=executable_basename,
	    console=False,
        embed_manifest=True,
        icon=icon_path,
    )
    app = BUNDLE(
        exe,
        name=f"{executable_basename}.app",
        icon=icon_path,
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

# Reset enviroment
dotenv.set_key(".env", "ENVIRONMENT", "dev")
