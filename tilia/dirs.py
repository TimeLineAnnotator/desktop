import os
from pathlib import Path

import platformdirs

import tilia.constants
from tilia.utils import open_with_os

autosaves_path = Path()
logs_path = Path()
tmp_path = Path()
_SITE_DATA_DIR = Path(platformdirs.site_data_dir(tilia.constants.APP_NAME))
_USER_DATA_DIR = Path(
    platformdirs.user_data_dir(tilia.constants.APP_NAME, roaming=True)
)


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


def setup_tmp_path(data_dir):
    if not os.path.exists(tmp_path):
        create_tmp_path(data_dir)


def setup_dirs() -> None:
    # if not in prod, set directory to root of tilia
    if os.environ.get("ENVIRONMENT") != "prod":
        os.chdir(os.path.dirname(__file__))

    data_dir = setup_data_dir()

    global autosaves_path, logs_path, tmp_path

    autosaves_path = Path(data_dir, "autosaves")
    setup_autosaves_path(data_dir)

    logs_path = Path(data_dir, "logs")
    setup_logs_path(data_dir)

    tmp_path = Path(data_dir, "tmp")
    setup_tmp_path(data_dir)


def create_data_dir() -> Path:
    try:
        os.makedirs(_SITE_DATA_DIR, exist_ok=True)
        _data_path = _SITE_DATA_DIR
    except PermissionError:
        os.makedirs(_USER_DATA_DIR, exist_ok=True)
        _data_path = _USER_DATA_DIR

    return _data_path


def create_autosaves_dir(data_dir: Path):
    os.mkdir(Path(data_dir, "autosaves"))


def create_logs_dir(data_dir: Path):
    os.mkdir(Path(data_dir, "logs"))


def create_tmp_path(data_dir: Path):
    os.mkdir(Path(data_dir, "tmp"))


def open_autosaves_dir():
    open_with_os(autosaves_path)


def clear_tmp_path():
    for root, dirs, files in os.walk(tmp_path, False):
        r = Path(root)
        for f in files:
            try:
                os.unlink(r / f)
            except PermissionError:  # file is in use
                continue
        for d in dirs:  # dir is not empty
            try:
                os.rmdir(r / d)
            except OSError:
                continue
