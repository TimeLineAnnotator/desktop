import os.path
import shutil
from pathlib import Path

from unittest.mock import patch

from tilia import dirs


@patch("tilia.dirs.SITE_DATA_DIR", Path("site_dir"))
def test_create_data_dir_site():

    dirs.create_data_dir()

    assert os.path.exists(Path("site_dir"))

    Path.rmdir(Path("site_dir"))


def makedirs_mock_raise_permissionerror_if_sitedirs(dir_path: str) -> None:
    if dir_path == dirs.SITE_DATA_DIR:
        raise PermissionError
    else:
        Path.mkdir(dir_path)


@patch("tilia.dirs.USER_DATA_DIR", Path("user_dir"))
@patch("os.makedirs", side_effect=makedirs_mock_raise_permissionerror_if_sitedirs)
def test_create_data_dir_user(_):

    dirs.create_data_dir()

    assert os.path.exists(Path("user_dir"))

    Path.rmdir(Path("user_dir"))


def test_create_settings_file():
    test_dir = Path("test_dir")
    Path.mkdir(test_dir)
    dirs.create_settings_file(test_dir)

    assert os.path.exists(test_dir)

    with open(Path(dirs.get_build_path(), "settings.toml")) as f:
        default_settings = f.read()

    with open(Path(test_dir, "settings.toml")) as f:
        assert f.read() == default_settings

    shutil.rmtree(test_dir)


def test_create_autosaves_dir():
    test_dir = Path("site_dir")
    Path.mkdir(test_dir)
    dirs.create_autosaves_dir(test_dir)

    assert os.path.exists(Path(test_dir, "autosaves"))

    shutil.rmtree(test_dir)


def os_path_exists_site_data(path: Path) -> bool:
    if path == dirs.SITE_DATA_DIR:
        return True
    else:
        return False


def os_path_exists_user_data(path: Path) -> bool:
    if path == dirs.USER_DATA_DIR:
        return True
    else:
        return False
