import os
from pathlib import Path

import tilia
import appdirs

from tilia import globals_

settings_path = ""
autosaves_path = ""
log_path = ""
data_path = ""
img_path = Path("ui", "img")
ffmpeg_path = Path("ffmpeg", "ffmpeg.exe")
SITE_DATA_DIR = Path(appdirs.site_data_dir(globals_.APP_NAME))
USER_DATA_DIR = Path(appdirs.user_data_dir(globals_.APP_NAME, roaming=True))


def get_parent_path() -> Path:
    return Path(tilia.__file__).absolute().parents[1]


def get_build_path() -> Path:
    return Path(get_parent_path(), "build")


def get_tests_path() -> Path:
    return Path(get_parent_path(), "tests")


def setup_data_dir() -> Path:
    if os.path.exists(SITE_DATA_DIR):
        return SITE_DATA_DIR
    elif os.path.exists(USER_DATA_DIR):
        return USER_DATA_DIR
    else:
        return create_data_dir()


def setup_settings_file(data_dir):
    if not os.path.exists(settings_path):
        create_settings_file(data_dir)


def setup_autosaves_path(data_dir):
    if not os.path.exists(autosaves_path):
        create_autosaves_dir(data_dir)


def setup_dirs() -> None:
    os.chdir(os.path.dirname(__file__))

    data_dir = setup_data_dir()

    global settings_path, autosaves_path, log_path

    settings_path = Path(data_dir, "settings.toml")
    setup_settings_file(data_dir)

    autosaves_path = Path(data_dir, "autosaves")
    setup_autosaves_path(data_dir)

    log_path = Path(data_dir, "log.txt")


def create_data_dir() -> Path:
    try:
        os.makedirs(SITE_DATA_DIR)
        return SITE_DATA_DIR
    except PermissionError:
        os.makedirs(USER_DATA_DIR)
        return USER_DATA_DIR


def create_settings_file(data_dir: Path):
    with open(Path(get_build_path(), "settings.toml")) as f:
        default_settings = f.read()

    with open(Path(data_dir, "settings.toml"), "w") as f:
        f.write(default_settings)


def create_autosaves_dir(data_dir: Path):
    os.mkdir(Path(data_dir, "autosaves"))
