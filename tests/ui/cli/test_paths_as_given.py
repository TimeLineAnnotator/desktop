"""The command line's `open` and `save` take a file's path as given: a link to a folder
isn't followed, nor a short name made long, as a script's aren't (FR-095; US8). So the
media a file stores, which `load-media` takes as given too, is relative to the folder the
file is in, however that folder is reached."""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import NamedTuple
from unittest.mock import patch

import pytest

from tests.constants import EXAMPLE_MEDIA_PATH
from tilia.media.player.qtplayer import QtPlayer
from tilia.requests import Get, get
from tilia_core import build, tla


class Reached(NamedTuple):
    folder: Path  # with media in it
    given: Path  # another path to it


@pytest.fixture(autouse=True)
def media_that_is_never_played():
    with patch.object(QtPlayer, "_engine_load_media", return_value=True):
        yield


@pytest.fixture(params=["link", "short name"])
def reached(request, tmp_path) -> Reached:
    folder = tmp_path / "a folder with a long name"
    folder.mkdir()
    for name in ("rec.mp3", "other.mp3"):
        shutil.copy(EXAMPLE_MEDIA_PATH, folder / name)
    if request.param == "short name":
        return Reached(folder, short_name(folder))
    link_folder(tmp_path / "link", folder)
    return Reached(folder, tmp_path / "link")


