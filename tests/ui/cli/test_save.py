import os

import pytest
from pathlib import Path
from io import StringIO

from tests.ui.cli.common import cli_run
from tilia.ui.cli.save import ensure_tla_extension


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


def test_save(tmp_path):
    path = tmp_path / "test.tla"
    cli_run(f'save "{str(path.resolve())}"')
    assert os.listdir(tmp_path) == [path.name]


def test_save_parent_is_file_fails(tmp_path, tilia_errors):
    parent = tmp_path / "parent"
    parent.touch()
    save_path = tmp_path / 'parent' / "file.tla"
    cli_run(f'save "{str(save_path.resolve())}"')
    tilia_errors.assert_error()
    assert not save_path.exists()


def test_save_parent_doesnt_exist_fails(tmp_path, tilia_errors):
    save_path = tmp_path / 'parent' / "file.tla"
    cli_run(f'save "{str(save_path.resolve())}"')
    tilia_errors.assert_error()
    assert not save_path.exists()


def test_save_overwrite_yes(monkeypatch, tmp_path):
    path = tmp_path / "file.tla"
    path.write_text("content")
    monkeypatch.setattr("sys.stdin", StringIO("yes\n"))
    cli_run(f'save "{str(path.resolve())}"')
    assert path.read_text() != "content"


def test_save_overwrite_no(monkeypatch, tmp_path):
    path = tmp_path / "file.tla"
    path.write_text("content")
    monkeypatch.setattr("sys.stdin", StringIO("no\n"))
    cli_run(f'save "{str(path.resolve())}"')
    assert path.read_text() == "content"


def test_save_invalid_save_path(tmp_path, tilia_errors):
    path = tmp_path / "invalid" / "file.tla"
    cli_run(f'save "{str(path.resolve())}"')
    tilia_errors.assert_error()



