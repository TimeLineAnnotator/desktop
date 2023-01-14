import os
import sys
from pathlib import Path

import appdirs
from enum import Enum, auto

APP_NAME = "TiLiA"
APP_ICON_PATH = Path("ui", "img", "main_icon.png")
FILE_EXTENSION = "tla"
VERSION = "0.0.94"

SUPPORTED_AUDIO_FORMATS = ["ogg", "wav"]
CONVERTIBLE_AUDIO_FORMATS = [
    "mp3",
    "aac",
    "m4a",
    "flac",
]  # ffmpeg can probably convert more formats
SUPPORTED_VIDEO_FORMATS = ["mp4", "mkv", "m4a"]

DEFAULT_TIMELINE_WIDTH = 400
DEFAULT_TIMELINE_PADX = 100

DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 700
