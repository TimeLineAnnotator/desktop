"""Finding the media of a `.tla` file (FR-030–FR-032, FR-036; US4, SC-005).

TiLiA looks for the media where the core finds it (`tla.media`), then where this
document last found it on this computer, a place kept in TiLiA's settings, and only
then asks. Wherever the media is found, and when the user declines to look for it,
the file keeps the path it stores; an undo gives it back. Loading other media from
the Media menu changes it.

The remembered places are settings: every test here runs on the test store, never
the user's own (FR-114).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings

from tests import SETTINGS_DIR
from tests.constants import EXAMPLE_MEDIA_DURATION, EXAMPLE_MEDIA_PATH, EXAMPLE_YT_URL
from tests.mock import PatchPost, Serve
from tests.utils import load_local_media, load_youtube_media
from tilia import dirs
from tilia.file import autosave
from tilia.file.open_document import OpenDocument
from tilia.media.player import QtAudioPlayer
from tilia.requests import Get, Post, get, post
from tilia.settings import SettingsManager, settings
from tilia.ui import commands
from tilia_core import tla

FILES = Path(__file__).parents[2] / "packages" / "tilia-core" / "tests" / "tla"
EMPTY = FILES / "golden" / "empty.tla"
EVERY_KIND = FILES / "golden" / "every-kind.tla"
DOCUMENT = tla.read(EMPTY).document_id
# The media path the files here store, unless a test says otherwise.
STORED = "m/example.mp3"
OTHER_DOCUMENT = "019b76da-f000-7000-8000-000000000998"
TIMELINE = "019b76da-f000-7000-8000-000000000999"


@pytest.fixture(autouse=True)
def on_the_test_store(use_test_settings):
    assert Path(settings._settings.fileName()).is_relative_to(SETTINGS_DIR)


@pytest.fixture(autouse=True)
def a_player_that_loads_any_media():
    # The media is never played: only where TiLiA loads it from matters.
    with patch.object(QtAudioPlayer, "_engine_load_media", return_value=True):
        yield


def media_in(folder: Path, name: str = "example.mp3") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    media = folder / name
    media.write_bytes(Path(EXAMPLE_MEDIA_PATH).read_bytes())
    return media


def media_doc(media: Path | str) -> tla.Document:
    """The core's empty file, with `media` as its media, and its length, so that
    loading it asks nothing about scaling."""
    doc = tla.read(EMPTY)
    doc.media_path = str(media)
    doc.media_length = EXAMPLE_MEDIA_DURATION
    return doc


def a_file_with_media(path: Path, media: Path) -> Path:
    """A file at `path` whose media is `media`, which may not be there, as the core
    writes it: relative to the file's folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tla.write(path, media_doc(media))
    return path


def the_core_s_bytes(path: Path, change=None, *, into: Path | None = None) -> bytes:
    """What the core writes for the file at `path`, with `change` made to its
    document, into the folder `into`, or the file's own."""
    doc = tla.read(path)
    if change is not None:
        change(doc)
    other = (into or path.parent) / "by the core.tla"
    tla.write(other, doc)
    return other.read_bytes()


def stored_media_path(path: Path) -> str:
    return json.loads(path.read_bytes())["media"]["path"]


def open_file(path: Path, look_for: Path | None = None) -> bool:
    """Opens `path`, as the File menu does. Asked to look for media that isn't
    there, the user picks `look_for`, or declines when it is None; asked to look for
    a PDF, the user declines. Whether TiLiA asked about the media."""
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, look_for is not None) as asked,
        Serve(Get.FROM_USER_MEDIA_PATH, (True, str(look_for))),
        Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
        Serve(Get.FROM_USER_SHOW_PROBLEMS, None),
    ):
        assert commands.execute("file.open", path)
    return asked.called


def save() -> None:
    assert commands.execute("file.save")


def save_as(path: Path) -> None:
    assert commands.execute("file.save_as", str(path))


def undo() -> None:
    commands.execute("edit.undo")


def redo() -> None:
    commands.execute("edit.redo")


def loaded_media() -> Path:
    return Path(get(Get.MEDIA_PATH))


def the_document(tilia) -> tla.Document:
    return tilia.file_manager.file.document


def moved_alone(path: Path, folder: Path) -> Path:
    """`path`, moved into `folder` without its media."""
    folder.mkdir(parents=True, exist_ok=True)
    return Path(shutil.move(path, folder / path.name))


class TestMovedWithItsMedia:
    """US4, scenario 1; SC-005."""

    def test_loads_it_without_a_question(self, qtui, tilia, tls, tmp_path):
        a_file_with_media(tmp_path / "a" / "file.tla", media_in(tmp_path / "a" / "m"))
        shutil.move(tmp_path / "a", tmp_path / "b")

        assert not open_file(tmp_path / "b" / "file.tla")

        assert loaded_media() == tmp_path / "b" / "m" / "example.mp3"

    def test_saving_changes_nothing(self, qtui, tilia, tls, tmp_path):
        a_file_with_media(tmp_path / "a" / "file.tla", media_in(tmp_path / "a" / "m"))
        shutil.move(tmp_path / "a", tmp_path / "b")
        path = tmp_path / "b" / "file.tla"
        before = path.read_bytes()
        open_file(path)

        save()

        assert path.read_bytes() == before
        assert not tilia.is_file_modified()

    def test_its_own_media_comes_before_the_place_it_was_found(
        self, qtui, tilia, tls, tmp_path
    ):
        # Found once in "a", then the folder copied to "b": "b"'s media loads.
        path = a_file_with_media(
            tmp_path / "a" / "file.tla", media_in(tmp_path / "a" / "m")
        )
        open_file(path)
        shutil.copytree(tmp_path / "a", tmp_path / "b")

        assert not open_file(tmp_path / "b" / "file.tla")

        assert loaded_media() == tmp_path / "b" / "m" / "example.mp3"


