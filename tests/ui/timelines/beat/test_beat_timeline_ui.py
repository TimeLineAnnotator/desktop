from unittest.mock import patch, MagicMock

from tests.mock import PatchGet, Serve
from tilia.requests import Post, post
from tilia.enums import Side
from tilia.requests import Get
from tilia.ui.actions import TiliaAction
from tilia.ui.windows import WindowKind


class TestCreateDeleteBeat:
    def test_create_single(self, beat_tlui):
        beat_tlui.create_beat(0)

        assert len(beat_tlui) == 1

    def test_create_multiple(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        assert len(beat_tlui) == 3

    def test_delete(self, beat_tlui, actions):
        beat_tlui.create_beat(0)
        beat_tlui.select_all_elements()

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(beat_tlui) == 0
        assert not beat_tlui.selected_elements


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
        beat_tlui.on_side_arrow_press(Side.RIGHT)
        assert beat_tlui.selected_elements == [beat1]

        beat_tlui.on_side_arrow_press(Side.RIGHT)
        assert beat_tlui.selected_elements == [beat1]

    def test_on_left_arrow_press_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]

        beat_tlui.select_element(beat1)
        beat_tlui.on_side_arrow_press(Side.LEFT)
        assert beat_tlui.selected_elements == [beat0]

        beat_tlui.on_side_arrow_press(Side.LEFT)
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

        beat_tlui.on_side_arrow_press(Side.RIGHT)
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

        beat_tlui.on_side_arrow_press(Side.LEFT)
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
            "by_component_value": {},
            "by_element_value": {},
            "support_by_component_value": {"time": 0},
            "support_by_element_value": {},
        }
        beat1_data = {
            "by_component_value": {},
            "by_element_value": {},
            "support_by_component_value": {"time": 0.1},
            "support_by_element_value": {},
        }
        beat2_data = {
            "by_component_value": {},
            "by_element_value": {},
            "support_by_component_value": {"time": 0.2},
            "support_by_element_value": {},
        }
        beat3_data = {
            "by_component_value": {},
            "by_element_value": {},
            "support_by_component_value": {"time": 0.3},
            "support_by_element_value": {},
        }
        assert beat0_data in copy_data
        assert beat1_data in copy_data
        assert beat2_data in copy_data
        assert beat3_data in copy_data

    def test_paste_single_into_selected_elements(self, beat_tlui, tluis, actions):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui.elements[0])

        tl_state0 = beat_tlui.timeline.get_state()

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        tl_state1 = beat_tlui.timeline.get_state()

        assert tl_state0 == tl_state1

    def test_paste_single_into_timeline(self, beat_tlui, tluis, actions):
        beat_tlui.create_beat(10)
        beat_tlui.select_element(beat_tlui[0])

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)

        beat_tlui.deselect_element(beat_tlui[0])

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert len(beat_tlui) == 2
        assert beat_tlui[0].time == 0

    def test_paste_multiple_into_timeline(self, beat_tlui, tluis, actions):
        beat_tlui.create_beat(10)
        beat_tlui.create_beat(11)
        beat_tlui.create_beat(12)
        beat_tlui.create_beat(13)

        beat_tlui.select_all_elements()

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)

        beat_tlui.deselect_all_elements()

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

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
            assert beat.get_data("measure_number") == expected_measure_numbers[i]


DUMMY_MEASURE_NUMBER = 11


class TestChangeMeasureNumber:
    @staticmethod
    def _set_measure_number(beat_tlui, actions, number=DUMMY_MEASURE_NUMBER):
        """Assumes there a beat in the measure is selected"""
        with Serve(Get.FROM_USER_INT, (number, True)):
            actions.trigger(TiliaAction.BEAT_SET_MEASURE_NUMBER)

    def test_set_measure_number_single_measure(self, beat_tlui, actions):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number(beat_tlui, actions)
        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_set_measure_number_twice(self, beat_tlui, actions):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number(beat_tlui, actions)
        self._set_measure_number(beat_tlui, actions, 101)
        assert beat_tlui.timeline.measure_numbers[0] == 101

    def test_set_measure_number_multiple_measures(self, beat_tlui, actions):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        beat_tlui.select_element(beat_tlui[3])
        self._set_measure_number(beat_tlui, actions)

        assert beat_tlui.timeline.measure_numbers[1] == DUMMY_MEASURE_NUMBER

    def test_set_measure_number_not_first_beat_in_measure(self, beat_tlui, actions):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        beat_tlui.select_element(beat_tlui[1])
        self._set_measure_number(beat_tlui, actions)

        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_undo_set_measure_number(self, beat_tlui, actions):
        actions.trigger(TiliaAction.BEAT_ADD)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number(beat_tlui, actions)
        actions.trigger(TiliaAction.EDIT_UNDO)
        assert beat_tlui.timeline.measure_numbers[0] == 1

    def test_redo_set_measure_number(self, beat_tlui, actions):
        actions.trigger(TiliaAction.BEAT_ADD)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number(beat_tlui, actions)
        actions.trigger(TiliaAction.EDIT_UNDO)
        actions.trigger(TiliaAction.EDIT_REDO)
        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_reset_measure_number(self, beat_tlui, actions):
        actions.trigger(TiliaAction.BEAT_ADD)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number(beat_tlui, actions)
        actions.trigger(TiliaAction.BEAT_RESET_MEASURE_NUMBER)
        assert beat_tlui.timeline.measure_numbers[0] == 1

    def test_undo_reset_measure_number(self, beat_tlui, actions):
        actions.trigger(TiliaAction.BEAT_ADD)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number(beat_tlui, actions)
        actions.trigger(TiliaAction.BEAT_RESET_MEASURE_NUMBER)
        actions.trigger(TiliaAction.EDIT_UNDO)
        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_redo_reset_measure_number(self, beat_tlui, actions):
        actions.trigger(TiliaAction.BEAT_ADD)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number(beat_tlui, actions)
        actions.trigger(TiliaAction.BEAT_RESET_MEASURE_NUMBER)
        actions.trigger(TiliaAction.EDIT_UNDO)
        actions.trigger(TiliaAction.EDIT_REDO)
        assert beat_tlui.timeline.measure_numbers[0] == 1


