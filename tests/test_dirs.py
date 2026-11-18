import os.path
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from tilia import dirs


@pytest.fixture
def test_dir():
    path = Path(".test")
    try:
        path.mkdir()
    except FileExistsError:
        pass

    yield path
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass


@patch("tilia.dirs._SITE_DATA_DIR", Path("site_dir"))
def test_create_data_dir_site():
    dirs.create_data_dir()

    assert os.path.exists(Path("site_dir"))

    Path.rmdir(Path("site_dir"))


def makedirs_mock_raise_permissionerror_if_sitedirs(
    dir_path: str, exist_ok: bool = True
) -> None:
    if dir_path == dirs._SITE_DATA_DIR:
        raise PermissionError
    else:
        Path(dir_path).mkdir(exist_ok=True)


@patch("tilia.dirs._USER_DATA_DIR", Path("user_dir"))
@patch("os.makedirs", side_effect=makedirs_mock_raise_permissionerror_if_sitedirs)
def test_create_data_dir_user(_):
    dirs.create_data_dir()

    assert os.path.exists(Path("user_dir"))

    Path.rmdir(Path("user_dir"))


def test_create_autosaves_dir(test_dir):
    dirs.create_autosaves_dir(test_dir)

    assert os.path.exists(Path(test_dir, "autosaves"))


def test_autosaves_go_to_an_empty_folder_of_the_test_s_own(tmp_path_factory):
    # Not the user's folder, nor the working directory, whose oldest files
    # making room for an autosave would delete.
    assert Path(dirs.autosaves_path).is_relative_to(tmp_path_factory.getbasetemp())
    assert not list(Path(dirs.autosaves_path).iterdir())
