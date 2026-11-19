"""The media's length, and YouTube links (FR-033–FR-035; user story 4, scenarios 4–6;
SC-006).

A YouTube player reports the media's length once its page has loaded, often a little
off the stored one. Within `DURATION_JITTER_TOLERANCE` of it, the file keeps its own,
so that opening and saving changes nothing; beyond it, TiLiA asks to scale or crop, as
before, and stores the new one. A file without a length takes the one reported. The
players here are stand-ins: they load nothing, and report what a test tells them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.mock import Serve
from tests.utils import load_youtube_media
from tilia.constants import DURATION_JITTER_TOLERANCE
from tilia.media.player.base import Player
from tilia.requests import Get, get
from tilia.ui import commands
from tilia_core import tla

FILES = Path(__file__).parents[2] / "packages" / "tilia-core" / "tests" / "tla"
EVERY_KIND = FILES / "golden" / "every-kind.tla"
LINK = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
# every-kind.tla's: a hierarchy and a range end there, and markers are at 16 s, so
# that a crop to a shorter length would change them.
STORED = 17.5


class _Player(Player):
    """A player that loads nothing. `report` is the player reporting a length."""

    def report(self, length: float) -> None:
        self.on_media_duration_available(length)

    def _engine_load_media(self, media_path: str) -> bool:
        return True

    def _engine_get_media_duration(self) -> float:
        return self.duration

    def _engine_get_current_time(self) -> float:
        return self.current_time

    def _engine_pause(self) -> None:
        pass

    def _engine_unpause(self) -> None:
        pass

    def _engine_stop(self) -> None:
        pass

    def _engine_seek(self, time: float) -> None:
        pass

    def _engine_unload_media(self) -> None:
        pass

    def _engine_play(self) -> None:
        pass

    def _engine_exit(self) -> None:
        pass

    def _engine_set_volume(self, volume: int) -> None:
        pass

    def _engine_set_mute(self, is_muted: bool) -> None:
        pass

    def _engine_try_playback_rate(self, playback_rate: float) -> None:
        pass

    def _engine_set_playback_rate(self, playback_rate: float) -> None:
        pass

    def _engine_loop(self, is_looping: bool) -> None:
        pass


class _YouTube(_Player):
    """TiLiA's YouTube player: it reports the length the file gives it at once, then,
    once its page has loaded, its own (`report`). Offline, it reports no other."""

    MEDIA_TYPE = "youtube"

    def load_media(
        self,
        path: str | Path,
        start: float = 0.0,
        end: float = 0.0,
        initial_duration: float = 0.0,
    ) -> bool:
        success = super().load_media(path, start, end)
        if initial_duration:
            self.report(initial_duration)
        return success


class _Audio(_Player):
    """TiLiA's audio player: it reports the length of a file as it loads it."""

    MEDIA_TYPE = "audio"
    LENGTH = 20.0

    def _engine_load_media(self, media_path: str) -> bool:
        self.report(self.LENGTH)
        return True


@pytest.fixture
def youtube(qtui, tilia, tls):
    """The stand-in for TiLiA's YouTube player, for the media TiLiA loads."""
    with Serve(Get.PLAYER_CLASS, _YouTube):
        yield


@pytest.fixture
def audio(qtui, tilia, tls):
    """The stand-in for TiLiA's audio player, as the app's player now: TiLiA changes
    its player only for media of another kind, and the one it has may be its own."""
    with Serve(Get.PLAYER_CLASS, _Audio):
        if not isinstance(tilia.player, _Audio):
            # As TiLiA changes its player: the new one first, then the old one goes.
            player = _Audio()
            tilia.player.destroy()
            tilia.player = player
        yield


def a_file(folder: Path, media_path: str = LINK, length: float | None = STORED) -> Path:
    """WP3's file of every kind, with this media, a link or an absolute path, as the
    core writes it into `folder`."""
    doc = tla.read(EVERY_KIND)
    doc.media_path = media_path
    doc.media_length = length
    path = folder / "file.tla"
    tla.write(path, doc)
    return path


def a_local_file(folder: Path, length: float | None) -> Path:
    """The same, with a local file as its media, beside it."""
    media = folder / "media.mp3"
    media.write_bytes(b"")
    return a_file(folder, str(media), length)


def open_file(path: Path) -> bool:
    """Opens `path`, as the File menu does, declining to look for media or a PDF
    that isn't there, and closing the warnings it opens with."""
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, False),
        Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
        Serve(Get.FROM_USER_SHOW_PROBLEMS, None),
    ):
        return commands.execute("file.open", path)


def save() -> bool:
    return commands.execute("file.save")


def report(tilia, length: float) -> Serve:
    """The player reports `length`. Returns the question to scale, answered yes."""
    with Serve(Get.FROM_USER_YES_OR_NO, True) as question:
        tilia.player.report(length)
    return question