class TestMovedAloneAfterItsMediaWasFound:
    """US4, scenario 2; SC-005."""

    @pytest.fixture
    def moved(self, qtui, tilia, tls, tmp_path) -> Path:
        path = a_file_with_media(
            tmp_path / "a" / "file.tla", media_in(tmp_path / "a" / "m")
        )
        assert not open_file(path)
        return moved_alone(path, tmp_path / "c")

    def test_the_place_is_remembered(self, moved, tmp_path):
        place = settings.get_media_place(DOCUMENT, STORED)

        assert Path(place) == tmp_path / "a" / "m" / "example.mp3"

    def test_loads_it_from_there_without_a_question(self, moved, tmp_path):
        assert not open_file(moved)

        assert loaded_media() == tmp_path / "a" / "m" / "example.mp3"

    def test_the_file_isnt_modified(self, moved, tilia):
        open_file(moved)

        assert not tilia.is_file_modified()

    def test_saving_changes_nothing(self, moved, tilia):
        before = moved.read_bytes()
        open_file(moved)

        save()

        assert moved.read_bytes() == before
        assert not tilia.is_file_modified()

    def test_the_place_isnt_tried_once_the_media_is_gone_from_it(self, moved, tmp_path):
        (tmp_path / "a" / "m" / "example.mp3").unlink()

        assert open_file(moved)

    def test_when_its_media_wont_load_there_tilia_asks(self, moved, tilia):
        # A file there that the player can't load: damaged, or a codec it lacks.
        before = moved.read_bytes()
        with patch.object(QtAudioPlayer, "_engine_load_media", return_value=False):
            assert open_file(moved)

        save()

        assert moved.read_bytes() == before

    def test_the_media_picked_then_replaces_the_place(self, moved, tmp_path):
        place = tmp_path / "a" / "m" / "example.mp3"
        picked = media_in(tmp_path / "elsewhere")

        with patch.object(
            QtAudioPlayer,
            "_engine_load_media",
            side_effect=lambda path: Path(path) != place,
        ):
            assert open_file(moved, look_for=picked)

        assert loaded_media() == picked
        assert Path(settings.get_media_place(DOCUMENT, STORED)) == picked


class TestNotFound:
    """US4, scenario 3: TiLiA asks, as today, and the file keeps its path (#409)."""

    @pytest.fixture
    def path(self, qtui, tilia, tls, tmp_path) -> Path:
        # Its media isn't there.
        return a_file_with_media(tmp_path / "file.tla", tmp_path / "m" / "example.mp3")

    def test_asks(self, path, tilia_errors):
        assert open_file(path)

        assert tilia_errors.errors == [
            {
                "title": "Media load error",
                "message": "No media available at 'm/example.mp3'. "
                "Try using another path.",
            }
        ]

    def test_the_media_picked_loads(self, path, tmp_path):
        picked = media_in(tmp_path / "elsewhere")

        assert open_file(path, look_for=picked)

        assert loaded_media() == picked

    def test_the_file_isnt_modified(self, path, tilia, tmp_path):
        open_file(path, look_for=media_in(tmp_path / "elsewhere"))

        assert not tilia.is_file_modified()

    def test_the_file_keeps_its_path(self, path, tilia, tmp_path):
        before = path.read_bytes()
        open_file(path, look_for=media_in(tmp_path / "elsewhere"))

        save()

        assert path.read_bytes() == before
        assert not tilia.is_file_modified()

    def test_the_media_picked_is_found_there_next_time(self, path, tmp_path):
        picked = media_in(tmp_path / "elsewhere")
        open_file(path, look_for=picked)

        assert not open_file(path)

        assert loaded_media() == picked

    def test_declining_changes_nothing(self, path, tilia):
        before = path.read_bytes()
        open_file(path)

        save()

        assert path.read_bytes() == before
        assert not tilia.is_file_modified()
        assert settings.get_media_place(DOCUMENT, STORED) is None


class TestMediaThatWontLoad:
    """Isn't remembered as the place this document found its media."""

    def test_where_the_core_finds_it(self, qtui, tilia, tls, tmp_path):
        path = a_file_with_media(tmp_path / "file.tla", media_in(tmp_path / "m"))

        with patch.object(QtAudioPlayer, "_engine_load_media", return_value=False):
            open_file(path)

        assert settings.get_media_place(DOCUMENT, STORED) is None

    def test_picked_when_asked(self, qtui, tilia, tls, tmp_path):
        path = a_file_with_media(tmp_path / "file.tla", tmp_path / "m" / "example.mp3")
        picked = media_in(tmp_path / "elsewhere")

        with patch.object(QtAudioPlayer, "_engine_load_media", return_value=False):
            assert open_file(path, look_for=picked)

        assert settings.get_media_place(DOCUMENT, STORED) is None

    def test_picked_when_asked_and_not_media(self, qtui, tilia, tls, tmp_path):
        path = a_file_with_media(tmp_path / "file.tla", tmp_path / "m" / "example.mp3")
        picked = tmp_path / "elsewhere" / "notes.txt"
        picked.parent.mkdir()
        picked.write_text("not media", encoding="utf-8")

        assert open_file(path, look_for=picked)

        assert settings.get_media_place(DOCUMENT, STORED) is None


class TestAYouTubeLink:
    def test_isnt_remembered_as_a_place(self, qtui, tilia, tls, tmp_path):
        path = tmp_path / "file.tla"
        tla.write(path, media_doc(EXAMPLE_YT_URL))

        def loads_it(player, url, **_):
            player.media_path = url
            return True, player

        # Without starting YouTube's player: only what TiLiA remembers matters.
        with patch("tilia.app.load_media", side_effect=loads_it) as load:
            assert not open_file(path)
            save()

        assert load.call_args.args[1] == EXAMPLE_YT_URL
        assert get(Get.MEDIA_PATH) == EXAMPLE_YT_URL
        assert settings.get_media_place(DOCUMENT, EXAMPLE_YT_URL) is None


