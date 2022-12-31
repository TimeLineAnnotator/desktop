import os
import sys
from pathlib import Path

import appdirs
from enum import Enum, auto

APP_NAME = "TiLiA"
APP_ICON_PATH = Path("ui", "img", "main_icon.png")
FILE_EXTENSION = "tla"
VERSION = "0.2.0"

SUPPORTED_AUDIO_FORMATS = ["ogg", "wav"]
CONVERTABLE_AUDIO_FORMATS = [
    "mp3",
    "aac",
    "m4a",
    "flac",
]  # ffmpeg can probably convert more formats
SUPPORTED_VIDEO_FORMATS = ["mp4", "mkv", "m4a"]

IMG_DIR = Path("ui", "img")
FFMPEG_PATH = Path("ffmpeg", "ffmpeg.exe")


try:
    DATA_DIR = Path(appdirs.user_data_dir(APP_NAME, roaming=True))
    SETTINGS_PATH = Path(DATA_DIR, "settings.toml")
    AUTOSAVE_DIR = Path(DATA_DIR, "autosaves")
except FileNotFoundError:
    DATA_DIR = Path(appdirs.site_data_dir(APP_NAME))
    SETTINGS_PATH = Path(DATA_DIR, "settings.toml")
    AUTOSAVE_DIR = Path(DATA_DIR, "autosaves")



DEFAULT_TIMELINE_WIDTH = 400
DEFAULT_TIMELINE_PADX = 100

DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 700


class UserInterfaceKind(Enum):
    TKINTER = auto()
    MOCK = auto()
