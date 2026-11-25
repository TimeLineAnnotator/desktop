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
from unittest.mock import patch

import pytest

from tests.mock import Serve, ServeSequence
from tests.utils import load_youtube_media
from tilia.constants import DURATION_JITTER_TOLERANCE
from tilia.file import autosave
from tilia.media.player.base import Player
from tilia.requests import Get, Post, get, post
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.marker.timeline import MarkerTimelineUI
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

    def test_two_on_either_side_of_the_stored_one_ask_nothing(
        self, youtube, tilia, tmp_path
    ):
        # Each is compared with the length the file stores, not with the one
        # reported before it, 3.8 s away.
        path = a_file(tmp_path)
        before = path.read_bytes()
        assert open_file(path)
        report(tilia, STORED + 1.9)

        question = report(tilia, STORED - 1.9)

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


class _Recorder(Serve):
    """Serves `request` with `return_value`, noting `name` in `log` each time, after
    doing `action`: what happens while a dialog is open."""

    def __init__(self, request: Get, return_value, log: list[str], name: str, action):
        super().__init__(request, return_value)
        self.log = log
        self.name = name
        self.action = action

    def _callback(self, *_, **__):
        self.log.append(self.name)
        if self.action is not None:
            self.action()
        return super()._callback()


def with_a_warning(path: Path) -> None:
    """Puts two of the markers of the file at `path` at 0 s, which breaks a rule, so
    that the file opens with a warning. A scale leaves them there, unchanged, so the
    file keeps the problem it came with."""
    content = json.loads(path.read_bytes())
    markers = next(
        timeline
        for timeline in content["timelines"].values()
        if timeline["kind"] == "Marker"
    )
    for marker in list(markers["components"].values())[:2]:
        marker["time"] = 0.0
    path.write_text(json.dumps(content), encoding="utf-8")


def open_noting(path: Path, log: list[str], while_warnings_shown=None) -> bool:
    """Opens `path`, noting in `log` the warnings and each question, answered yes,
    and doing `while_warnings_shown` while the warnings are."""
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
        _Recorder(
            Get.FROM_USER_SHOW_PROBLEMS, None, log, "warnings", while_warnings_shown
        ),
        _Recorder(Get.FROM_USER_YES_OR_NO, True, log, "question", None),
    ):
        return commands.execute("file.open", path)


def drawn(tluis) -> list[tuple]:
    """Each item that can be seen of each element of the timelines, as it is drawn:
    what it is, and where."""
    return [
        (
            type(element).__name__,
            type(item).__name__,
            item.sceneBoundingRect().getRect(),
        )
        for tlui in tluis
        for element in tlui
        for item in element.child_items()
        if item.isVisible()
    ]


def drawn_markers(tluis) -> list[tuple[float, float]]:
    """Where each marker is drawn, and the time it has."""
    return [
        (element.body.sceneBoundingRect().center().x(), element.get_data("time"))
        for tlui in tluis
        if isinstance(tlui, MarkerTimelineUI)
        for element in tlui
    ]


def marker_labels(path: Path) -> list[str]:
    """The labels of the markers the file at `path` stores."""
    return [
        component.attrs.get("label", "")
        for timeline in tla.read(path).timelines.values()
        if timeline.kind == "marker"
        for component in timeline.components.values()
    ]


def marker_times(path: Path) -> list[float]:
    """The times of the markers the file at `path` stores."""
    return sorted(
        component.attrs["time"]
        for timeline in tla.read(path).timelines.values()
        if timeline.kind == "marker"
        for component in timeline.components.values()
    )