class TestTheMediasDriveGone:
    """A file that stores its media's absolute path, on a drive unplugged since:
    TiLiA asks, and the file keeps its path (FR-032)."""

    def test_asks_and_the_file_keeps_its_path(self, qtui, tilia, tls, tmp_path):
        drive = tmp_path / "usb"
        media = media_in(drive)
        path = tmp_path / "file.tla"
        # Absolute, as a file whose media is on another drive stores it.
        path.write_bytes(tla.canonical_bytes(media_doc(media.as_posix())))
        assert stored_media_path(path) == media.as_posix()
        # Found there once, so it is the place remembered too.
        assert not open_file(path)
        shutil.rmtree(drive)
        # The path as the core writes it for the file unchanged: whether a path
        # read absolute stays so is the core's, as
        # TimeLineAnnotator/project-management#600 has it.
        expected = the_core_s_bytes(path)

        assert open_file(path)
        save()

        assert path.read_bytes() == expected


class TestSaveAsAfterAFoundPlace:
    def test_the_file_s_own_path_follows_the_new_folder(
        self, qtui, tilia, tls, tmp_path
    ):
        path = a_file_with_media(
            tmp_path / "a" / "file.tla", media_in(tmp_path / "a" / "m")
        )
        open_file(path)
        moved = moved_alone(path, tmp_path / "c")
        assert not open_file(moved)  # from the place it was found
        (tmp_path / "c" / "sub").mkdir()
        expected = the_core_s_bytes(moved, into=tmp_path / "c" / "sub")

        save_as(tmp_path / "c" / "sub" / "saved.tla")

        saved = tmp_path / "c" / "sub" / "saved.tla"
        assert saved.read_bytes() == expected
        # The path the file stored, from the new folder: not the place it was found.
        assert stored_media_path(saved) == "../m/example.mp3"


class TestTheMediaMenu:
    """Loading other media from the Media menu changes the file (FR-032)."""

    def test_stores_the_path_tla_as_media_path_gives(self, qtui, tilia, tls, tmp_path):
        path = a_file_with_media(tmp_path / "file.tla", media_in(tmp_path / "m"))
        other = media_in(tmp_path / "other", "other.mp3")
        open_file(path)

        load_local_media(other)

        assert the_document(tilia).media_path == tla.as_media_path(str(other))

    def test_changes_the_file(self, qtui, tilia, tls, tmp_path):
        path = a_file_with_media(tmp_path / "file.tla", media_in(tmp_path / "m"))
        other = media_in(tmp_path / "other", "other.mp3")
        open_file(path)
        load_local_media(other)

        def with_other(doc):
            doc.media_path = tla.as_media_path(str(other))

        expected = the_core_s_bytes(path, with_other)

        save()

        assert path.read_bytes() == expected
        assert stored_media_path(path) == "other/other.mp3"


class TestOtherMediaIsAnUnsavedChange:
    """Loading other media from the Media menu is an unsaved change, as any other,
    whether it is as long as the media the file had or not: closing TiLiA or opening
    another file asks to save it, and an autosave writes it. An undo back to the media
    the file was read with is no change (FR-021, FR-032;
    TimeLineAnnotator/project-management#638)."""

    # take1 is the media the file stores; take2 is as long, take3 is longer.
    LENGTHS = {"take1.mp3": 180.0, "take2.mp3": 180.0, "take3.mp3": 200.0}

    @pytest.fixture(autouse=True)
    def a_player_that_reports_their_lengths(self):
        def load(player, media_path):
            # As Qt's player does, once the media has loaded.
            player.on_media_duration_available(self.LENGTHS[Path(media_path).name])
            return True

        with patch.object(QtAudioPlayer, "_engine_load_media", load):
            yield

    @pytest.fixture
    def piece(self, qtui, tilia, tls, tmp_path) -> Path:
        """piece.tla, open, which stores take1.mp3, beside it, 3:00 long."""
        for name in self.LENGTHS:
            media_in(tmp_path, name)
        doc = media_doc(tmp_path / "take1.mp3")
        doc.media_length = self.LENGTHS["take1.mp3"]
        path = tmp_path / "piece.tla"
        tla.write(path, doc)
        assert not open_file(path)
        assert not tilia.is_file_modified()
        return path

    def test_closing_tilia_asks_to_save_it(self, piece, tmp_path):
        load_local_media(tmp_path / "take2.mp3")

        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)) as asked,
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            commands.execute("tilia.close")

        assert asked.called
        exit_mock.assert_called()
        assert stored_media_path(piece) == "take2.mp3"

    def test_a_new_file_asks_to_save_it(self, piece, tmp_path):
        load_local_media(tmp_path / "take2.mp3")

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)) as asked:
            commands.execute("file.new")

        assert asked.called
        assert stored_media_path(piece) == "take2.mp3"

    @pytest.mark.parametrize(
        "take", ["take2.mp3", "take3.mp3"], ids=["as long", "longer"]
    )
    def test_reads_as_modified_until_undone(self, piece, tilia, tmp_path, take):
        load_local_media(tmp_path / take)

        assert tilia.is_file_modified()
        undo()
        assert loaded_media() == tmp_path / "take1.mp3"
        assert not tilia.is_file_modified()
        redo()
        assert tilia.is_file_modified()

    def test_a_youtube_link_is_one_before_its_length_is_known(self, piece, tilia):
        def loads_it(player, url, **_):
            # What YouTube's player does at once: its length comes later, if at all.
            player.on_media_load_done(url, 0.0, 0.0)
            return True, player

        with patch("tilia.app.load_media", side_effect=loads_it):
            load_youtube_media(EXAMPLE_YT_URL)

        assert get(Get.MEDIA_PATH) == EXAMPLE_YT_URL
        assert tilia.is_file_modified()
        undo()
        assert not tilia.is_file_modified()

    def test_an_undo_once_it_is_saved_is_a_change(self, piece, tilia, tmp_path):
        load_local_media(tmp_path / "take2.mp3")
        save()
        assert not tilia.is_file_modified()

        undo()

        assert tilia.is_file_modified()

    @pytest.mark.parametrize("stored", ["", "m/gone.mp3"], ids=["none", "not found"])
    def test_an_undo_back_to_no_media_is_no_change(
        self, qtui, tilia, tls, tmp_path, stored
    ):
        # The file stores no media, or the user declined to look for what it stores.
        path = tmp_path / "file.tla"
        tla.write(path, media_doc(stored and tmp_path / stored))
        open_file(path)
        load_local_media(media_in(tmp_path, "take1.mp3"))
        assert tilia.is_file_modified()

        undo()

        assert get(Get.MEDIA_PATH) == ""
        assert not tilia.is_file_modified()

    def test_an_undo_back_to_media_found_elsewhere_is_no_change(
        self, piece, tilia, tmp_path
    ):
        # The file moved alone: its media is where it was last found.
        assert not open_file(moved_alone(piece, tmp_path / "c"))
        load_local_media(tmp_path / "take2.mp3")
        assert tilia.is_file_modified()

        undo()

        assert loaded_media() == tmp_path / "take1.mp3"
        assert not tilia.is_file_modified()

    def test_the_same_media_again_is_no_change(self, piece, tilia, tmp_path):
        # Spelt as the Media menu's dialog gives it.
        load_local_media((tmp_path / "take1.mp3").as_posix())

        assert not tilia.is_file_modified()

    def test_opening_another_file_asks_and_autosaves_it_first(self, piece, tmp_path):
        load_local_media(tmp_path / "take2.mp3")
        other = tmp_path / "other.tla"
        tla.write(other, tla.read(EMPTY))

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)) as asked:
            assert commands.execute("file.open", other)

        assert asked.called
        assert stored_media_path(piece) == "take1.mp3"
        # Not saved, it is kept in an autosave (FR-012).
        [autosaved] = Path(dirs.autosaves_path).iterdir()
        found = tla.media(autosaved, tla.read(autosaved)).path
        assert found == tmp_path / "take2.mp3"

    def test_is_autosaved(self, piece, tilia, tmp_path):
        with patch.object(autosave.settings, "get", return_value=0):
            # No thread: autosaves are made here.
            saver = autosave.AutoSaver(
                tilia.get_app_state,
                lambda: tilia.file_manager.file.copy_for_writing(),
            )
        (tmp_path / "autosaves").mkdir()
        written = iter(tmp_path / "autosaves" / name for name in ("1.tla", "2.tla"))
        with (
            patch.object(
                autosave, "get_autosave_path", side_effect=lambda: next(written)
            ),
            patch.object(autosave, "make_room_for_new_autosave"),
        ):
            saver.auto_save_once()
            assert not saver.needs_auto_save()
            load_local_media(tmp_path / "take2.mp3")

            assert saver.needs_auto_save()
            saver.auto_save_once()

        saved = tmp_path / "autosaves" / "2.tla"
        assert tla.media(saved, tla.read(saved)).path == tmp_path / "take2.mp3"


