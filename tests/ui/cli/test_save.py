import argparse
import os
import tempfile

import pytest
from pathlib import Path
from io import StringIO
from unittest.mock import patch

from tests.mock import PatchPost
from tilia.requests import Post
from tilia.ui.cli.save import (
    ensure_tla_extension,
    ask_overwrite_save_path,
    validate_save_path,
    save,
)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("file.txt", "file.txt.tla"),
        ("file", "file.tla"),
        ("file.tla", "file.tla"),
    ],
)
def test_ensure_tla_extension(path, expected):
    result = ensure_tla_extension(Path(path))
    assert str(result) == expected


def test_ask_overwrite_save_path_yes(monkeypatch):
    with patch("builtins.input", return_value="yes"):
        assert ask_overwrite_save_path(Path("file.tla")) is True


def test_ask_overwrite_save_path_no(monkeypatch):
    with patch("builtins.input", return_value="no"):
        assert ask_overwrite_save_path(Path("file.tla")) is False


def test_validate_save_path_valid(tmp_path):
    path = tmp_path / "file.tla"
    validate_save_path(path)


def test_validate_save_path_parent_dir_doesnt_exist(tmp_path):
    path = tmp_path / "invalid" / "file.tla"
    with pytest.raises(ValueError):
        validate_save_path(path)


def test_validate_save_path_parent_is_file():
    with tempfile.NamedTemporaryFile() as tmp_file:
        path = Path(tmp_file.name, "file.tla")
        with pytest.raises(ValueError):
            validate_save_path(path)


def test_save_no_overwrite_existing_file(monkeypatch, tmp_path):
    path = tmp_path / "file.tla"
    path.write_text("content")
    monkeypatch.setattr("sys.stdin", StringIO("no\n"))
    namespace = argparse.Namespace(path=str(path))
    save(namespace)
    assert path.read_text() == "content"


def test_save_overwrite_existing_file(monkeypatch, tmp_path):
    path = tmp_path / "file.tla"
    path.write_text("content")
    monkeypatch.setattr("sys.stdin", StringIO("yes\n"))
    namespace = argparse.Namespace(path=str(path))
    with PatchPost("tilia.ui.cli.save", Post.REQUEST_SAVE_TO_PATH) as post_mock:
        save(namespace)
        post_mock.assert_called_once_with(Post.REQUEST_SAVE_TO_PATH, path)


def test_save_non_existing_file(monkeypatch, tmp_path):
    path = tmp_path / "file.tla"
    namespace = argparse.Namespace(path=str(path))
    with PatchPost("tilia.ui.cli.save", Post.REQUEST_SAVE_TO_PATH) as post_mock:
        save(namespace)
        post_mock.assert_called_once_with(Post.REQUEST_SAVE_TO_PATH, path)


def test_save_invalid_save_path(monkeypatch, tmp_path):
    path = tmp_path / "invalid" / "file.tla"
    namespace = argparse.Namespace(path=str(path))
    with pytest.raises(ValueError):
        save(namespace)


def test_save_valid_save(tilia, tmp_path):
    path = tmp_path / "test.tla"
    namespace = argparse.Namespace(path=str(path))
    save(namespace)
    assert os.listdir(tmp_path) == [path.name]
