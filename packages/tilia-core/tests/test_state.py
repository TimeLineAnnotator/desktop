import os
import re
import sys
import threading
import time
from pathlib import Path

import platformdirs
import pytest
import tomlkit

from tilia_core import state
from tilia_core.state import StateFile, atomic_write

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")


def leftovers(folder):
    return [p.name for p in folder.iterdir() if p.name.endswith(".tmp")]


def test_state_dir_is_the_platform_folder_and_creates_nothing():
    expected = (
        Path(platformdirs.user_data_dir("TiLiA", "TiLiA", roaming=False)) / "library"
    )
    existed = expected.exists()
    assert state.state_dir() == expected
    assert expected.exists() == existed


def test_missing_file_gives_new_document_and_writes_nothing(tmp_path):
    path = tmp_path / "x.toml"
    doc = StateFile(path, 2, {1: lambda d: None}).load()
    assert dict(doc) == {"version": 2}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "content",
    [
        b'name = "x"\n',
        b"version = 0\n",
        b'version = "1"\n',
        b"version = true\n",
        b"version = [[[\n",
        b"version = 1\nname = '\xff\xfe'\n",
        b"\xff\xfe\x00",
    ],
)
def test_unreadable_files_are_set_aside(tmp_path, content):
    path = tmp_path / "library.toml"
    path.write_bytes(content)
    sf = StateFile(path, 1)
    doc = sf.load()
    assert dict(doc) == {"version": 1}
    assert not path.exists()
    assert sf.set_aside_to is not None
    assert re.fullmatch(r"library\.unreadable-\d{8}-\d{6}\.toml", sf.set_aside_to.name)
    assert sf.set_aside_to.parent == tmp_path
    assert sf.set_aside_to.read_bytes() == content
    assert sf.problem


def test_file_with_a_byte_order_mark_loads_and_is_saved_without_it(tmp_path):
    path = tmp_path / "library.toml"
    path.write_bytes(b'\xef\xbb\xbf# typed by hand\nversion = 1\nname = "a"\n')
    sf = StateFile(path, 1)
    doc = sf.load()
    assert sf.set_aside_to is None
    assert doc["name"] == "a"
    doc["name"] = "b"
    sf.save(doc)
    on_disk = path.read_bytes()
    assert on_disk.startswith(b"# typed by hand")
    assert b'name = "b"' in on_disk


def test_good_load_resets_problem(tmp_path):
    path = tmp_path / "a.toml"
    path.write_bytes(b"junk")
    sf = StateFile(path, 1)
    sf.load()
    assert sf.problem
    sf.load()
    assert sf.set_aside_to is None and sf.problem is None


def test_second_set_aside_in_same_second_gets_suffix(tmp_path, monkeypatch):
    import datetime as dt

    class Fixed(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 3, 12, 0, 0)

    monkeypatch.setattr(state, "datetime", Fixed)
    path = tmp_path / "library.toml"
    sf = StateFile(path, 1)
    names = []
    for _ in range(3):
        path.write_bytes(b"junk")
        names.append(sf.set_aside("test").name)
    assert names == [
        "library.unreadable-20261003-120000.toml",
        "library.unreadable-20261003-120000-2.toml",
        "library.unreadable-20261003-120000-3.toml",
    ]


def make_migrating(path, calls):
    def m1(doc):
        calls.append(1)
        doc["from_one"] = True

    def m2(doc):
        calls.append(2)
        doc["from_two"] = True

    return StateFile(path, 3, {1: m1, 2: m2})


def test_migrations_run_in_order_from_version_1(tmp_path):
    path = tmp_path / "f.toml"
    path.write_text("version = 1\n# keep me\nother = 5\n")
    calls = []
    doc = make_migrating(path, calls).load()
    assert calls == [1, 2]
    assert doc["version"] == 3
    on_disk = path.read_text()
    assert "# keep me" in on_disk and "other = 5" in on_disk
    parsed = tomlkit.parse(on_disk)
    assert parsed["version"] == 3
    assert parsed["from_one"] and parsed["from_two"]


def test_migrations_run_from_version_2(tmp_path):
    path = tmp_path / "f.toml"
    path.write_text("version = 2\nother = 5\n")
    calls = []
    make_migrating(path, calls).load()
    assert calls == [2]
    parsed = tomlkit.parse(path.read_text())
    assert parsed["version"] == 3 and parsed["other"] == 5
    assert "from_one" not in parsed


def test_invalid_construction(tmp_path):
    with pytest.raises(ValueError):
        StateFile(tmp_path / "f.toml", 3, {1: lambda d: None})
    with pytest.raises(ValueError):
        StateFile(tmp_path / "f.toml", 0)


