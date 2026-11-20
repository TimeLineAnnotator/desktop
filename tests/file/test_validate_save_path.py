"""`validate_save_path` gives the first reason a path can't be saved to.

A folder that doesn't exist can't be written to either, and a file may be read-only,
so a later check would give the wrong reason.
"""

import os
from pathlib import Path

import pytest

from tilia.file.common import validate_save_path


@pytest.fixture
def not_writable(monkeypatch):
    """Paths added to the list this returns are ones `os.access` says can't be
    written to, as it says of a read-only file, or of a folder the user may not
    write in."""
    paths = []
    access = os.access

    def fake_access(path, mode, *args, **kwargs):
        if mode & os.W_OK and Path(path) in paths:
            return False
        return access(path, mode, *args, **kwargs)

    monkeypatch.setattr(os, "access", fake_access)
    return paths


def test_a_folder_it_can_write_to_is_valid(tmp_path):
    assert validate_save_path(tmp_path / "file.tla") == (True, "")


def test_a_missing_folder_does_not_exist(tmp_path):
    parent = tmp_path / "missing"

    assert validate_save_path(parent / "file.tla") == (
        False,
        f"Parent directory {parent} does not exist.",
    )


def test_a_missing_folder_inside_a_missing_folder_does_not_exist(tmp_path):
    parent = tmp_path / "missing" / "inner"

    assert validate_save_path(parent / "file.tla") == (
        False,
        f"Parent directory {parent} does not exist.",
    )


@pytest.mark.parametrize("writable", [True, False])
def test_a_file_is_a_file(tmp_path, not_writable, writable):
    parent = tmp_path / "parent"
    parent.touch()
    if not writable:
        not_writable.append(parent)

    assert validate_save_path(parent / "file.tla") == (
        False,
        f"Parent directory {parent} is a file.",
    )


def test_a_read_only_file_is_a_file(tmp_path):
    # A real read-only file, which `os.access` says can't be written to on every
    # system (unless the tests run as root on Linux or macOS).
    parent = tmp_path / "parent"
    parent.touch()
    os.chmod(parent, 0o444)
    try:
        assert validate_save_path(parent / "file.tla") == (
            False,
            f"Parent directory {parent} is a file.",
        )
    finally:
        os.chmod(parent, 0o644)


def test_a_folder_it_can_t_write_to_is_not_writable(tmp_path, not_writable):
    not_writable.append(tmp_path)

    assert validate_save_path(tmp_path / "file.tla") == (
        False,
        f"Parent directory {tmp_path} is not writable.",
    )
