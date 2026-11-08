import pytest

from tests.constants import EXAMPLE_MUSICXML_PATH, EXAMPLE_QUARTER_TONES_MUSICXML_PATH
from tests.mock import patch_file_dialog
from tests.utils import (
    get_command_names,
    get_main_window_menu,
    get_submenu,
    save_and_reopen,
    undoable,
)
from tilia.requests import Get, get
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui import commands

COMMAND = "timelines.import.score_with_beats"


def _only_timeline(cls):
    timelines = get(Get.TIMELINE_COLLECTION).get_timelines_by_type(cls)
    assert len(timelines) <= 1
    return timelines[0] if timelines else None


def _beat_tl():
    return _only_timeline(BeatTimeline)


def _score_tl():
    return _only_timeline(ScoreTimeline)


def _notes():
    return _score_tl().component_manager._get_component_set_by_kind(ComponentKind.NOTE)


def _beat_times():
    return [b.time for b in sorted(_beat_tl())]


@pytest.fixture
def no_media(tilia_state):
    tilia_state.duration = 0
    # As in a new file: undo must find no duration to go back to.
    tilia_state._reset_undo_manager()


class TestWithoutMedia:
    def test_creates_a_beat_and_a_score_timeline(self, tluis, no_media):
        commands.execute(COMMAND, path=EXAMPLE_QUARTER_TONES_MUSICXML_PATH)

        assert _beat_tl().name == "Beats"
        assert _score_tl().name == "Quarter-tone study"
        assert _notes()

    def test_beats_follow_the_measures(self, tluis, no_media):
        commands.execute(COMMAND, path=EXAMPLE_QUARTER_TONES_MUSICXML_PATH)

        beat_tl = _beat_tl()
        assert len(beat_tl) == 16
        assert beat_tl.beats_in_measure == [4, 4, 4, 4]
        assert beat_tl.measure_numbers == [1, 2, 3, 4]

    def test_one_second_per_beat_without_tempo(self, tluis, tilia_state, no_media):
        commands.execute(COMMAND, path=EXAMPLE_QUARTER_TONES_MUSICXML_PATH)

        assert tilia_state.duration == 16
        assert _beat_times() == [float(i) for i in range(16)]

    def test_keeps_a_pickup_measure(self, tluis, no_media):
        commands.execute(COMMAND, path=EXAMPLE_MUSICXML_PATH)

        beat_tl = _beat_tl()
        assert beat_tl.measure_numbers == [0, 1, 2]
        assert beat_tl.beats_in_measure == [1, 3, 3]
        # Every note of the pickup is imported, with no prompt to add measure 0.
        assert len(_notes()) == 4

    def test_duration_from_the_tempo(self, tluis, tilia_state, no_media, tmp_path):
        xml = open(EXAMPLE_QUARTER_TONES_MUSICXML_PATH).read()
        # A quarter at 120 per minute: half a second per beat.
        xml = xml.replace("</attributes>", '</attributes><sound tempo="120"/>', 1)
        path = tmp_path / "fast.musicxml"
        path.write_text(xml)

        commands.execute(COMMAND, path=str(path))

        assert tilia_state.duration == 8
        assert _beat_times()[:3] == [0, 0.5, 1]

    def test_asks_for_the_file(self, tluis, no_media):
        with patch_file_dialog(True, [EXAMPLE_QUARTER_TONES_MUSICXML_PATH]):
            commands.execute(COMMAND)

        assert _notes()

    def test_cancelling_the_file_dialog_changes_nothing(
        self, tluis, tilia_state, no_media
    ):
        with patch_file_dialog(False, [""]):
            commands.execute(COMMAND)

        assert _beat_tl() is None
        assert _score_tl() is None
        assert tilia_state.duration == 0

    def test_an_invalid_file_changes_nothing(
        self, tluis, tilia_state, tilia_errors, no_media, tmp_path
    ):
        path = tmp_path / "bad.musicxml"
        path.write_text("<notmusic/>")

        commands.execute(COMMAND, path=str(path))

        assert _beat_tl() is None
        assert _score_tl() is None
        assert tilia_state.duration == 0
        tilia_errors.assert_error()

    def test_undo_and_redo(self, tluis, tilia_state, no_media):
        commands.execute(COMMAND, path=EXAMPLE_QUARTER_TONES_MUSICXML_PATH)

        commands.execute("edit.undo")
        assert _beat_tl() is None
        assert _score_tl() is None
        # The duration set for the score stays, as a duration set by hand does.
        assert tilia_state.duration == 16

        commands.execute("edit.redo")
        assert len(_beat_tl()) == 16
        assert _notes()

    def test_save_and_reopen(self, tluis, tilia_state, no_media, tmp_path):
        commands.execute(COMMAND, path=EXAMPLE_MUSICXML_PATH)
        note_count = len(_notes())

        save_and_reopen(tmp_path)

        assert tilia_state.duration == 7
        assert _beat_tl().measure_numbers == [0, 1, 2]
        assert len(_beat_tl()) == 7
        assert len(_notes()) == note_count


class TestWithMedia:
    def test_beats_are_spread_over_the_media(self, tluis, tilia_state):
        tilia_state.duration = 32

        commands.execute(COMMAND, path=EXAMPLE_QUARTER_TONES_MUSICXML_PATH)

        assert tilia_state.duration == 32
        assert _beat_times() == [float(2 * i) for i in range(16)]

    def test_undo_and_redo(self, tluis):
        with undoable():
            commands.execute(COMMAND, path=EXAMPLE_QUARTER_TONES_MUSICXML_PATH)


class TestMenus:
    def test_in_the_score_menu(self, qtui):
        menu = get_submenu(get_main_window_menu(qtui, "Timelines"), "Score")
        assert COMMAND in get_command_names(menu)

    def test_in_the_file_menu(self, qtui):
        assert COMMAND in get_command_names(get_main_window_menu(qtui, "File"))

    def test_menu_action_imports(self, qtui, tluis, no_media):
        menu = get_main_window_menu(qtui, "File")
        action = next(
            a for a in menu.actions() if getattr(a, "command_name", "") == COMMAND
        )
        with patch_file_dialog(True, [EXAMPLE_QUARTER_TONES_MUSICXML_PATH]):
            action.trigger()

        assert _notes()