class TestALocalFilesLengthAsItOpens:
    """A local file's media reports its length while the file loads, before its
    timelines are built. Once the file is open, TiLiA handles that report as a later
    one (FR-034; TimeLineAnnotator/project-management#629, point 1, a)."""

    @pytest.mark.parametrize(
        "reported, answers, kept",
        [
            (20.0, [True], "scaled"),
            (20.0, [False], "as they are"),
            (15.0, [True], "scaled"),
            (15.0, [False, True], "cropped"),
            (15.0, [False, False], "scaled"),
        ],
        ids=[
            "longer, scale",
            "longer, don't scale",
            "shorter, scale",
            "shorter, crop",
            "shorter, neither: scale",
        ],
    )
    def test_beyond_the_tolerance_asks_and_takes_the_new_one(
        self, audio, tilia, tmp_path, monkeypatch, reported, answers, kept
    ):
        monkeypatch.setattr(_Audio, "LENGTH", reported)
        path = a_local_file(tmp_path, length=STORED)
        times = marker_times(path)
        questions = ServeSequence(Get.FROM_USER_YES_OR_NO, answers)

        with questions:
            assert open_file(path)

        assert questions.return_count == len(answers)
        assert get(Get.MEDIA_DURATION) == reported
        assert tilia.is_file_modified()
        assert save()
        assert tla.read(path).media_length == reported
        expected = {
            "scaled": [time * reported / STORED for time in times],
            "as they are": times,
            "cropped": [time for time in times if time <= reported],
        }[kept]
        assert marker_times(path) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "reported, answers",
        [(20.0, [True]), (15.0, [False, True])],
        ids=["scale", "crop"],
    )
    def test_undo_doesn_t_go_back_past_the_answer(
        self, audio, tilia, tls, tmp_path, monkeypatch, reported, answers
    ):
        # The answer is part of the file as opened: undo starts after it
        # (TimeLineAnnotator/project-management#642, a).
        monkeypatch.setattr(_Audio, "LENGTH", reported)
        path = a_local_file(tmp_path, length=STORED)
        questions = ServeSequence(Get.FROM_USER_YES_OR_NO, answers)
        with questions:
            assert open_file(path)
        assert questions.return_count == len(answers)
        answered = tilia.get_timelines_state()[0]
        markers = tls.get_timelines_by_type(MarkerTimeline)[0]
        first = min(markers, key=lambda marker: marker.get_data("time"))
        markers.set_component_data(first.id, "label", "edited")
        post(Post.APP_STATE_RECORD, "test")

        with Serve(Get.FROM_USER_YES_OR_NO, False) as question:
            commands.execute("edit.undo")
            commands.execute("edit.undo")

        assert not question.called
        assert tilia.get_timelines_state()[0] == answered
        assert get(Get.MEDIA_DURATION) == reported
        assert save()
        assert tla.read(path).media_length == reported
        assert "edited" not in marker_labels(path)

        commands.execute("edit.redo")

        assert save()
        assert tla.read(path).media_length == reported
        assert "edited" in marker_labels(path)

    @pytest.mark.parametrize(
        "reported, answers",
        [(20.0, [True]), (15.0, [False, True])],
        ids=["scale", "crop"],
    )
    def test_undo_right_after_the_answer_does_nothing(
        self, audio, tilia, tluis, tmp_path, monkeypatch, reported, answers
    ):
        # As in a file just opened, the history holds the one state it starts from
        # (TimeLineAnnotator/project-management#642, a).
        monkeypatch.setattr(_Audio, "LENGTH", reported)
        with ServeSequence(Get.FROM_USER_YES_OR_NO, answers):
            assert open_file(a_local_file(tmp_path, length=STORED))
        assert tilia.undo_manager.is_cleared
        answered = tilia.get_timelines_state()[0]
        as_drawn = drawn(tluis)

        with Serve(Get.FROM_USER_YES_OR_NO, True) as question:
            commands.execute("edit.undo")
            commands.execute("edit.redo")

        assert not question.called
        assert tilia.get_timelines_state()[0] == answered
        assert drawn(tluis) == as_drawn
        assert get(Get.MEDIA_DURATION) == reported
        assert tilia.is_file_modified()

    def test_the_document_follows_the_answer_at_once(
        self, audio, tilia, tmp_path, monkeypatch
    ):
        # An autosave before any action writes the timelines as answered.
        monkeypatch.setattr(_Audio, "LENGTH", 20.0)
        path = a_local_file(tmp_path, length=STORED)
        times = marker_times(path)
        with Serve(Get.FROM_USER_YES_OR_NO, True):
            assert open_file(path)
        (tmp_path / "autosaves").mkdir()
        autosaved = tmp_path / "autosaves" / "autosave.tla"

        with (
            patch.object(autosave, "get_autosave_path", return_value=autosaved),
            patch.object(autosave, "make_room_for_new_autosave"),
        ):
            autosave.autosave(tilia.file_manager.file.copy_for_writing())

        assert tla.read(autosaved).media_length == 20.0
        assert marker_times(autosaved) == pytest.approx(
            [time * 20.0 / STORED for time in times]
        )

    @pytest.mark.parametrize(
        "reported, answers",
        [
            (20.0, [True]),
            (20.0, [False]),
            (15.0, [True]),
            (15.0, [False, True]),
            (15.0, [False, False]),
        ],
        ids=[
            "longer, scale",
            "longer, don't scale",
            "shorter, scale",
            "shorter, crop",
            "shorter, neither: scale",
        ],
    )
    def test_everything_is_drawn_where_the_answer_puts_it(
        self, audio, tluis, tmp_path, monkeypatch, reported, answers
    ):
        monkeypatch.setattr(_Audio, "LENGTH", reported)
        questions = ServeSequence(Get.FROM_USER_YES_OR_NO, answers)
        with questions:
            assert open_file(a_local_file(tmp_path, length=STORED))
        assert questions.return_count == len(answers)

        as_opened = drawn(tluis)

        # Where a zoom, which draws everything again, puts it.
        for tlui in tluis:
            tluis.update_timeline_times(tlui)
        assert as_opened == drawn(tluis)
        for x, time in drawn_markers(tluis):
            assert x == pytest.approx(time_x_converter.get_x_by_time(time), abs=1)

    def test_within_the_tolerance_asks_nothing(self, audio, tilia, tmp_path):
        path = a_local_file(tmp_path, length=_Audio.LENGTH + 1.9)
        before = path.read_bytes()

        with Serve(Get.FROM_USER_YES_OR_NO, True) as question:
            assert open_file(path)

        assert not question.called
        assert not tilia.is_file_modified()
        assert save()
        assert path.read_bytes() == before

    def test_asks_after_the_file_s_warnings(self, audio, tilia, tmp_path):
        path = a_local_file(tmp_path, length=STORED)
        with_a_warning(path)
        shown: list[str] = []

        assert open_noting(path, shown)

        assert shown == ["warnings", "question"]

    def test_a_report_handled_while_the_warnings_are_shown_isn_t_handled_again(
        self, audio, tilia, tmp_path
    ):
        # The warnings dialog runs an event loop. Here the player reports the stored
        # length then: it is the latest, and confirms the stored one.
        path = a_local_file(tmp_path, length=STORED)
        with_a_warning(path)
        times = marker_times(path)
        shown: list[str] = []

        assert open_noting(path, shown, lambda: tilia.player.report(STORED))

        assert shown == ["warnings"]
        assert get(Get.MEDIA_DURATION) == STORED
        assert not tilia.is_file_modified()
        assert save()
        assert tla.read(path).media_length == STORED
        assert marker_times(path) == times

    def test_a_youtube_report_while_the_warnings_are_shown_is_handled_once(
        self, youtube, tilia, tmp_path
    ):
        path = a_file(tmp_path)
        with_a_warning(path)
        times = marker_times(path)
        new = STORED + 2.5
        shown: list[str] = []

        assert open_noting(path, shown, lambda: tilia.player.report(new))

        assert shown == ["warnings", "question"]
        assert save()
        assert tla.read(path).media_length == new
        assert marker_times(path) == pytest.approx(
            [time * new / STORED for time in times]
        )

    def test_undo_doesn_t_go_back_past_an_answer_given_while_the_warnings_are_shown(
        self, youtube, tilia, tls, tmp_path
    ):
        # The answer is given as the file opens, too
        # (TimeLineAnnotator/project-management#642, a).
        path = a_file(tmp_path)
        with_a_warning(path)
        times = marker_times(path)
        new = STORED + 2.5
        shown: list[str] = []
        assert open_noting(path, shown, lambda: tilia.player.report(new))
        assert shown == ["warnings", "question"]
        answered = tilia.get_timelines_state()[0]
        markers = tls.get_timelines_by_type(MarkerTimeline)[0]
        last = max(markers, key=lambda marker: marker.get_data("time"))
        markers.set_component_data(last.id, "label", "edited")
        post(Post.APP_STATE_RECORD, "test")

        with Serve(Get.FROM_USER_YES_OR_NO, False) as question:
            commands.execute("edit.undo")
            commands.execute("edit.undo")

        assert not question.called
        assert tilia.get_timelines_state()[0] == answered
        assert get(Get.MEDIA_DURATION) == new
        assert tilia.is_file_modified()
        assert save()
        assert tla.read(path).media_length == new
        assert marker_times(path) == pytest.approx(
            [time * new / STORED for time in times]
        )
        assert "edited" not in marker_labels(path)

    def test_a_youtube_report_as_the_file_loads_is_handled_as_a_local_one(
        self, youtube, tilia, tmp_path, monkeypatch
    ):
        # As the command line's YouTube player reports: as it loads the media.
        new = STORED + 2.5

        def load_media(player, path, start=0.0, end=0.0, initial_duration=0.0):
            success = _Player.load_media(player, path, start, end)
            player.report(new)
            return success

        monkeypatch.setattr(_YouTube, "load_media", load_media)
        path = a_file(tmp_path)
        times = marker_times(path)
        shown: list[str] = []

        assert open_noting(path, shown)

        assert shown == ["question"]
        assert save()
        assert tla.read(path).media_length == new
        assert marker_times(path) == pytest.approx(
            [time * new / STORED for time in times]
        )

    def test_a_youtube_report_during_a_dialog_as_the_file_loads_asks_once(
        self, youtube, tilia, tmp_path
    ):
        # every-kind.tla's PDF isn't there: TiLiA asks, as the file loads, whether to
        # look for it, and the page reports then. What the file then stores is
        # TimeLineAnnotator/project-management#652's.
        path = a_file(tmp_path)
        shown: list[str] = []

        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
            Serve(Get.FROM_USER_SHOW_PROBLEMS, None),
            _Recorder(
                Get.FROM_USER_RETRY_PDF_PATH,
                False,
                shown,
                "pdf",
                lambda: tilia.player.report(STORED + 2.5),
            ),
            _Recorder(Get.FROM_USER_YES_OR_NO, True, shown, "question", None),
        ):
            assert commands.execute("file.open", path)

        assert shown.count("question") == 1

    def test_media_picked_within_the_tolerance_keeps_the_stored_length(
        self, audio, tilia, tmp_path
    ):
        # The file's media isn't there and no place is remembered: the person picks
        # a file, whose player reports 1 s more than the file stores. It is the
        # file's media found elsewhere, which changes nothing (FR-032, FR-034).
        picked = tmp_path / "picked.mp3"
        picked.write_bytes(b"")
        path = a_file(tmp_path, str(tmp_path / "missing.mp3"), _Audio.LENGTH - 1.0)
        before = path.read_bytes()
        shown: list[str] = []

        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
            Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
            Serve(Get.FROM_USER_SHOW_PROBLEMS, None),
            Serve(Get.FROM_USER_RETRY_MEDIA_PATH, True),
            Serve(Get.FROM_USER_MEDIA_PATH, (True, str(picked))),
            _Recorder(Get.FROM_USER_YES_OR_NO, True, shown, "question", None),
        ):
            assert commands.execute("file.open", path)

        assert get(Get.MEDIA_DURATION) == _Audio.LENGTH
        assert shown == []
        assert not tilia.is_file_modified()
        assert save()
        assert path.read_bytes() == before


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

    def test_a_second_report_within_the_tolerance_is_still_a_change(
        self, youtube, tilia, tmp_path
    ):
        # The length taken isn't on disk: the file has none to keep yet.
        path = a_file(tmp_path, length=None)
        assert open_file(path)
        report(tilia, STORED)

        question = report(tilia, STORED + 0.003)

        assert not question.called
        assert tilia.is_file_modified()
        assert save()
        assert tla.read(path).media_length == STORED + 0.003

    def test_once_saved_the_length_taken_is_the_stored_one(
        self, youtube, tilia, tmp_path
    ):
        path = a_file(tmp_path, length=None)
        assert open_file(path)
        report(tilia, STORED)
        assert save()
        before = path.read_bytes()

        question = report(tilia, STORED + 0.003)

        assert not question.called
        assert not tilia.is_file_modified()
        assert save()
        assert path.read_bytes() == before

    def test_an_edit_and_its_undo_leave_it_a_change(self, audio, tilia, tls, tmp_path):
        # The undo gives the player the length again, which isn't on disk.
        path = a_local_file(tmp_path, length=None)
        assert open_file(path)
        marker_timeline = next(
            timeline
            for timeline in tilia.file_manager.file.document.timelines.values()
            if timeline.kind == "marker"
        )
        tls.get_timeline(marker_timeline.id).set_component_data(
            next(iter(marker_timeline.components)), "label", "edited"
        )
        post(Post.APP_STATE_RECORD, "test")

        commands.execute("edit.undo")

        assert tilia.is_file_modified()
        assert save()
        assert tla.read(path).media_length == _Audio.LENGTH

    @pytest.mark.parametrize(
        "media_path", ["", "missing.mp3"], ids=["none", "declined"]
    )
    def test_loading_the_same_media_again_after_an_undo(
        self, audio, tilia, tmp_path, media_path
    ):
        # A file without media, or whose media isn't looked for, and without a length.
        # TiLiA holds no length after the undo, and takes the media's with no question,
        # where scaling from no length divided by zero.
        path = a_file(tmp_path, str(tmp_path / media_path) if media_path else "", None)
        take1 = tmp_path / "take1.mp3"
        take1.write_bytes(b"")
        times = marker_times(path)
        assert open_file(path)
        with Serve(Get.FROM_USER_YES_OR_NO, True):
            post(Post.APP_MEDIA_LOAD, str(take1))
            commands.execute("edit.undo")

        with Serve(Get.FROM_USER_YES_OR_NO, True) as question:
            post(Post.APP_MEDIA_LOAD, str(take1))

        assert not question.called
        assert get(Get.MEDIA_DURATION) == _Audio.LENGTH
        assert save()
        assert tla.read(path).media_length == _Audio.LENGTH
        assert marker_times(path) == times

    @pytest.mark.parametrize(
        "media_path", ["", "missing.mp3"], ids=["none", "declined"]
    )
    def test_loading_the_same_media_again_after_an_undo_with_a_length_stored(
        self, audio, tilia, tmp_path, media_path
    ):
        # The same in a file that stores a length: nothing divides by zero, whatever
        # is answered.
        path = a_file(tmp_path, str(tmp_path / media_path) if media_path else "")
        take1 = tmp_path / "take1.mp3"
        take1.write_bytes(b"")
        assert open_file(path)
        with Serve(Get.FROM_USER_YES_OR_NO, True):
            post(Post.APP_MEDIA_LOAD, str(take1))
            commands.execute("edit.undo")
            post(Post.APP_MEDIA_LOAD, str(take1))

        assert get(Get.MEDIA_DURATION) == _Audio.LENGTH
        assert save()
        assert tla.read(path).media_length == _Audio.LENGTH

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
