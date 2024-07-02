import os
from pathlib import Path

from PyQt6.QtCore import QDir, QTemporaryDir

import tilia
import platformdirs

import tilia.constants
from tilia.utils import open_with_os

autosaves_path = Path()
log_path = Path()
temp_dir: QDir | None = None
temp_path = Path()
img_path = Path("ui", "img")
_SITE_DATA_DIR = Path(platformdirs.site_data_dir(tilia.constants.APP_NAME))
_USER_DATA_DIR = Path(platformdirs.user_data_dir(tilia.constants.APP_NAME, roaming=True))
data_path = _SITE_DATA_DIR


def get_parent_path() -> Path:
    return Path(tilia.__file__).absolute().parents[1]


def get_build_path() -> Path:
    return Path(get_parent_path(), "build")


def get_tests_path() -> Path:
    return Path(get_parent_path(), "tests")


def setup_data_dir() -> Path:
    if os.path.exists(_SITE_DATA_DIR) and os.access(_SITE_DATA_DIR, os.W_OK):
        path = _SITE_DATA_DIR
    elif os.path.exists(_USER_DATA_DIR):
        path = _USER_DATA_DIR
    else:
        path = create_data_dir()

    return path


def setup_autosaves_path(data_dir):
    if not os.path.exists(autosaves_path):
        create_autosaves_dir(data_dir)


def setup_temp_path():
    global temp_dir
    temp_dir = QTemporaryDir()
    return temp_dir.path()


def setup_dirs() -> None:
    os.chdir(os.path.dirname(__file__))

    data_dir = setup_data_dir()

    global autosaves_path, log_path, temp_path

    autosaves_path = Path(data_dir, "autosaves")
    setup_autosaves_path(data_dir)

    temp_path = setup_temp_path()

    log_path = Path(data_dir, "log.txt")


def create_data_dir() -> Path:
    try:
        os.makedirs(_SITE_DATA_DIR)
        _data_path = _SITE_DATA_DIR
    except PermissionError:
        os.makedirs(_USER_DATA_DIR)
        _data_path = _USER_DATA_DIR

    return _data_path


def create_autosaves_dir(data_dir: Path):
    os.mkdir(Path(data_dir, "autosaves"))


def create_temp_dir(data_dir: Path):
    os.mkdir(Path(data_dir, ".temp"))


def open_autosaves_dir():
    open_with_os(autosaves_path)