def link_folder(link: Path, folder: Path) -> None:
    """Makes `link` a link to `folder`, or a junction where Windows makes no link
    for this user."""
    try:
        link.symlink_to(folder, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import _winapi

        _winapi.CreateJunction(str(folder), str(link))


def load_a_link(url: str) -> None:
    """Loads a YouTube link from the menu, without starting YouTube's player."""

    def loads_it(player, url, **_):
        player.on_media_load_done(url, 0.0, 0.0)
        return True, player

    with patch("tilia.app.load_media", side_effect=loads_it):
        load_youtube_media(url)


def close_saving() -> bool:
    """Closes TiLiA, saving if it asks. Whether it asked."""
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)) as asked,
        PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
    ):
        commands.execute("tilia.close")
    exit_mock.assert_called()
    return asked.called


class TestMediaFoundElsewhereThenPicked:
    """Media picked from File > Load media becomes the file's, also when it is the
    media TiLiA had found elsewhere: the place it remembers, or the one the user
    picked when asked (TimeLineAnnotator/project-management#688, a). An unsaved
    change, as any other (FR-021, FR-032)."""

    # The place, as the file then stores it.
    ITS_PLACE = "../a/m/example.mp3"

    @pytest.fixture(params=["remembered", "picked when asked"])
    def path(self, request, qtui, tilia, tls, tmp_path) -> Path:
        """c/file.tla, open, which stores m/example.mp3: its media isn't there, and
        TiLiA found it in a/m/."""
        if request.param == "remembered":
            path = a_file_with_media(
                tmp_path / "a" / "file.tla", media_in(tmp_path / "a" / "m")
            )
            assert not open_file(path)
            path = moved_alone(path, tmp_path / "c")
            assert not open_file(path)
        else:
            path = a_file_with_media(
                tmp_path / "c" / "file.tla", tmp_path / "c" / "m" / "example.mp3"
            )
            # Spelt as the dialog gives it.
            assert open_file(path, media_in(tmp_path / "a" / "m").as_posix())
        assert loaded_media() == tmp_path / "a" / "m" / "example.mp3"
        assert stored_media_path(path) == STORED
        assert not tilia.is_file_modified()
        return path

    @pytest.fixture
    def place(self, path, tmp_path) -> str:
        """Where TiLiA found the media, as the menu's dialog spells it."""
        return (tmp_path / "a" / "m" / "example.mp3").as_posix()

    @pytest.fixture
    def other(self, tmp_path) -> str:
        return media_in(tmp_path / "o", "other.mp3").as_posix()

    def test_it_becomes_the_files(self, path, place, tilia):
        load_local_media(place)

        assert tilia.is_file_modified()
        save()
        assert stored_media_path(path) == self.ITS_PLACE
        assert not tilia.is_file_modified()
        # The core finds it there.
        assert tla.media(path, tla.read(path)).path == Path(place)

    def test_by_way_of_other_media_too(self, path, place, other, tilia):
        load_local_media(other)
        load_local_media(place)

        assert tilia.is_file_modified()
        save()
        assert stored_media_path(path) == self.ITS_PLACE
        assert not tilia.is_file_modified()

    def test_spelt_otherwise_too(self, path, place, tilia):
        load_local_media(place.replace("/a/m/", "/a/x/../m/"))

        assert tilia.is_file_modified()
        save()
        assert stored_media_path(path) == self.ITS_PLACE

    def test_by_way_of_a_youtube_link_too(self, path, place, tilia):
        load_a_link(EXAMPLE_YT_URL)
        load_local_media(place)

        assert tilia.is_file_modified()
        save()
        assert stored_media_path(path) == self.ITS_PLACE

    def test_closing_tilia_asks_to_save_it(self, path, place):
        load_local_media(place)

        assert close_saving()

        assert stored_media_path(path) == self.ITS_PLACE

    def test_until_then_nothing_is_asked(self, path):
        assert not close_saving()

        assert stored_media_path(path) == STORED

    def test_an_undo_gives_the_files_path_back(self, path, place, tilia):
        before = path.read_bytes()
        load_local_media(place)

        undo()

        assert not tilia.is_file_modified()
        redo()
        assert tilia.is_file_modified()
        undo()
        save()
        assert path.read_bytes() == before

    def test_an_undo_once_it_is_saved_is_a_change(self, path, place, tilia):
        before = path.read_bytes()
        load_local_media(place)
        save()
        saved = path.read_bytes()

        undo()

        assert tilia.is_file_modified()
        redo()
        assert not tilia.is_file_modified()
        save()
        assert path.read_bytes() == saved
        undo()
        save()
        assert path.read_bytes() == before
        assert not tilia.is_file_modified()

    def test_an_undo_of_other_media_goes_back_to_it(self, path, place, other, tilia):
        load_local_media(place)
        save()
        saved = path.read_bytes()
        load_local_media(other)
        assert tilia.is_file_modified()

        undo()

        assert not tilia.is_file_modified()
        save()
        assert path.read_bytes() == saved

    def test_a_save_as_stores_it_from_the_new_folder(
        self, path, place, tilia, tmp_path
    ):
        load_local_media(place)
        saved = tmp_path / "c" / "sub" / "saved.tla"
        saved.parent.mkdir()

        save_as(saved)

        assert stored_media_path(saved) == "../../a/m/example.mp3"
        assert not tilia.is_file_modified()
        assert stored_media_path(path) == STORED

    def test_opening_another_file_autosaves_it_first(self, path, place, tmp_path):
        load_local_media(place)
        another = tmp_path / "another.tla"
        tla.write(another, tla.read(EMPTY))

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)) as asked:
            assert commands.execute("file.open", another)

        assert asked.called
        assert stored_media_path(path) == STORED
        [autosaved] = Path(dirs.autosaves_path).iterdir()
        assert tla.media(autosaved, tla.read(autosaved)).path == Path(place)

    def test_is_autosaved(self, path, place, tilia, tmp_path):
        with patch.object(autosave.settings, "get", return_value=0):
            # No thread: autosaves are made here.
            saver = autosave.AutoSaver(
                tilia.get_app_state,
                lambda: tilia.file_manager.file.copy_for_writing(),
            )
        (tmp_path / "autosaves").mkdir()
        written = iter(tmp_path / "autosaves" / f"{n}.tla" for n in (1, 2, 3))
        with (
            patch.object(
                autosave, "get_autosave_path", side_effect=lambda: next(written)
            ),
            patch.object(autosave, "make_room_for_new_autosave"),
        ):
            saver.auto_save_once()
            assert not saver.needs_auto_save()
            load_local_media(place)
            assert saver.needs_auto_save()
            saver.auto_save_once()
            assert not saver.needs_auto_save()
            # A save stores the place otherwise, and changes nothing.
            save()
            assert not saver.needs_auto_save()
            undo()
            assert saver.needs_auto_save()
            saver.auto_save_once()

        picked, undone = (tmp_path / "autosaves" / f"{n}.tla" for n in (2, 3))
        assert tla.media(picked, tla.read(picked)).path == Path(place)
        # Its path as the file stores it, which names nothing.
        assert tla.media(undone, tla.read(undone)).path is None