class TestALengthWithinTheTolerance:
    """User story 4, scenario 4; SC-006."""

    @pytest.mark.parametrize(
        "off", [0.003, -0.003, 1.9, -1.9], ids=["3 ms", "-3 ms", "1.9 s", "-1.9 s"]
    )
    def test_keeps_the_stored_one_and_saving_changes_nothing(
        self, youtube, tilia, tmp_path, off
    ):
        path = a_file(tmp_path)
        before = path.read_bytes()
        assert open_file(path)

        question = report(tilia, STORED + off)

        assert not question.called
        assert not tilia.is_file_modified()
        assert save()
        assert path.read_bytes() == before

    def test_a_shorter_one_crops_nothing(self, youtube, tilia, tmp_path):
        assert open_file(a_file(tmp_path))
        timelines = tilia.get_timelines_state()[0]

        report(tilia, STORED - 1.9)

        assert tilia.get_timelines_state()[0] == timelines

    def test_the_metadata_window_shows_the_one_reported(self, youtube, tilia, tmp_path):
        # It reads the player's (FR-035).
        assert open_file(a_file(tmp_path))

        report(tilia, STORED + 1.9)

        assert get(Get.MEDIA_DURATION) == STORED + 1.9

    def test_offline_no_report_keeps_the_stored_one(self, youtube, tilia, tmp_path):
        path = a_file(tmp_path)
        before = path.read_bytes()

        assert open_file(path)

        assert get(Get.MEDIA_DURATION) == STORED
        assert not tilia.is_file_modified()
        assert save()
        assert path.read_bytes() == before

    def test_is_the_tolerance_tilia_s_constant_gives(self):
        assert DURATION_JITTER_TOLERANCE == 2.0


class TestALengthBeyondTheTolerance:
    """User story 4, scenario 5."""

    @pytest.mark.parametrize("off", [2.5, -2.5], ids=["2.5 s", "-2.5 s"])
    def test_asks_and_stores_the_new_one(self, youtube, tilia, tmp_path, off):
        path = a_file(tmp_path)
        assert open_file(path)

        question = report(tilia, STORED + off)

        assert question.called
        assert tilia.is_file_modified()
        assert save()
        assert tla.read(path).media_length == STORED + off


class TestAFileWithoutALength:
    """FR-034: it takes the length reported, without a question, as a change that a
    save stores: nothing TiLiA does on opening changes the document (FR-003)."""

    def test_takes_the_one_its_youtube_player_reports(self, youtube, tilia, tmp_path):
        path = a_file(tmp_path, length=None)
        assert open_file(path)

        question = report(tilia, STORED)

        assert not question.called
        assert get(Get.MEDIA_DURATION) == STORED
        assert tilia.is_file_modified()
        assert save()
        assert tla.read(path).media_length == STORED

    def test_one_reported_within_the_tolerance_of_none(self, youtube, tilia, tmp_path):
        # Media shorter than the tolerance: no stored length is near it.
        path = a_file(tmp_path, length=None)
        assert open_file(path)

        report(tilia, 1.5)

        assert save()
        assert tla.read(path).media_length == 1.5

    def test_takes_the_one_reported_as_its_media_loads(self, audio, tilia, tmp_path):
        # A local file's player reports while the file opens.
        path = a_local_file(tmp_path, length=None)

        with Serve(Get.FROM_USER_YES_OR_NO, True) as question:
            assert open_file(path)

        assert get(Get.MEDIA_PATH).endswith("/media.mp3")
        assert not question.called
        assert get(Get.MEDIA_DURATION) == _Audio.LENGTH
        assert tilia.is_file_modified()
        assert save()
        assert tla.read(path).media_length == _Audio.LENGTH

    def test_a_file_with_a_length_keeps_it_as_its_media_loads(
        self, audio, tilia, tmp_path
    ):
        path = a_local_file(tmp_path, length=_Audio.LENGTH + 0.003)
        before = path.read_bytes()

        assert open_file(path)

        assert get(Get.MEDIA_DURATION) == _Audio.LENGTH
        assert not tilia.is_file_modified()
        assert save()
        assert path.read_bytes() == before


class TestTheYouTubeDialog:
    """User story 4, scenario 6 (FR-033): a link is stored with its scheme."""

    @pytest.mark.parametrize(
        "typed, stored",
        [
            (
                "youtube.com/watch?v=dQw4w9WgXcQ",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            ("youtu.be/dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ"),
            (
                "//www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "http://youtube.com/watch?v=dQw4w9WgXcQ",
                "http://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
        ],
        ids=["no scheme", "www", "youtu.be", "two slashes", "https", "http"],
    )
    def test_stores_what_is_typed_with_a_scheme(
        self, youtube, tilia, tmp_path, typed, stored
    ):
        load_youtube_media(typed)
        report(tilia, 212.0)

        # What TiLiA plays and shows, and what the file stores.
        assert get(Get.MEDIA_PATH) == stored
        path = tmp_path / "file.tla"
        assert commands.execute("file.save_as", str(path))
        assert json.loads(path.read_bytes())["media"]["path"] == stored
        assert tla.media(path, tla.read(path)).kind == "youtube"

    def test_a_link_is_never_a_file_named_like_it(
        self, youtube, tilia, tmp_path, monkeypatch
    ):
        # The command line's load-media would take the file (#380); the dialog
        # takes links only.
        (tmp_path / "youtu.be").mkdir()
        (tmp_path / "youtu.be" / "dQw4w9WgXcQ").write_bytes(b"")
        monkeypatch.chdir(tmp_path)

        load_youtube_media("youtu.be/dQw4w9WgXcQ")
        report(tilia, 212.0)

        path = tmp_path / "file.tla"
        assert commands.execute("file.save_as", str(path))
        stored = json.loads(path.read_bytes())["media"]["path"]
        assert stored == "https://youtu.be/dQw4w9WgXcQ"
