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

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings

from tests import SETTINGS_DIR
from tests.constants import EXAMPLE_MEDIA_DURATION, EXAMPLE_MEDIA_PATH, EXAMPLE_YT_URL
from tests.mock import Serve
from tests.utils import load_local_media
from tilia.media.player import QtAudioPlayer
from tilia.requests import Get, get
from tilia.settings import SettingsManager, settings
from tilia.ui import commands
from tilia_core import tla

FILES = Path(__file__).parents[2] / "packages" / "tilia-core" / "tests" / "tla"
EMPTY = FILES / "golden" / "empty.tla"
DOCUMENT = tla.read(EMPTY).document_id
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
    there, the user picks `look_for`, or declines when it is None. Whether TiLiA
    asked."""
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, look_for is not None) as asked,
        Serve(Get.FROM_USER_MEDIA_PATH, (True, str(look_for))),
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
        place = settings.get_media_place(DOCUMENT)

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
        assert settings.get_media_place(DOCUMENT) is None


class TestAYouTubeLink:
    def test_isnt_remembered_as_a_place(self, qtui, tilia, tls, tmp_path):
        path = tmp_path / "file.tla"
        tla.write(path, media_doc(EXAMPLE_YT_URL))

        # Without starting YouTube's player: only what TiLiA remembers matters.
        with patch("tilia.app.load_media", return_value=(True, tilia.player)) as load:
            assert not open_file(path)

        assert load.call_args.args[1] == EXAMPLE_YT_URL
        assert settings.get_media_place(DOCUMENT) is None


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

    def test_a_redo_gives_back_the_other_media(self, declined, other):
        load_local_media(other)
        undo()

        redo()
        save()

        assert stored_media_path(declined) == "other/other.mp3"


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


class TestRememberedPlaces:
    """`SettingsManager.get_media_place` and `set_media_place` (FR-031)."""

    def test_none_before_one_is_stored(self, a_store):
        assert a_store.get_media_place(DOCUMENT) is None
        assert a_store.get_media_place(DOCUMENT, TIMELINE) is None

    def test_one_per_document_and_one_per_pdf_timeline(self, a_store, tmp_path):
        a_store.set_media_place(DOCUMENT, "C:/music/example.mp3")
        a_store.set_media_place(DOCUMENT, "C:/scores/example.pdf", TIMELINE)
        a_store.set_media_place(OTHER_DOCUMENT, "/home/me/other.mp3")

        store = restarted(a_store, tmp_path)

        assert store.get_media_place(DOCUMENT) == "C:/music/example.mp3"
        assert store.get_media_place(DOCUMENT, TIMELINE) == "C:/scores/example.pdf"
        assert store.get_media_place(OTHER_DOCUMENT) == "/home/me/other.mp3"
        assert store.get_media_place(OTHER_DOCUMENT, TIMELINE) is None

    def test_the_last_one_stored_is_kept(self, a_store):
        a_store.set_media_place(DOCUMENT, "C:/music/example.mp3")
        a_store.set_media_place(DOCUMENT, "D:/music/example.mp3")

        assert a_store.get_media_place(DOCUMENT) == "D:/music/example.mp3"

    def test_their_keys(self, a_store):
        a_store.set_media_place(DOCUMENT, "C:/music/example.mp3")
        a_store.set_media_place(DOCUMENT, "C:/scores/example.pdf", TIMELINE)

        stored = a_store._settings
        assert stored.value(f"media_places/{DOCUMENT}") == "C:/music/example.mp3"
        assert (
            stored.value(f"media_places/{DOCUMENT}/{TIMELINE}")
            == "C:/scores/example.pdf"
        )

    def test_they_arent_among_the_settings_a_person_edits(self, a_store):
        a_store.set_media_place(DOCUMENT, "C:/music/example.mp3")

        assert "media_places" not in a_store.DEFAULT_SETTINGS
        assert "media_places" not in a_store.get_dict()
        a_store.reset_to_default()
        assert a_store.get_media_place(DOCUMENT) == "C:/music/example.mp3"
