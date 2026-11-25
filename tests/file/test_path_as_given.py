"""The path TiLiA keeps for the file that is open is the one it was given, made
absolute: a link to a folder isn't followed, nor a drive letter that stands for another
folder (TimeLineAnnotator/project-management#686, point 2, a). The document is read from
that path, its media and its PDFs are looked up from it, and Save writes to it, so that a
save without an edit changes nothing (FR-003), by whichever path the file is opened."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple
from unittest.mock import patch

import pytest

from tests.constants import EXAMPLE_MEDIA_PATH
from tests.file.test_save_through_core import (
    EVERY_KIND,
    RESOURCES,
    first_of_kind,
    open_file,
    record,
    save,
    save_as,
    the_document,
    written_by_the_core,
)
from tests.mock import Serve
from tilia.media.player import QtAudioPlayer
from tilia.requests import Get, get
from tilia.settings import settings
from tilia.ui import commands
from tilia_core import tla


class Reached(NamedTuple):
    folder: Path  # with a file, its media and its PDF in it
    given: Path  # another path to it

    @property
    def path(self) -> Path:
        return self.folder / "file.tla"

    @property
    def path_given(self) -> Path:
        return self.given / "file.tla"


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


@contextmanager
def a_drive_for(folder: Path) -> Iterator[Path]:
    """A drive letter that stands for `folder`, taken away again."""
    if sys.platform != "win32":
        pytest.skip("Windows only")
    taken = os.listdrives()
    for letter in "TUVWXYQRS":
        # Another test may take the letter in between: then `subst` fails.
        if f"{letter}:\\" not in taken and subst(f"{letter}:", str(folder)) == 0:
            break
    else:
        pytest.skip("no drive letter is free")
    try:
        yield Path(f"{letter}:/")
    finally:
        subst(f"{letter}:", "/D")


def subst(*args: str) -> int:
    return subprocess.run(["subst", *args], capture_output=True).returncode


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


@pytest.fixture
def any_media_loads():
    """And no question blocks a test: an unexpected one cancels the save."""
    with (
        patch.object(QtAudioPlayer, "_engine_load_media", return_value=True),
        Serve(Get.PLAYER_CLASS, QtAudioPlayer),
        Serve(Get.FROM_USER_CHOICE, "Cancel"),
    ):
        yield


@pytest.fixture
def folder(qtui, tilia, tls, tmp_path, any_media_loads, use_test_settings) -> Path:
    """WP3's file of every kind, in a folder with its media, its PDF and others."""
    folder = tmp_path / "a folder with a long name"
    folder.mkdir()
    for name in ("rec.mp3", "other.mp3"):
        shutil.copyfile(EXAMPLE_MEDIA_PATH, folder / name)
    for name in ("score.pdf", "other.pdf"):
        shutil.copyfile(RESOURCES / "example.pdf", folder / name)

    def beside_it(doc):
        doc.media_path = str(folder / "rec.mp3")
        first_of_kind(doc, "pdf").attrs["path"] = str(folder / "score.pdf")

    written_by_the_core(EVERY_KIND, folder, beside_it)
    return folder


@contextmanager
def another_path_to(folder: Path, how: str) -> Iterator[Reached]:
    if how == "link":
        link = folder.parent / "deep" / "er" / "link"
        link.parent.mkdir(parents=True)
        link_folder(link, folder)
        yield Reached(folder, link)
    elif how == "drive":
        with a_drive_for(folder) as drive:
            yield Reached(folder, drive)
    elif how == "short name":
        yield Reached(folder, short_name(folder))
    else:
        given = folder.with_name(folder.name.upper())
        if not given.exists():
            pytest.skip("this file system tells letter cases apart")
        yield Reached(folder, given)


@pytest.fixture(params=["link", "drive", "short name", "other letters"])
def reached(request, folder) -> Iterator[Reached]:
    """That folder, by another path too."""
    with another_path_to(folder, request.param) as reached:
        yield reached


@pytest.fixture(params=["link", "drive"])
def linked(request, folder) -> Iterator[Reached]:
    """That folder, by a link to it, or by a drive letter that stands for it."""
    with another_path_to(folder, request.param) as reached:
        yield reached


def stored_in(path: Path) -> tuple[str, str]:
    """The media's path and the PDF's, as the file stores them."""
    content = json.loads(path.read_bytes())
    (pdf,) = [tl for tl in content["timelines"].values() if tl["kind"] == "Pdf"]
    return content["media"]["path"], pdf["path"]


def shown(tilia, tls) -> tuple[str, str]:
    """The media's path and the PDF's, as TiLiA holds them."""
    pdf = first_of_kind(the_document(tilia), "pdf").id
    return get(Get.MEDIA_PATH), tls.get_timeline(pdf).get_data("path")


def rename_a_marker_timeline(tilia, tls) -> str:
    marker = first_of_kind(the_document(tilia), "marker").id
    tls.set_timeline_data(marker, "name", "Renamed")
    record()
    return marker


def by_the_core(path: Path, to: Path, change=None) -> bytes:
    """What a script stores that reads the file at `path`, makes `change` to it, and
    writes it at `to`."""
    doc = tla.read(path)
    if change is not None:
        change(doc)
    tla.write(to, doc)
    return to.read_bytes()


