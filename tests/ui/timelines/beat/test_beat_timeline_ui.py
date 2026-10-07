from unittest.mock import MagicMock

import pytest

from tests.mock import Serve, patch_yes_or_no_dialog
from tests.ui.timelines.beat.interact import click_beat_ui
from tests.ui.timelines.interact import drag_mouse_in_timeline_view
from tests.utils import get_command_names, reloadable, undoable
from tilia.requests import Get, Post, post
from tilia.settings import settings
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.ui import commands
from tilia.ui.commands import get_qaction
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.beat.context_menu import BeatContextMenu
from tilia.ui.windows import WindowKind


def get_displayed_measure_number(beat_ui):
    if beat_ui.label.isVisible():
        return beat_ui.label.toPlainText()
    else:
        return ""


class TestLoadFromFile:
    def test_measure_numbers_are_loaded(self, beat_tl, tluis, tmp_path):
        beat_tl.beat_pattern = [1]

        beat_tl.create_beat(0)
        beat_tl.create_beat(1)
        beat_tl.create_beat(2)
        beat_tl.create_beat(3)

        beat_tl.recalculate_measures()

        beat_tl.set_measure_number(0, 1)
        beat_tl.set_measure_number(1, 3)
        beat_tl.set_measure_number(2, 5)
        beat_tl.set_measure_number(3, 7)

        tmp_file = tmp_path / "test.tla"

        post(Post.REQUEST_SAVE_TO_PATH, tmp_file)

        commands.execute("file.open", tmp_file)

        assert [x.label.toPlainText() for x in tluis[0]] == ["1", "3", "5", "7"]

    def test_file_with_measures_to_force_display(
        self, beat_tlui, tluis, tmp_path, use_test_settings
    ):
        settings.set("beat_timeline", "display_measure_periodicity", 2)

        beat_tlui.timeline.beat_pattern = [1]
        for i in range(8):
            beat_tlui.create_beat(i)

        beat_tlui.timeline.measures_to_force_display = [1, 3, 5, 7]

        tmp_file = tmp_path / "test.tla"

        post(Post.REQUEST_SAVE_TO_PATH, tmp_file)

        commands.execute("file.open", tmp_file)

        assert [x.label.toPlainText() for x in tluis[0]] == [
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
        ]

    def test_duplicate_and_out_of_range_forced_measures_are_dropped(
        self, beat_tlui, tluis, tmp_path
    ):
        # Earlier versions could save such a list; the current one can't
        # produce it, so it is set directly.
        settings.set("beat_timeline", "display_measure_periodicity", 4)
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(4):
            commands.execute("media.seek", i)
            commands.execute("timeline.beat.add")
        beat_tlui.timeline.measures_to_force_display = [1, 6, 1, 2]

        tmp_file = tmp_path / "test.tla"
        post(Post.REQUEST_SAVE_TO_PATH, tmp_file)
        commands.execute("file.open", tmp_file)

        reopened = tluis[0]
        reopened.select_element(reopened[1])
        commands.execute("timeline.beat.reset_measure_number")
        # A duplicate would need a second reset to hide the label.
        assert get_displayed_measure_number(reopened[1]) == ""

        for i in range(4, 7):
            commands.execute("media.seek", i)
            commands.execute("timeline.beat.add")
        # An out-of-range index would force measure 7's label once it exists.
        assert get_displayed_measure_number(reopened[6]) == ""