class TestMediaWhereTheFileSaysPicked:
    """Picking the media that is where the file says changes nothing, however the
    file and the menu spell it, and by way of other media too
    (TimeLineAnnotator/project-management#688, a)."""

    STORED_AS = {
        "relative": "m/example.mp3",
        "with a dot": "./m/example.mp3",
        "with ..": "m/../m/example.mp3",
        "with two slashes": "m//example.mp3",
        "absolute": "{folder}/m/example.mp3",
        "absolute with ..": "{folder}/m/../m/example.mp3",
    }

    @staticmethod
    def spellings(media: Path) -> dict[str, str]:
        spelt, folder = media.as_posix(), media.parent.as_posix()
        spellings = {
            "as the dialog gives it": spelt,
            "the system's": str(media),
            "with ..": f"{folder}/x/../{media.name}",
            "with a dot": f"{folder}/./{media.name}",
            "with two slashes": f"{folder}//{media.name}",
            "relative": os.path.relpath(media),
        }
        if os.name == "nt":
            spellings["another drive letter case"] = spelt[0].swapcase() + spelt[1:]
        capitals = media.with_name(media.name.upper())
        if capitals.is_file():  # on Windows, and as a rule on macOS
            spellings["capitals"] = capitals.as_posix()
        return spellings

    @pytest.fixture(params=STORED_AS)
    def path(self, request, qtui, tilia, tls, tmp_path, monkeypatch) -> Path:
        """file.tla, open, with its media, in m/, stored as the spelling says."""
        monkeypatch.chdir(tmp_path)  # so that a relative path can name the media
        media_in(tmp_path / "m")
        stored = self.STORED_AS[request.param].format(folder=tmp_path.as_posix())
        path = tmp_path / "file.tla"
        path.write_bytes(tla.canonical_bytes(media_doc(stored)))
        assert stored_media_path(path) == stored
        assert not open_file(path)
        return path

    def test_is_no_change(self, path, tilia, tmp_path):
        before = path.read_bytes()
        media = tmp_path / "m" / "example.mp3"

        for name, spelt in self.spellings(media).items():
            load_local_media(spelt)

            assert not tilia.is_file_modified(), name
            save()
            assert path.read_bytes() == before, name

    def test_by_way_of_other_media_is_none_either(self, path, tilia, tmp_path):
        before = path.read_bytes()
        media = tmp_path / "m" / "example.mp3"
        other = media_in(tmp_path / "o", "other.mp3").as_posix()

        for name, spelt in self.spellings(media).items():
            load_local_media(other)
            assert tilia.is_file_modified(), name
            load_local_media(spelt)

            assert not tilia.is_file_modified(), name
            save()
            assert path.read_bytes() == before, name

    def test_once_other_media_was_saved_is_a_change(self, path, tilia, tmp_path):
        load_local_media(media_in(tmp_path / "o", "other.mp3").as_posix())
        save()
        assert stored_media_path(path) == "o/other.mp3"

        load_local_media((tmp_path / "m" / "example.mp3").as_posix())

        assert tilia.is_file_modified()
        save()
        assert tla.media(path, tla.read(path)).path == tmp_path / "m" / "example.mp3"
        assert not tilia.is_file_modified()

    def test_through_a_linked_folder_is_none_either(self, qtui, tilia, tls, tmp_path):
        # Opened through the link, its paths are from the linked folder, where the
        # media picked isn't: but a save stores the path the file has.
        real, link = tmp_path / "real", tmp_path / "link"
        media = media_in(real / "m")
        path = a_file_with_media(real / "file.tla", media)
        link_folder(link, real)
        before = path.read_bytes()
        assert not open_file(link / "file.tla")

        for picked in (media, link / "m" / media.name):
            load_local_media(media_in(tmp_path / "o", "other.mp3").as_posix())
            assert tilia.is_file_modified()
            load_local_media(picked.as_posix())

            assert not tilia.is_file_modified()
        load_local_media(media.as_posix())
        save()
        assert path.read_bytes() == before

    def test_in_capitals_is_none_either_where_they_are_ignored(
        self, qtui, tilia, tls, tmp_path
    ):
        # By the file system alone, as on macOS, whose normcase keeps them.
        media = media_in(tmp_path / "m")
        capitals = media.with_name(media.name.upper())
        if not capitals.is_file():
            pytest.skip("the file system tells capitals apart")
        path = a_file_with_media(tmp_path / "file.tla", media)
        before = path.read_bytes()
        assert not open_file(path)

        with patch.object(os.path, "normcase", lambda path: path):
            load_local_media(capitals.as_posix())

            assert not tilia.is_file_modified()
        save()
        assert path.read_bytes() == before

    def test_found_elsewhere_in_the_meantime_is_none_either(
        self, qtui, tilia, tls, tmp_path
    ):
        # The media came back to where the file says, while TiLiA plays the copy it
        # found elsewhere.
        path = a_file_with_media(tmp_path / "file.tla", tmp_path / "m" / "example.mp3")
        before = path.read_bytes()
        assert open_file(path, media_in(tmp_path / "a").as_posix())

        load_local_media(media_in(tmp_path / "m").as_posix())

        assert not tilia.is_file_modified()
        save()
        assert path.read_bytes() == before