def test_newer_version_is_kept(tmp_path):
    path = tmp_path / "f.toml"
    path.write_text(
        'version = 9\nknown = "a"\nunknown = 3\n\n[future]\nx = 1\n[future.deep]\ny = 2\n'
    )
    sf = StateFile(path, 1)
    doc = sf.load()
    assert path.read_text().startswith("version = 9")
    doc["known"] = "b"
    sf.save(doc)
    parsed = tomlkit.parse(path.read_text())
    assert parsed["version"] == 9
    assert parsed["known"] == "b"
    assert parsed["unknown"] == 3
    assert parsed["future"]["x"] == 1 and parsed["future"]["deep"]["y"] == 2


def test_comments_and_unknown_keys_survive(tmp_path):
    path = tmp_path / "f.toml"
    text = (
        "# top comment\nversion = 1\n\n# about known\nknown = 1  # eol comment\n"
        "mystery = 'x'\n"
    )
    path.write_text(text)
    sf = StateFile(path, 1)
    doc = sf.load()
    doc["known"] = 2
    sf.save(doc)
    assert path.read_text() == text.replace("known = 1 ", "known = 2 ")


def test_save_inserts_version_first_and_creates_folders(tmp_path):
    path = tmp_path / "a" / "b" / "f.toml"
    doc = tomlkit.document()
    doc["z"] = 1
    StateFile(path, 4, {1: lambda d: None, 2: lambda d: None, 3: lambda d: None}).save(
        doc
    )
    assert list(tomlkit.parse(path.read_text())) == ["version", "z"]


def test_atomic_write_writes_and_leaves_no_temp(tmp_path):
    path = tmp_path / "f.bin"
    atomic_write(path, b"one")
    atomic_write(path, b"two")
    assert path.read_bytes() == b"two"
    assert leftovers(tmp_path) == []
    assert [p.name for p in tmp_path.iterdir()] == ["f.bin"]


def test_atomic_write_keeps_old_file_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "f.bin"
    path.write_bytes(b"old")

    def boom(src, dst):
        raise OSError("nope")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write(path, b"new")
    assert path.read_bytes() == b"old"
    assert leftovers(tmp_path) == []


def test_atomic_write_cleans_up_on_keyboard_interrupt(tmp_path, monkeypatch):
    path = tmp_path / "f.bin"
    path.write_bytes(b"old")

    def boom(fd):
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(KeyboardInterrupt):
        atomic_write(path, b"new")
    assert path.read_bytes() == b"old"
    assert leftovers(tmp_path) == []


def flaky_replace(monkeypatch, failures):
    real = os.replace
    calls = {"n": 0}

    def replace(src, dst):
        calls["n"] += 1
        if failures is None or calls["n"] <= failures:
            raise PermissionError("held")
        real(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    return calls


def test_windows_retries_until_the_file_is_free(tmp_path, monkeypatch):
    path = tmp_path / "f.bin"
    path.write_bytes(b"old")
    monkeypatch.setattr(state, "_IS_WINDOWS", True)
    calls = flaky_replace(monkeypatch, 2)
    atomic_write(path, b"new")
    assert path.read_bytes() == b"new"
    assert calls["n"] == 3


def test_windows_gives_up_after_about_a_second(tmp_path, monkeypatch):
    path = tmp_path / "f.bin"
    path.write_bytes(b"old")
    monkeypatch.setattr(state, "_IS_WINDOWS", True)
    flaky_replace(monkeypatch, None)
    start = time.monotonic()
    with pytest.raises(PermissionError):
        atomic_write(path, b"new")
    assert 0.8 <= time.monotonic() - start <= 2.0
    assert path.read_bytes() == b"old"
    assert leftovers(tmp_path) == []


def test_posix_does_not_retry(tmp_path, monkeypatch):
    path = tmp_path / "f.bin"
    path.write_bytes(b"old")
    monkeypatch.setattr(state, "_IS_WINDOWS", False)
    calls = flaky_replace(monkeypatch, None)
    start = time.monotonic()
    with pytest.raises(PermissionError):
        atomic_write(path, b"new")
    assert time.monotonic() - start < 0.5
    assert calls["n"] == 1
    assert leftovers(tmp_path) == []


@posix_only
def test_mode_is_exact_despite_umask(tmp_path):
    path = tmp_path / "secret"
    old = os.umask(0o022)
    try:
        atomic_write(path, b"x", mode=0o600)
    finally:
        os.umask(old)
    assert path.stat().st_mode & 0o777 == 0o600


@posix_only
def test_rewrite_keeps_existing_mode(tmp_path):
    path = tmp_path / "f"
    path.write_bytes(b"a")
    path.chmod(0o640)
    atomic_write(path, b"b")
    assert path.read_bytes() == b"b"
    assert path.stat().st_mode & 0o777 == 0o640


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file locking")
def test_windows_really_held_file(tmp_path):
    target = tmp_path / "f.bin"
    target.write_bytes(b"old")
    handle = open(target, "rb")
    timer = threading.Timer(0.3, handle.close)
    timer.start()
    try:
        atomic_write(target, b"new")
    finally:
        timer.cancel()
        handle.close()
    assert target.read_bytes() == b"new"