class TestCreateDeleteBeat:
    def test_create_single(self, beat_tlui):
        beat_tlui.create_beat(0)

        assert len(beat_tlui) == 1

    def test_create_multiple(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        assert len(beat_tlui) == 3

    def test_delete(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.select_all_elements()

        commands.execute("timeline.component.delete")

        assert len(beat_tlui) == 0
        assert not beat_tlui.selected_elements

    def test_delete_update_next_measures_numbers(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        beat_tlui.timeline.measures_to_force_display = [0, 1, 2]
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)

        beat_tlui.select_element(beat_tlui[0])
        commands.execute("timeline.component.delete")

        assert get_displayed_measure_number(beat_tlui[0]) == "1"
        assert get_displayed_measure_number(beat_tlui[1]) == "2"

    def test_create_update_next_measures_numbers(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        beat_tlui.timeline.measures_to_force_display = [0, 1, 2, 3]
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)

        commands.execute("media.seek", 0.5)
        commands.execute("timeline.beat.add")

        assert [get_displayed_measure_number(beat) for beat in beat_tlui] == [
            "1",
            "2",
            "3",
            "4",
        ]


class TestSelect:
    def test_deselect_all_but_last(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        beat_tlui.select_all_elements()

        beat_tlui._deselect_all_but_last()

        assert beat_tlui.selected_elements == [beat_tlui[-1]]

    def test_deselect_all_but_first(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        beat_tlui.select_all_elements()

        beat_tlui._deselect_all_but_first()

        assert beat_tlui.selected_elements == [beat_tlui[0]]

    def test_on_right_arrow_press_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]

        beat_tlui.select_element(beat0)
        beat_tlui.on_horizontal_arrow_press("right")
        assert beat_tlui.selected_elements == [beat1]

        beat_tlui.on_horizontal_arrow_press("right")
        assert beat_tlui.selected_elements == [beat1]

    def test_on_left_arrow_press_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]

        beat_tlui.select_element(beat1)
        beat_tlui.on_horizontal_arrow_press("left")
        assert beat_tlui.selected_elements == [beat0]

        beat_tlui.on_horizontal_arrow_press("left")
        assert beat_tlui.selected_elements == [beat0]

    def test_on_right_arrow_press_more_than_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        beat_tlui.create_beat(0.3)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]
        beat2 = beat_tlui[2]
        beat3 = beat_tlui[3]

        beat_tlui.select_element(beat0)
        beat_tlui.select_element(beat1)
        beat_tlui.select_element(beat2)

        beat_tlui.on_horizontal_arrow_press("right")
        assert beat_tlui.selected_elements == [beat3]

    def test_on_left_arrow_press_more_than_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        beat_tlui.create_beat(0.3)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]
        beat2 = beat_tlui[2]
        beat3 = beat_tlui[3]

        beat_tlui.select_element(beat1)
        beat_tlui.select_element(beat2)
        beat_tlui.select_element(beat3)

        beat_tlui.on_horizontal_arrow_press("left")
        assert beat_tlui.selected_elements == [beat0]


class TestGetBeat:
    def test_get_next_beat(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]
        assert beat_tlui.get_next_element(beat0) == beat1
        assert beat_tlui.get_next_element(beat1) is None

    def test_get_previous_beat(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]
        assert beat_tlui.get_previous_element(beat1) == beat0
        assert beat_tlui.get_previous_element(beat0) is None


class TestCopyPaste:
    def test_get_copy_data_from_beat_uis(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        beat_tlui.create_beat(0.3)

        for beat in beat_tlui:
            beat_tlui.select_element(beat)

        copy_data = beat_tlui.get_copy_data_from_selected_elements()
        beat0_data = {
            "values": {},
            "context": {"time": 0},
        }
        beat1_data = {
            "values": {},
            "context": {"time": 0.1},
        }
        beat2_data = {
            "values": {},
            "context": {"time": 0.2},
        }
        beat3_data = {
            "values": {},
            "context": {"time": 0.3},
        }
        assert beat0_data in copy_data
        assert beat1_data in copy_data
        assert beat2_data in copy_data
        assert beat3_data in copy_data

    def test_paste_single_into_selected_elements(self, beat_tlui, tluis):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui.elements[0])

        tl_state0 = beat_tlui.timeline.get_state()

        commands.execute("timeline.component.copy")
        commands.execute("timeline.component.paste")

        tl_state1 = beat_tlui.timeline.get_state()

        assert tl_state0 == tl_state1

    def test_paste_single_into_timeline(self, beat_tlui, tluis):
        beat_tlui.create_beat(10)
        beat_tlui.select_element(beat_tlui[0])

        commands.execute("timeline.component.copy")

        beat_tlui.deselect_element(beat_tlui[0])

        commands.execute("timeline.component.paste")

        assert len(beat_tlui) == 2
        assert beat_tlui[0].time == 0

    def test_paste_multiple_into_timeline(self, beat_tlui, tluis):
        beat_tlui.create_beat(10)
        beat_tlui.create_beat(11)
        beat_tlui.create_beat(12)
        beat_tlui.create_beat(13)

        beat_tlui.select_all_elements()

        commands.execute("timeline.component.copy")

        beat_tlui.deselect_all_elements()

        commands.execute("timeline.component.paste")

        assert len(beat_tlui) == 8
        assert beat_tlui[0].time == 0
        assert beat_tlui[1].time == 1
        assert beat_tlui[2].time == 2
        assert beat_tlui[3].time == 3