class TestActions:
    def test_inspect(self, qtui, beat_tlui, actions, tilia_state):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for element in beat_tlui:
            beat_tlui.select_element(element)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_INSPECT)

        assert tilia_state.is_window_open(qtui, WindowKind.INSPECT)

        actions.trigger(TiliaAction.INSPECT_WINDOW_CLOSE)

    def test_distribute_beats(self, beat_tlui, actions):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)
        beat_tlui.create_beat(3)
        beat_tlui.create_beat(8)

        beat_tlui.select_element(beat_tlui[0])

        actions.trigger(TiliaAction.BEAT_DISTRIBUTE)

        assert beat_tlui[1].get_data("time") == 2
        assert beat_tlui[2].get_data("time") == 4
        assert beat_tlui[3].get_data("time") == 6

    def test_distribute_beats_on_last_measure(self, beat_tlui, actions):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)

        beat_tlui.select_element(beat_tlui[0])

        actions.trigger(TiliaAction.BEAT_DISTRIBUTE)

        assert beat_tlui[0].get_data('time') == 0
        assert beat_tlui[1].get_data('time') == 1

    def test_change_beats_in_measure(self, beat_tlui, actions):
        beat_tlui.create_beat(0)

        beat_tlui.select_element(beat_tlui[0])

        beat_tlui.timeline.set_beat_amount_in_measure = MagicMock()
        with patch("tilia.ui.dialogs.basic.ask_for_int", lambda *_, **__: (11, True)):
            actions.trigger(TiliaAction.BEAT_SET_AMOUNT_IN_MEASURE)

        beat_tlui.timeline.set_beat_amount_in_measure.assert_called_with(0, 11)


class TestUndoRedo:
    def test_undo_redo_add_beat(self, beat_tlui, tluis, actions):
        post(Post.APP_RECORD_STATE, "test state")

        with PatchGet(
            "tilia.ui.timelines.beat.timeline", Get.MEDIA_CURRENT_TIME, 0.101
        ):
            actions.trigger(TiliaAction.BEAT_ADD)

        post(Post.EDIT_UNDO)
        assert len(beat_tlui) == 0

        post(Post.EDIT_REDO)
        assert len(beat_tlui) == 1

    def test_on_delete_beat_button(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui[0])
        post(Post.BEAT_DELETE)

        assert len(beat_tlui) == 0

    def test_on_delete_beat_button_multiple_beats(self, beat_tlui, tluis):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        beat_tlui.select_all_elements()

        post(Post.BEAT_DELETE)

        assert len(beat_tlui) == 0

    def test_undo_redo_delete_beat_multiple_beats(self, beat_tlui, tluis, actions):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for beat_ui in beat_tlui:
            beat_tlui.select_element(beat_ui)

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        post(Post.EDIT_UNDO)
        assert len(beat_tlui) == 3

        post(Post.EDIT_REDO)
        assert len(beat_tlui) == 0

    def test_undo_redo_delete_beat(self, beat_tlui, tluis, actions):
        # 'tlui_clct' is needed as it subscriber to toolbar event
        # and forwards it to beat timeline

        beat_tlui.create_beat(0)

        post(Post.APP_RECORD_STATE, "test state")

        beat_tlui.select_element(beat_tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        post(Post.EDIT_UNDO)
        assert len(beat_tlui) == 1

        post(Post.EDIT_REDO)
        assert len(beat_tlui) == 0