class TestOpenedAndSaved:
    def test_without_an_edit_it_keeps_its_bytes(self, reached):
        before = reached.path.read_bytes()
        assert stored_in(reached.path) == ("rec.mp3", "score.pdf")
        assert open_file(reached.path_given)

        assert save()

        assert reached.path.read_bytes() == before

    def test_its_media_and_its_pdf_are_found_there(self, reached, tilia, tls):
        assert open_file(reached.path_given)

        media, pdf = shown(tilia, tls)
        assert os.path.samefile(media, reached.folder / "rec.mp3")
        assert os.path.samefile(pdf, reached.folder / "score.pdf")

    def test_an_edit_changes_what_it_changes_in_a_script(self, reached, tilia, tls):
        assert open_file(reached.path_given)
        marker = rename_a_marker_timeline(tilia, tls)

        def rename(doc):
            doc.timelines[marker].name = "Renamed"

        expected = by_the_core(reached.path, reached.folder / "script.tla", rename)
        assert save()

        assert reached.path.read_bytes() == expected

    def test_an_edit_undone_gives_back_its_bytes(self, reached, tilia, tls):
        before = reached.path.read_bytes()
        assert open_file(reached.path_given)
        rename_a_marker_timeline(tilia, tls)
        assert save()

        commands.execute("edit.undo")
        assert save()

        assert reached.path.read_bytes() == before

    def test_other_media_and_another_pdf_are_stored_beside_it(
        self, reached, tilia, tls
    ):
        assert open_file(reached.path_given)
        tilia.load_media((reached.given / "other.mp3").as_posix(), scale_timelines="no")
        pdf = first_of_kind(the_document(tilia), "pdf").id
        tls.set_timeline_data(pdf, "path", (reached.given / "other.pdf").as_posix())
        record()

        assert save()

        assert stored_in(reached.path) == ("other.mp3", "other.pdf")

    def test_opened_again_from_recent_files_too(self, reached):
        before = reached.path.read_bytes()
        assert open_file(reached.path_given)
        assert save()

        assert open_file(settings.get_recent_files()[0])
        assert save()

        assert reached.path.read_bytes() == before


class TestSavedAs:
    def test_beside_it_the_paths_stay(self, reached):
        assert open_file(reached.path_given)

        assert save_as(reached.given / "copy.tla")

        assert stored_in(reached.folder / "copy.tla") == ("rec.mp3", "score.pdf")

    def test_elsewhere_they_are_a_script_s(self, reached, tmp_path):
        (tmp_path / "elsewhere").mkdir()
        by_the_core(reached.path_given, tmp_path / "elsewhere" / "script.tla")
        assert open_file(reached.path_given)

        assert save_as(tmp_path / "elsewhere" / "copy.tla")

        assert stored_in(tmp_path / "elsewhere" / "copy.tla") == stored_in(
            tmp_path / "elsewhere" / "script.tla"
        )

    def test_into_the_folder_then_saved_it_keeps_its_bytes(self, reached, tmp_path):
        (tmp_path / "elsewhere").mkdir()
        first = written_by_the_core(reached.path, tmp_path / "elsewhere")
        assert open_file(first)
        copy = reached.given / "copy.tla"
        assert save_as(copy)
        before = (reached.folder / "copy.tla").read_bytes()
        assert (
            stored_in(reached.folder / "copy.tla")[0]
            == json.loads(by_the_core(first, reached.given / "script.tla"))["media"][
                "path"
            ]
        )

        assert save()

        assert (reached.folder / "copy.tla").read_bytes() == before


