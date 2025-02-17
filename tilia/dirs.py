import os
from pathlib import Path

import tilia
import platformdirs

import tilia.constants
from tilia.utils import open_with_os

autosaves_path = Path()
logs_path = Path()
_SITE_DATA_DIR = Path(platformdirs.site_data_dir(tilia.constants.APP_NAME))
_USER_DATA_DIR = Path(
    platformdirs.user_data_dir(tilia.constants.APP_NAME, roaming=True)
)
data_path = _SITE_DATA_DIR
PROJECT_ROOT = Path(tilia.__file__).parents[1]


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


def setup_logs_path(data_dir):
    if not os.path.exists(logs_path):
        create_logs_dir(data_dir)


def setup_dirs() -> None:
    os.chdir(os.path.dirname(__file__))

    data_dir = setup_data_dir()

    global autosaves_path, logs_path

    autosaves_path = Path(data_dir, "autosaves")
    setup_autosaves_path(data_dir)

    logs_path = Path(data_dir, "logs")
    setup_logs_path(data_dir)


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


def create_logs_dir(data_dir: Path):
    os.mkdir(Path(data_dir, "logs"))


def open_autosaves_dir():
    open_with_os(autosaves_path)