class TestAYouTubeLinkPicked:
    LINK = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    OTHER_LINK = "https://www.youtube.com/watch?v=bbbbbbbbbbb"

    @pytest.fixture
    def path(self, qtui, tilia, tls, tmp_path) -> Path:
        """A file, open, whose media is a link."""
        path = tmp_path / "file.tla"
        tla.write(path, media_doc(self.LINK))

        def loads_it(player, url, **_):
            player.on_media_load_done(url, 0.0, 0.0)
            return True, player

        with patch("tilia.app.load_media", side_effect=loads_it):
            assert not open_file(path)
        assert not tilia.is_file_modified()
        return path

    @pytest.mark.parametrize("start", ["https://", ""])
    def test_the_files_own_is_no_change(self, path, tilia, start):
        # Without its scheme, as it can be typed, it is stored with it.
        before = path.read_bytes()

        load_a_link(self.LINK.replace("https://", start))

        assert not tilia.is_file_modified()
        save()
        assert path.read_bytes() == before

    def test_another_is_one_until_undone(self, path, tilia):
        load_a_link(self.OTHER_LINK)

        assert tilia.is_file_modified()
        load_a_link(self.LINK)
        assert not tilia.is_file_modified()
        load_a_link(self.OTHER_LINK)
        save()
        assert stored_media_path(path) == self.OTHER_LINK
        assert not tilia.is_file_modified()


class TestMediaTheDocumentDoesntFollowYet:
    def test_reads_as_what_a_save_would_store(self, qtui, tilia, tls, tmp_path):
        # A video that won't load takes the audio's player away, so TiLiA has no
        # media, and nothing was recorded: a save would store none.
        path = a_file_with_media(tmp_path / "file.tla", media_in(tmp_path / "m"))
        assert not open_file(path)

        # Another player of the same class stands for the video's.
        with (
            Serve(Get.PLAYER_CLASS, QtAudioPlayer),
            patch.object(QtAudioPlayer, "_engine_load_media", return_value=False),
        ):
            load_local_media((tmp_path / "broken.mp4").as_posix())

        assert get(Get.MEDIA_PATH) == ""
        assert tilia.is_file_modified()


class TestMediaPickedInANewFile:
    def test_is_an_unsaved_change_until_undone(self, qtui, tilia, tls, tmp_path):
        commands.execute("file.new")
        assert not tilia.is_file_modified()

        load_local_media(media_in(tmp_path).as_posix())

        assert tilia.is_file_modified()
        undo()
        assert not tilia.is_file_modified()
        redo()
        assert tilia.is_file_modified()
        save_as(tmp_path / "new.tla")
        assert stored_media_path(tmp_path / "new.tla") == "example.mp3"
        assert not tilia.is_file_modified()