class TestWhatIsKeptByThePath:
    def test_the_path_is_the_one_given(self, linked, tilia):
        assert open_file(linked.path_given)

        assert Path(get(Get.FILE_PATH)) == linked.path_given
        assert tilia.cur_file_path == linked.path_given
        assert the_document(tilia).origin == linked.path_given

    def test_after_a_save_as_too(self, linked, tilia):
        assert open_file(linked.path_given)

        assert save_as(linked.given / "copy.tla")

        assert Path(get(Get.FILE_PATH)) == linked.given / "copy.tla"
        assert the_document(tilia).origin == linked.given / "copy.tla"

    def test_its_media_and_its_pdf_are_looked_up_from_it(self, linked, tilia, tls):
        assert open_file(linked.path_given)

        assert shown(tilia, tls) == (
            (linked.given / "rec.mp3").as_posix(),
            (linked.given / "score.pdf").as_posix(),
        )

    def test_recent_files_lists_it_so(self, linked):
        assert open_file(linked.path_given)
        assert settings.get_recent_files()[0] == linked.path_given.as_posix()

        assert save_as(linked.given / "copy.tla")

        copy = (linked.given / "copy.tla").as_posix()
        assert settings.get_recent_files()[:2] == [copy, linked.path_given.as_posix()]

    def test_the_zoom_a_save_remembers_is_the_one_used_next(self, linked):
        assert open_file(linked.path_given)
        with Serve(Get.CURRENT_ZOOM, 1.5):
            assert save()

        assert settings.get_file_zoom(linked.path_given) == pytest.approx(1.5)

    def test_a_relative_path_is_from_the_working_folder(
        self, folder, tmp_path, monkeypatch
    ):
        before = (folder / "file.tla").read_bytes()
        monkeypatch.chdir(folder)
        assert open_file("file.tla")
        monkeypatch.chdir(tmp_path)

        assert save()

        assert Path(get(Get.FILE_PATH)).is_absolute()
        assert os.path.samefile(get(Get.FILE_PATH), folder / "file.tla")
        assert os.listdir(tmp_path) == [folder.name]
        assert (folder / "file.tla").read_bytes() == before

    def test_a_save_as_to_a_relative_path_is_too(
        self, folder, tmp_path, monkeypatch, tilia
    ):
        assert open_file(folder / "file.tla")
        (tmp_path / "elsewhere").mkdir()
        monkeypatch.chdir(tmp_path / "elsewhere")
        assert save_as(Path("copy.tla"))
        monkeypatch.chdir(tmp_path)

        assert save()

        assert Path(settings.get_recent_files()[0]).is_absolute()
        assert os.listdir(tmp_path / "elsewhere") == ["copy.tla"]
        assert not (tmp_path / "copy.tla").exists()

    def test_the_place_remembered_for_the_media_is_that_one(self, linked, tilia):
        # Where this document found its media, on this computer (FR-031).
        assert open_file(linked.path_given)

        place = settings.get_media_place(the_document(tilia).document_id, "rec.mp3")
        assert place == (linked.given / "rec.mp3").as_posix()


class TestTheFileOpen:
    """Which file is open doesn't change with the path it is reached by."""

    def test_is_known_by_its_own_path_too(self, reached, tilia):
        assert open_file(reached.path_given)

        assert tilia.file_manager._is_the_file_open(reached.path)
        assert not tilia.file_manager._is_the_file_open(reached.folder / "other.tla")

    def test_changed_by_its_own_path_it_is_asked_about(self, reached, tilia, tls):
        assert open_file(reached.path_given)
        rename_a_marker_timeline(tilia, tls)
        reached.path.write_bytes(reached.path.read_bytes() + b"\n\n")
        doc = tla.read(reached.path)
        doc.metadata["notes"] = "changed elsewhere"
        tla.write(reached.path, doc)
        before = reached.path.read_bytes()

        with Serve(Get.FROM_USER_CHOICE, "Cancel") as asked:
            assert not save()

        assert asked.called
        assert reached.path.read_bytes() == before


class TestALinkToAFile:
    def test_stays_one_and_the_file_it_names_is_saved(self, folder, tmp_path, tilia):
        # The core follows a link to a file: its paths are relative to the folder of
        # the file it names (#431), and that file is the one written.
        path = folder / "file.tla"
        (tmp_path / "links").mkdir()
        link = tmp_path / "links" / "link.tla"
        try:
            link.symlink_to(path)
        except OSError as error:
            pytest.skip(f"no links to files here: {error}")
        before = path.read_bytes()
        assert open_file(link)
        assert get(Get.MEDIA_PATH) == (folder / "rec.mp3").as_posix()

        assert save()

        assert link.is_symlink()
        assert path.read_bytes() == before


class TestAParentAfterALink:
    @pytest.mark.skipif(sys.platform == "win32", reason="Windows reads it by name")
    def test_is_the_one_the_system_reads(self, folder, tmp_path):
        # macOS and Linux go up from the link's target: by name, it would be another
        # file, which a save would write over.
        (folder / "audio").mkdir()
        (tmp_path / "corpus").mkdir()
        link_folder(tmp_path / "corpus" / "audio", folder / "audio")
        other = tmp_path / "corpus" / "file.tla"
        other.write_bytes(b"another file")
        before = (folder / "file.tla").read_bytes()
        assert open_file(f"{tmp_path}/corpus/audio/../file.tla")

        assert save()
        assert save_as(Path(f"{tmp_path}/corpus/audio/../copy.tla"))

        assert other.read_bytes() == b"another file"
        assert (folder / "file.tla").read_bytes() == before
        assert stored_in(folder / "copy.tla") == ("rec.mp3", "score.pdf")


class TestAPathUpOutOfTheFolder:
    """A stored path that goes up out of the linked folder is read by name, as the core
    reads it (WP3's FR-033): found or not, a save keeps it."""

    @pytest.mark.parametrize("how", ["link", "drive"])
    def test_saved_without_an_edit_it_keeps_its_bytes(self, folder, tmp_path, how):
        (tmp_path / "far").mkdir()
        shutil.copyfile(EXAMPLE_MEDIA_PATH, tmp_path / "far" / "rec.mp3")

        def up(doc):
            doc.media_path = str(tmp_path / "far" / "rec.mp3")

        path = written_by_the_core(folder / "file.tla", folder, up)
        assert stored_in(path)[0] == "../far/rec.mp3"
        before = path.read_bytes()
        with another_path_to(folder, how) as reached:
            assert open_file(reached.path_given)
            assert save()

        assert path.read_bytes() == before