def link_folder(link: Path, target: Path) -> None:
    """A link to a folder: a symbolic link where the system lets us make one, else,
    on Windows, a junction."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


def short_name(folder: Path) -> Path:
    """`folder` by its short (8.3) name, as Windows names the temporary folder of a
    user whose name is long."""
    if sys.platform != "win32":
        pytest.skip("Windows only")
    import ctypes

    buffer = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(folder), buffer, len(buffer))
    if not buffer.value or buffer.value.lower() == str(folder).lower():
        pytest.skip("this volume has no short names")
    return Path(buffer.value)


def stored(path: Path) -> str:
    return json.loads(path.read_bytes())["media"]["path"]


def document_with(media: Path | str) -> tla.Document:
    doc = build.new_script_document()
    build.load_media(doc, media, duration_if_error=100.0)
    return doc


def stored_by_a_script(media: Path | str, path: Path) -> str:
    tla.write(path, document_with(media))
    return stored(path)


def a_file_in(folder: Path) -> Path:
    tla.write(folder / "piece.tla", document_with(folder / "rec.mp3"))
    return folder / "piece.tla"


def test_media_and_file_given_so(cli, tilia_errors, reached):
    folder, given = reached

    cli.run(["load-media", str(given / "rec.mp3")])
    cli.run(["save", str(given / "piece.tla")])

    tilia_errors.assert_no_error()
    assert stored(folder / "piece.tla") == "rec.mp3"
    assert stored_by_a_script(given / "rec.mp3", given / "script.tla") == "rec.mp3"


def test_by_plain_names_from_there(cli, tilia_errors, reached, monkeypatch):
    folder, given = reached
    monkeypatch.chdir(given)

    cli.run(["load-media", "rec.mp3"])
    cli.run(["save", "piece.tla"])

    tilia_errors.assert_no_error()
    assert stored(folder / "piece.tla") == "rec.mp3"
    assert stored_by_a_script("rec.mp3", Path("script.tla")) == "rec.mp3"


def test_the_media_is_found_once_the_folder_has_moved(
    cli, tilia_errors, reached, monkeypatch, tmp_path
):
    folder, given = reached
    monkeypatch.chdir(given)
    cli.run(["load-media", "rec.mp3"])
    cli.run(["save", "piece.tla"])
    moved = Path(shutil.copytree(folder, tmp_path / "moved"))
    (folder / "rec.mp3").unlink()

    found = tla.media(moved / "piece.tla", tla.read(moved / "piece.tla"))

    tilia_errors.assert_no_error()
    assert found.path is not None
    assert os.path.samefile(found.path, moved / "rec.mp3")


def test_a_file_opened_and_saved_so_keeps_its_bytes(cli, tilia_errors, reached):
    path = a_file_in(reached.folder)
    before = path.read_bytes()

    cli.run(["open", str(reached.given / "piece.tla")])
    cli.run(["save", str(reached.given / "piece.tla"), "--overwrite"])

    tilia_errors.assert_no_error()
    assert path.read_bytes() == before


def test_the_media_the_file_has_keeps_its_bytes(cli, tilia_errors, reached):
    path = a_file_in(reached.folder)
    before = path.read_bytes()

    cli.run(["open", str(reached.given / "piece.tla")])
    cli.run(["load-media", str(reached.given / "rec.mp3")])
    cli.run(["save", str(reached.given / "piece.tla"), "--overwrite"])

    tilia_errors.assert_no_error()
    assert path.read_bytes() == before


def test_other_media_in_a_file_opened_so(cli, tilia_errors, reached):
    path = a_file_in(reached.folder)

    cli.run(["open", str(reached.given / "piece.tla")])
    cli.run(["load-media", str(reached.given / "other.mp3")])
    cli.run(["save", str(reached.given / "piece.tla"), "--overwrite"])

    tilia_errors.assert_no_error()
    assert stored(path) == "other.mp3"


def test_then_saved_by_the_folder_s_own_path_as_a_script_s(cli, tilia_errors, reached):
    folder, given = reached
    doc = document_with(given / "rec.mp3")
    tla.write(given / "script.tla", doc)
    tla.write(folder / "script 2.tla", doc)

    cli.run(["load-media", str(given / "rec.mp3")])
    cli.run(["save", str(given / "piece.tla")])
    cli.run(["save", str(folder / "piece 2.tla")])

    tilia_errors.assert_no_error()
    assert stored(folder / "piece 2.tla") == stored(folder / "script 2.tla")


def test_the_path_kept_for_the_file_is_absolute(cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    cli.run(["save", "piece.tla"])

    assert get(Get.FILE_PATH) == (tmp_path / "piece.tla").as_posix()


def test_a_relative_path_is_from_the_working_folder(
    cli, tilia_errors, tmp_path, monkeypatch
):
    shutil.copy(EXAMPLE_MEDIA_PATH, tmp_path / "rec.mp3")
    path = a_file_in(tmp_path)
    before = path.read_bytes()
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")

    cli.run(["open", "../piece.tla"])
    cli.run(["save", "../piece.tla", "--overwrite"])

    tilia_errors.assert_no_error()
    assert path.read_bytes() == before
    assert os.listdir(tmp_path / "work") == []


@pytest.mark.skipif(sys.platform == "win32", reason="Windows reads it by name")
def test_a_parent_after_a_link_is_the_one_the_system_reads(cli, tilia_errors, tmp_path):
    # macOS and Linux go up from the link's target, as for `load-media`: by name, it
    # would be another file.
    (tmp_path / "corpus").mkdir()
    (tmp_path / "ext" / "audio").mkdir(parents=True)
    link_folder(tmp_path / "corpus" / "audio", tmp_path / "ext" / "audio")
    shutil.copy(EXAMPLE_MEDIA_PATH, tmp_path / "ext" / "rec.mp3")
    path = a_file_in(tmp_path / "ext")
    other = tmp_path / "corpus" / "piece.tla"
    other.write_bytes(b"another file")
    before = path.read_bytes()

    cli.run(["open", f"{tmp_path}/corpus/audio/../piece.tla"])
    cli.run(["save", f"{tmp_path}/corpus/audio/../piece.tla", "--overwrite"])
    cli.run(["save", f"{tmp_path}/corpus/audio/../new.tla"])

    tilia_errors.assert_no_error()
    assert path.read_bytes() == before
    assert other.read_bytes() == b"another file"
    assert stored(tmp_path / "ext" / "new.tla") == "rec.mp3"


def test_a_link_to_a_file_stays_one_and_its_file_is_saved(cli, tilia_errors, tmp_path):
    # The core follows a link to a file, for both: the folder the paths are relative
    # to and the file written are those of the file it names.
    for name in ("real", "links"):
        (tmp_path / name).mkdir()
    shutil.copy(EXAMPLE_MEDIA_PATH, tmp_path / "real" / "rec.mp3")
    path = a_file_in(tmp_path / "real")
    link = tmp_path / "links" / "link.tla"
    try:
        link.symlink_to(path)
    except OSError as error:
        pytest.skip(f"no links to files here: {error}")
    before = path.read_bytes()

    cli.run(["open", str(link)])
    cli.run(["save", str(link), "--overwrite"])

    tilia_errors.assert_no_error()
    assert link.is_symlink()
    assert path.read_bytes() == before