class TestAPlacePerStoredPath:
    """The place is kept per document id and stored path, and a save remembers the
    media TiLiA has loaded (TimeLineAnnotator/project-management#627, c, and #637,
    point 1, c)."""

    def test_a_template_s_copies_each_open_with_their_own(
        self, qtui, tilia, tls, tmp_path
    ):
        # piece2 is a Save As of piece1, so they share a document id.
        take1 = media_in(tmp_path / "p1", "take1.mp3")
        piece1 = a_file_with_media(tmp_path / "p1" / "piece1.tla", take1)
        assert not open_file(piece1)
        take2 = media_in(tmp_path / "p2", "take2.mp3")
        piece2 = tmp_path / "p2" / "piece2.tla"
        save_as(piece2)
        load_local_media(take2)
        save()
        assert tla.read(piece2).document_id == tla.read(piece1).document_id
        assert not open_file(piece2)
        piece1 = moved_alone(piece1, tmp_path / "elsewhere1")
        piece2 = moved_alone(piece2, tmp_path / "elsewhere2")

        assert not open_file(piece1)
        assert loaded_media() == take1
        assert not open_file(piece2)
        assert loaded_media() == take2

    @pytest.fixture
    def opened(self, qtui, tilia, tls, tmp_path) -> Path:
        """A file, open, whose media the core found beside it."""
        path = a_file_with_media(
            tmp_path / "a" / "file.tla", media_in(tmp_path / "a" / "m")
        )
        assert not open_file(path)
        return path

    @pytest.fixture
    def other(self, tmp_path) -> Path:
        """Other media beside the file, which it would store as `o/other.mp3`."""
        return media_in(tmp_path / "a" / "o", "other.mp3")

    def test_the_media_menu_then_a_save(self, opened, other, tmp_path):
        load_local_media(other)

        save()

        assert stored_media_path(opened) == "o/other.mp3"
        assert Path(settings.get_media_place(DOCUMENT, "o/other.mp3")) == other
        assert not open_file(moved_alone(opened, tmp_path / "c"))
        assert loaded_media() == other

    def test_the_media_menu_without_a_save(self, opened, other, tmp_path):
        load_local_media(other)

        # Opening another file without saving this one.
        assert not open_file(moved_alone(opened, tmp_path / "c"))

        assert loaded_media() == tmp_path / "a" / "m" / "example.mp3"
        assert settings.get_media_place(DOCUMENT, "o/other.mp3") is None

    def test_the_media_menu_then_an_undo_then_a_save(self, opened, other, tmp_path):
        load_local_media(other)
        undo()

        save()

        assert stored_media_path(opened) == STORED
        assert settings.get_media_place(DOCUMENT, "o/other.mp3") is None
        assert not open_file(moved_alone(opened, tmp_path / "c"))
        assert loaded_media() == tmp_path / "a" / "m" / "example.mp3"


class TestAnUndoOfOtherMedia:
    """An undo back to the media the file stores gives the file its path back, though
    TiLiA's state holds where it was found, or nothing when the user declined to look
    (from the review of TimeLineAnnotator/desktop#904)."""

    @pytest.fixture
    def declined(self, qtui, tilia, tls, tmp_path) -> Path:
        """A file whose media isn't there, open, the user having declined to look for
        it."""
        path = a_file_with_media(tmp_path / "file.tla", tmp_path / "m" / "example.mp3")
        assert open_file(path)
        return path

    @pytest.fixture
    def other(self, tmp_path) -> Path:
        return media_in(tmp_path / "other", "other.mp3")

    def test_after_declining_to_look(self, declined, other):
        before = declined.read_bytes()
        load_local_media(other)

        undo()
        save()

        assert declined.read_bytes() == before

    def test_after_finding_it_elsewhere(self, qtui, tilia, tls, tmp_path, other):
        path = a_file_with_media(
            tmp_path / "a" / "file.tla", media_in(tmp_path / "a" / "m")
        )
        open_file(path)
        moved = moved_alone(path, tmp_path / "c")
        before = moved.read_bytes()
        assert not open_file(moved)
        load_local_media(other)

        undo()
        save()

        assert moved.read_bytes() == before

    def test_with_a_save_in_between(self, declined, other):
        before = declined.read_bytes()
        load_local_media(other)
        save()

        undo()
        save()

        assert declined.read_bytes() == before

    def test_after_a_save_as_names_the_media_from_the_new_folder(
        self, declined, other, tmp_path
    ):
        (tmp_path / "sub").mkdir()
        expected = the_core_s_bytes(declined, into=tmp_path / "sub")
        load_local_media(other)
        save_as(tmp_path / "sub" / "saved.tla")

        undo()
        save()

        saved = tmp_path / "sub" / "saved.tla"
        assert saved.read_bytes() == expected
        assert stored_media_path(saved) == "../m/example.mp3"

    def test_after_a_save_as_through_a_link_names_the_media_from_its_target(
        self, declined, other, tmp_path
    ):
        # The core writes the file the link names, with paths from that file's
        # folder, which is at another depth than the link's.
        (tmp_path / "store").mkdir()
        target = tmp_path / "store" / "saved.tla"
        link = tmp_path / "links" / "deeper" / "saved.tla"
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(target)
        except OSError as error:
            pytest.skip(f"can't make a symbolic link here: {error}")
        expected = the_core_s_bytes(declined, into=tmp_path / "store")
        load_local_media(other)
        save_as(link)

        undo()
        save()

        assert target.read_bytes() == expected
        assert stored_media_path(target) == "../m/example.mp3"

    @pytest.mark.parametrize("saved_between", [False, True], ids=["", "saved between"])
    def test_of_an_absolute_path_not_on_this_computer(
        self, qtui, tilia, tls, tmp_path, other, saved_between
    ):
        # A file with timelines, whose media someone else keeps at an absolute path.
        doc = tla.read(EVERY_KIND)
        doc.media_path = (Path(tmp_path.anchor) / "someone" / "x.mp3").as_posix()
        path = tmp_path / "proj" / "file.tla"
        path.parent.mkdir()
        path.write_bytes(tla.canonical_bytes(doc))
        # As the core writes it for the file unchanged: whether a path read
        # absolute stays so is the core's, as
        # TimeLineAnnotator/project-management#600 has it.
        expected = json.loads(the_core_s_bytes(path))["media"]
        assert open_file(path)
        post(Post.APP_MEDIA_LOAD, other.as_posix(), scale_timelines="no")
        if saved_between:
            save()

        # Back to no media, TiLiA asks whether to scale the timelines; the undo
        # restores them whatever the answer.
        with Serve(Get.FROM_USER_YES_OR_NO, False):
            undo()
        save()

        assert json.loads(path.read_bytes())["media"] == expected

    def test_a_redo_gives_back_the_other_media(self, declined, other):
        load_local_media(other)
        undo()

        redo()
        save()

        assert stored_media_path(declined) == "other/other.mp3"