class TestOther:
    def test_get_measure_number(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        beat_tlui.timeline.recalculate_measures()

        expected_measure_numbers = {
            0: 1,
            1: 1,
            2: 1,
            3: 2,
            4: 2,
            5: 2,
            6: 3,
            7: 3,
            8: 3,
            9: 4,
            10: 4,
            11: 4,
        }

        for i, beat in enumerate(sorted(beat_tlui)):
            assert beat.get_data("measure") == expected_measure_numbers[i]


DUMMY_MEASURE_NUMBER = 11


class TestSetMeasureNumber:
    @staticmethod
    def _set_measure_number(number=DUMMY_MEASURE_NUMBER):
        """Assumes there a beat in the measure is selected"""
        with Serve(Get.FROM_USER_INT, (True, number)):
            commands.execute("timeline.beat.set_measure_number")

    def test_set_measure_number_single_measure(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_set_measure_number_twice(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        self._set_measure_number(101)
        assert beat_tlui.timeline.measure_numbers[0] == 101

    def test_set_measure_number_multiple_measures(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        beat_tlui.select_element(beat_tlui[3])
        self._set_measure_number()

        assert beat_tlui.timeline.measure_numbers[1] == DUMMY_MEASURE_NUMBER

    def test_set_measure_number_not_first_beat_in_measure(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        beat_tlui.select_element(beat_tlui[1])
        self._set_measure_number()

        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_undo_set_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("edit.undo")
        assert beat_tlui.timeline.measure_numbers[0] == 1

    def test_redo_set_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("edit.undo")
        commands.execute("edit.redo")
        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_reset_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("timeline.beat.reset_measure_number")
        assert beat_tlui.timeline.measure_numbers[0] == 1

    def test_undo_reset_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("timeline.beat.reset_measure_number")
        commands.execute("edit.undo")
        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_redo_reset_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("timeline.beat.reset_measure_number")
        commands.execute("edit.undo")
        commands.execute("edit.redo")
        assert beat_tlui.timeline.measure_numbers[0] == 1

    def test_reset_measure_number_hides_label_set_more_than_once(self, beat_tlui):
        settings.set("beat_timeline", "display_measure_periodicity", 4)
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(4):
            beat_tlui.create_beat(i)

        beat_tlui.select_element(beat_tlui[1])
        self._set_measure_number()
        self._set_measure_number()
        assert get_displayed_measure_number(beat_tlui[1]) == str(DUMMY_MEASURE_NUMBER)

        commands.execute("timeline.beat.reset_measure_number")

        assert get_displayed_measure_number(beat_tlui[1]) == ""

    def test_forced_measure_past_the_end_is_dropped_when_beats_are_deleted(
        self, beat_tlui
    ):
        settings.set("beat_timeline", "display_measure_periodicity", 4)
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(6):
            commands.execute("media.seek", i)
            commands.execute("timeline.beat.add")

        # Forcing measure 6 before measure 2 leaves the list unsorted.
        beat_tlui.select_element(beat_tlui[5])
        self._set_measure_number(6)
        beat_tlui.deselect_all_elements()
        beat_tlui.select_element(beat_tlui[1])
        self._set_measure_number(2)
        beat_tlui.deselect_all_elements()

        for i in range(3, 6):
            beat_tlui.select_element(beat_tlui[i])
        commands.execute("timeline.component.delete")
        for i in range(3, 6):
            commands.execute("media.seek", i)
            commands.execute("timeline.beat.add")

        assert get_displayed_measure_number(beat_tlui[5]) == ""

    def test_measure_zero_number_is_not_displayed(self, beat_tlui):
        settings.set("beat_timeline", "display_measure_periodicity", 2)
        beat_tlui.timeline.beat_pattern = [1]

        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)
        beat_tlui.create_beat(3)

        beat_tlui.timeline.recalculate_measures()

        beat_tlui.select_element(beat_tlui[0])

        self._set_measure_number(0)

        displayed_measure = [get_displayed_measure_number(b) for b in beat_tlui]
        assert displayed_measure == ["", "1", "", "3"]

    def test_set_measure_number_undo_redo_and_reload(self, beat_tlui, tluis, tmp_path):
        """Setting a measure number is undoable/redoable and survives
        a save/reopen round trip."""
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])

        with undoable():
            self._set_measure_number()
            assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

        @reloadable(tmp_path / "file.tla")
        def check_measure_number():
            assert tluis[0].timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_reset_measure_number_is_undoable(self, beat_tlui):
        """Undoing a measure-number reset must restore the custom
        number exactly (full app-state comparison, not just the target
        attribute), and redoing must reset it again. Uses a non-first
        measure so the reset also exercises the propagation cascade to
        later measures, not just the hardcoded "measure 0 resets to 1"
        branch."""
        beat_tlui.timeline.beat_pattern = [3]
        for i in range(12):
            beat_tlui.create_beat(i / 10)
        beat_tlui.timeline.recalculate_measures()

        beat_tlui.select_element(beat_tlui[3])
        self._set_measure_number()

        with undoable():
            commands.execute("timeline.beat.reset_measure_number")
            assert beat_tlui.timeline.measure_numbers[1] == 2


class TestActions:
    def test_inspect(self, qtui, beat_tlui, tilia_state):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for element in beat_tlui:
            beat_tlui.select_element(element)

        commands.execute("timeline.element.inspect")

        assert tilia_state.is_window_open(qtui, WindowKind.INSPECT)

        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def test_distribute_beats(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)
        beat_tlui.create_beat(3)
        beat_tlui.create_beat(8)

        beat_tlui.select_element(beat_tlui[0])

        commands.execute("timeline.beat.distribute")

        assert beat_tlui[1].get_data("time") == 2
        assert beat_tlui[2].get_data("time") == 4
        assert beat_tlui[3].get_data("time") == 6

    def test_distribute_beats_on_last_measure(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)

        beat_tlui.select_element(beat_tlui[0])

        commands.execute("timeline.beat.distribute")

        assert beat_tlui[0].get_data("time") == 0
        assert beat_tlui[1].get_data("time") == 1


class TestSetBeatAmountInMeasure:
    def test_set_beat_amount_in_measure(self, beat_tlui):
        beat_tlui.create_beat(0)

        beat_tlui.select_element(beat_tlui[0])

        beat_tlui.timeline.set_beat_amount_in_measure = MagicMock()
        commands.execute("timeline.beat.set_amount_in_measure", amount=11)

        beat_tlui.timeline.set_beat_amount_in_measure.assert_called_with(0, 11)

    def test_updates_measure_numbers(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        beat_tlui.timeline.measures_to_force_display = [0, 1, 2]
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)

        beat_tlui.select_element(beat_tlui[0])

        commands.execute("timeline.beat.set_amount_in_measure", amount=2)

        assert [get_displayed_measure_number(b) for b in beat_tlui] == ["1", "", "2"]

    def test_add_beat_when_last_measure_is_fuller_than_beat_pattern(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [4]
        for i in range(24):
            beat_tlui.create_beat(i / 10)

        # give a middle measure one beat more than the beat pattern prescribes
        beat_tlui.select_element(beat_tlui[16])
        commands.execute("timeline.beat.set_amount_in_measure", amount=5)

        # then make that measure the last one
        beat_tlui.deselect_all_elements()
        for element in list(beat_tlui)[-3:]:
            beat_tlui.select_element(element)
        commands.execute("timeline.component.delete")
        assert beat_tlui.timeline.beats_in_measure == [4, 4, 4, 4, 5]

        commands.execute("media.seek", 3.0)
        commands.execute("timeline.beat.add")

        assert len(beat_tlui) == 22
        assert beat_tlui.timeline.beats_in_measure == [4, 4, 4, 4, 5, 1]


class TestFillWithBeats:
    @pytest.fixture(autouse=True)
    def setup(self, beat_tlui):
        # required for undoable actions
        post(Post.APP_STATE_RECORD, "test")

    def test_by_amount(self, beat_tlui):
        with Serve(
            Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD,
            (True, (beat_tlui.timeline, BeatTimeline.FillMethod.BY_AMOUNT, 100)),
        ):
            with undoable():
                commands.execute("timeline.beat.fill")

        assert len(beat_tlui) == 100

    def test_by_interval(self, beat_tlui, tilia_state):
        interval = 0.5
        amount = int(tilia_state.duration / interval)
        with Serve(
            Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD,
            (True, (beat_tlui.timeline, BeatTimeline.FillMethod.BY_INTERVAL, interval)),
        ):
            with undoable():
                commands.execute("timeline.beat.fill")

        assert len(beat_tlui) == amount
        assert beat_tlui[1].get_data("time") - beat_tlui[0].get_data("time") == interval

    def test_accept_delete_existing_beats(self, beat_tlui):
        commands.execute("timeline.beat.add")

        response = (True, (beat_tlui.timeline, BeatTimeline.FillMethod.BY_AMOUNT, 100))
        with Serve(Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD, response):
            with patch_yes_or_no_dialog(True):
                with undoable():
                    commands.execute("timeline.beat.fill")

        assert len(beat_tlui) == 100

    def test_reject_delete_existing_beats(self, beat_tlui):
        beat_tlui.create_beat(0)
        response = (True, (beat_tlui.timeline, BeatTimeline.FillMethod.BY_AMOUNT, 100))
        with Serve(Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD, response):
            with patch_yes_or_no_dialog(False):
                commands.execute("timeline.beat.fill")

        assert len(beat_tlui) == 1


class TestUndoRedo:
    def test_undo_redo_add_beat(self, beat_tlui, tluis):
        commands.execute("media.seek", 10)
        commands.execute("timeline.beat.add")

        commands.execute("edit.undo")
        assert len(beat_tlui) == 0

        commands.execute("edit.redo")
        assert len(beat_tlui) == 1

    def test_undo_redo_delete_beat_multiple_beats(self, beat_tlui, tluis):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for beat_ui in beat_tlui:
            beat_tlui.select_element(beat_ui)

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")
        assert len(beat_tlui) == 3

        commands.execute("edit.redo")
        assert len(beat_tlui) == 0

    def test_undo_redo_delete_beat(self, beat_tlui, tluis):
        # 'tlui_clct' is needed as it subscriber to toolbar event
        # and forwards it to beat timeline

        commands.execute("timeline.beat.add")

        beat_tlui.select_element(beat_tlui[0])
        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")
        assert len(beat_tlui) == 1

        commands.execute("edit.redo")
        assert len(beat_tlui) == 0

    def test_undo_redo_updates_displayed_measure_numbers(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        beat_tlui.timeline.measures_to_force_display = [0, 1, 2]
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)

        post(Post.APP_STATE_RECORD, "test")

        beat_tlui.select_element(beat_tlui[0])
        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")

        assert [get_displayed_measure_number(beat_ui) for beat_ui in beat_tlui] == [
            "1",
            "2",
            "3",
        ]

        commands.execute("edit.redo")

        assert [get_displayed_measure_number(beat_ui) for beat_ui in beat_tlui] == [
            "1",
            "2",
        ]


class TestTimelineUIContextMenu:
    def test_has_no_height_set_action(self, beat_tlui, tluis):
        context_menu = beat_tlui.CONTEXT_MENU_CLASS(beat_tlui, 0, 0)

        assert get_qaction("timeline.set_height") not in context_menu.actions()


class TestChangeBeatsInMeasureContextMenu:
    def test_context_menu_has_set_amount_in_measure(self, beat_tlui):
        beat_tlui.create_beat(0)
        menu = BeatContextMenu(beat_tlui[0])
        assert "timeline.beat.set_amount_in_measure" in get_command_names(menu)

    def test_change_3_to_8_beats_and_undo_redo(self, beat_tlui):
        # A timeline with 3 beats/measure; change one measure from 3 to 8
        # beats and undo/redo it. Regression test for a previously reported
        # crash on undo.
        beat_tlui.timeline.beat_pattern = [3]
        for t in range(6):
            commands.execute("timeline.beat.add", time=t)
        assert beat_tlui.timeline.beats_in_measure == [3, 3]

        beat_tlui.select_element(beat_tlui[0])
        with undoable():
            commands.execute("timeline.beat.set_amount_in_measure", amount=8)
        assert beat_tlui.timeline.beats_in_measure == [6]


class TestDistributeBeatsErrors:
    def test_distribute_from_last_beat_displays_error(self, beat_tlui, tilia_errors):
        for t in range(8):
            beat_tlui.create_beat(t)

        beat_tlui.select_element(beat_tlui[-1])
        commands.execute("timeline.beat.distribute")

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_title("Distribute")
        assert beat_tlui.timeline.beats_in_measure == [4, 4]

    def test_distribute_measure_with_one_beat_displays_error(
        self, beat_tlui, tilia_errors
    ):
        # Most plausible reading: the only measure-with-one-beat case the app
        # actually flags is a trailing/incomplete last measure -
        # BeatTLComponentManager.distribute_beats only errors on
        # `measure_index == measure_count - 1`, so build a timeline whose
        # last measure has exactly one beat.
        for t in range(5):
            beat_tlui.create_beat(t)
        assert beat_tlui.timeline.beats_in_measure == [4, 1]

        beat_tlui.select_element(beat_tlui[4])
        commands.execute("timeline.beat.distribute")

        tilia_errors.assert_error()
        assert beat_tlui.timeline.beats_in_measure == [4, 1]


class TestSetBeatAmountInMeasureEdgeCases:
    def test_add_beat_after_oversized_measure_change(self, beat_tlui):
        for t in range(8):
            beat_tlui.create_beat(t)  # pattern [4] -> measures [4, 4]

        beat_tlui.select_element(beat_tlui[0])
        commands.execute("timeline.beat.set_amount_in_measure", amount=100)

        commands.execute("timeline.beat.add", time=8)
        assert len(beat_tlui) == 9

    def test_change_beats_starting_from_measure_with_one_beat(self, beat_tlui):
        # The one-beat measure being changed is not the last measure, so the
        # shortfall is absorbed from later measures instead of being
        # silently reverted.
        beat_tlui.timeline.beat_pattern = [1, 4]
        for t in range(5):
            commands.execute("timeline.beat.add", time=t)
        assert beat_tlui.timeline.beats_in_measure == [1, 4]

        beat_tlui.select_element(beat_tlui[0])
        with undoable():
            commands.execute("timeline.beat.set_amount_in_measure", amount=2)
        assert beat_tlui.timeline.beats_in_measure == [2, 3]


class TestFillWithBeatsIntervalEdgeCases:
    @pytest.mark.parametrize(
        "pre_existing_beats, interval",
        [
            pytest.param(0, 0.5, id="empty-timeline"),
            pytest.param(1, 0.5, id="non-empty-timeline"),
            pytest.param(
                0,
                0,
                id="interval-zero",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "BeatTimeline.fill_with_beats divides the media "
                        "duration by the interval unconditionally "
                        "(tilia/timelines/beat/timeline.py:705), so an "
                        "interval of 0 raises ZeroDivisionError instead of "
                        "being refused."
                    ),
                ),
            ),
        ],
    )
    def test_fill_by_interval(
        self, beat_tlui, tilia_state, pre_existing_beats, interval
    ):
        for t in range(pre_existing_beats):
            commands.execute("timeline.beat.add", time=t)

        response = (
            True,
            (beat_tlui.timeline, BeatTimeline.FillMethod.BY_INTERVAL, interval),
        )
        with Serve(Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD, response):
            with patch_yes_or_no_dialog(True):
                with undoable():
                    commands.execute("timeline.beat.fill")

        amount = int(tilia_state.duration / interval)
        assert len(beat_tlui) == amount


class TestDragBeatLimits:
    def test_drag_beyond_next_beat_cannot_pass_it(self, beat_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.beat.add", time=10)
        commands.execute("timeline.beat.add", time=20)
        commands.execute("timeline.beat.add", time=30)

        click_beat_ui(beat_tlui[1])
        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(40), 0)
            assert beat_tlui[1].get_data("time") < 30

    def test_drag_beyond_previous_beat_cannot_pass_it(self, beat_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.beat.add", time=10)
        commands.execute("timeline.beat.add", time=20)
        commands.execute("timeline.beat.add", time=30)

        click_beat_ui(beat_tlui[1])
        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(0), 0)
            assert beat_tlui[1].get_data("time") > 10

    def test_drag_beyond_timeline_end_is_clamped(self, beat_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.beat.add", time=90)

        click_beat_ui(beat_tlui[0])
        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(100) + 200, 0)
            assert beat_tlui[0].get_data("time") == 100

    def test_drag_beyond_timeline_start_is_clamped(self, beat_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.beat.add", time=10)

        click_beat_ui(beat_tlui[0])
        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(0) - 200, 0)
            assert beat_tlui[0].get_data("time") == 0
