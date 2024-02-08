"""Partially completed ddownloader and installer from ffmpeg. Currently unused."""

import os
import subprocess
import sys
import urllib.request

from tilia.dirs import data_path

import logging

logger = logging.getLogger(__name__)

links = {
    "win32": ("https://www.gyan.dev/ffmpeg/builds/", "ffmpeg-release-essentials.zip"),
    "linux": "",
    "darwin": "https://evermeet.cx/pub/ffprobe/ffprobe-6.0.7z",
}


def _download(platform: str) -> None:
    temp_path = r"C:\ProgramData\TiLiA\TiLiA\.temp"
    url = links[platform][0] + links[platform][1]
    logger.info(f"Downloading ffmpeg from {url}")
    urllib.request.urlretrieve(url, temp_path)


def install_ffmpeg():
    # check if file already exists
    cwd = os.getcwd()
    os.chdir(data_path)
    if sys.platform == "win32":
        p = subprocess.Popen(
            f"powershell.exe -executionpolicy bypass {cwd}\\sh\\ffmpeg_install.ps1",
            shell=True,
        )
        p.wait()
    os.chdir(cwd)