class TestNoteMediaFound:
    def test_the_path_found_is_no_change(self):
        doc = media_doc("m/example.mp3")
        opened = OpenDocument(document=doc)
        state = {"media_metadata": {}, "media_path": "", "timelines": {}}
        opened.synced = state

        opened.note_media_found("C:/found/example.mp3")
        opened.sync({**state, "media_path": "C:/found/example.mp3"})

        assert doc.media_path == "m/example.mp3"
        assert opened.media_path == "C:/found/example.mp3"

    def test_other_media_is_a_change(self):
        doc = media_doc("m/example.mp3")
        opened = OpenDocument(document=doc)
        state = {"media_metadata": {}, "media_path": "", "timelines": {}}
        opened.synced = state

        opened.note_media_found("C:/found/example.mp3")
        opened.sync({**state, "media_path": "C:/other/other.mp3"})

        assert doc.media_path == tla.as_media_path("C:/other/other.mp3")


@pytest.fixture
def a_store(tmp_path) -> SettingsManager:
    """Settings of their own, in a file in the test's folder."""
    return SettingsManager(
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    )


def restarted(store: SettingsManager, tmp_path: Path) -> SettingsManager:
    """The same settings, as TiLiA reads them when it starts again. Qt keeps an INI
    file this process wrote in memory: a copy is read from disk."""
    store._settings.sync()
    copy = tmp_path / "restarted.ini"
    shutil.copy(tmp_path / "settings.ini", copy)
    return SettingsManager(QSettings(str(copy), QSettings.Format.IniFormat))


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TestRememberedPlaces:
    """`SettingsManager.get_media_place` and `set_media_place`: per document id and
    stored path (FR-031; TimeLineAnnotator/project-management#637)."""

    def test_none_before_one_is_stored(self, a_store):
        assert a_store.get_media_place(DOCUMENT, "take1.mp3") is None
        assert a_store.get_media_place(DOCUMENT, "score.pdf", TIMELINE) is None

    def test_one_per_document_stored_path_and_pdf_timeline(self, a_store, tmp_path):
        a_store.set_media_place(DOCUMENT, "take1.mp3", "C:/music/take1.mp3")
        a_store.set_media_place(DOCUMENT, "take2.mp3", "C:/music/take2.mp3")
        a_store.set_media_place(
            DOCUMENT, "score.pdf", "C:/scores/score.pdf", timeline_id=TIMELINE
        )
        a_store.set_media_place(OTHER_DOCUMENT, "take1.mp3", "/home/me/take1.mp3")

        store = restarted(a_store, tmp_path)

        assert store.get_media_place(DOCUMENT, "take1.mp3") == "C:/music/take1.mp3"
        assert store.get_media_place(DOCUMENT, "take2.mp3") == "C:/music/take2.mp3"
        assert (
            store.get_media_place(DOCUMENT, "score.pdf", TIMELINE)
            == "C:/scores/score.pdf"
        )
        assert store.get_media_place(DOCUMENT, "score.pdf") is None
        assert store.get_media_place(OTHER_DOCUMENT, "take1.mp3") == (
            "/home/me/take1.mp3"
        )
        assert store.get_media_place(OTHER_DOCUMENT, "take2.mp3") is None

    @pytest.mark.parametrize(
        "other", ["Take1.mp3", "audio/take1.mp3", "audio\\take1.mp3", "take1.mp3 "]
    )
    def test_a_stored_path_spelt_otherwise_is_another(self, a_store, other):
        a_store.set_media_place(DOCUMENT, "take1.mp3", "C:/music/take1.mp3")

        assert a_store.get_media_place(DOCUMENT, other) is None

    def test_the_last_one_stored_is_kept(self, a_store):
        a_store.set_media_place(DOCUMENT, "take1.mp3", "C:/music/take1.mp3")
        a_store.set_media_place(DOCUMENT, "take1.mp3", "D:/music/take1.mp3")

        assert a_store.get_media_place(DOCUMENT, "take1.mp3") == "D:/music/take1.mp3"

    def test_their_keys(self, a_store):
        a_store.set_media_place(DOCUMENT, "audio/take1.mp3", "C:/music/take1.mp3")
        a_store.set_media_place(DOCUMENT, "score.pdf", "C:/score.pdf", TIMELINE)

        stored = a_store._settings
        assert (
            stored.value(f"media_places/{DOCUMENT}/{sha256('audio/take1.mp3')}")
            == "C:/music/take1.mp3"
        )
        assert (
            stored.value(f"media_places/{DOCUMENT}/{TIMELINE}/{sha256('score.pdf')}")
            == "C:/score.pdf"
        )

    def test_they_arent_among_the_settings_a_person_edits(self, a_store):
        a_store.set_media_place(DOCUMENT, "take1.mp3", "C:/music/take1.mp3")

        assert "media_places" not in a_store.DEFAULT_SETTINGS
        assert "media_places" not in a_store.get_dict()
        a_store.reset_to_default()
        assert a_store.get_media_place(DOCUMENT, "take1.mp3") == "C:/music/take1.mp3"
