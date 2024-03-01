# -*- mode: python ; coding: utf-8 -*-
import argparse

from pathlib import Path

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
        name="tilia",
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
        name="tilia",
        console=False,
        embed_manifest=True,
        icon=Path("tilia", "ui", "img", "main_icon.ico").resolve().__str__(),
    )
