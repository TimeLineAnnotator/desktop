from unittest.mock import patch, MagicMock

import pytest

from tests.mock import PatchGet
from tilia.requests import Post, post
from tilia.exceptions import CreateComponentError
from tilia.enums import Side
from tilia.requests import Get
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.windows import WindowKind


class TestBeatTimelineUI:
    def test_init(self, beat_tlui):
        assert beat_tlui

    def test_create_beat(self, beat_tlui):
        beat_tlui.create_beat(0)

        assert len(beat_tlui.elements) == 1

    def test_create_multiple_beats(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        assert len(beat_tlui.elements) == 3

    @patch("tkinter.messagebox.showerror")
    def test_create_beat_at_same_time_raises_error(self, showerror_mock, beat_tlui):
        beat_tlui.create_beat(0)
        with pytest.raises(CreateComponentError):
            beat_tlui.create_beat(0)

    def test_deselect_all_but_last(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for element in beat_tlui.elements:
            beat_tlui.select_element(element)

        beat_tlui._deselect_all_but_last()

        assert beat_tlui.selected_elements == [beat_tlui.ordered_elements[-1]]

    def test_deselect_all_but_first(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for element in beat_tlui.elements:
            beat_tlui.select_element(element)

        beat_tlui._deselect_all_but_first()

        assert beat_tlui.selected_elements == [beat_tlui.ordered_elements[0]]

    def test_get_next_beat(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui.ordered_elements[0]
        beat1 = beat_tlui.ordered_elements[1]
        assert beat_tlui.get_next_beat(beat0) == beat1
        assert beat_tlui.get_next_beat(beat1) is None

    def test_get_previous_beat(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui.ordered_elements[0]
        beat1 = beat_tlui.ordered_elements[1]
        assert beat_tlui.get_previous_beat(beat1) == beat0
        assert beat_tlui.get_previous_beat(beat0) is None

    def test_get_measure_number(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

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

        for i, beat in enumerate(beat_tlui.ordered_elements):
            assert beat_tlui.get_measure_number(beat) == expected_measure_numbers[i]

    def test_on_right_arrow_press_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui.ordered_elements[0]
        beat1 = beat_tlui.ordered_elements[1]

        beat_tlui.select_element(beat0)
        beat_tlui.on_side_arrow_press(Side.RIGHT)
        assert beat_tlui.selected_elements == [beat1]

        beat_tlui.on_side_arrow_press(Side.RIGHT)
        assert beat_tlui.selected_elements == [beat1]

    def test_on_left_arrow_press_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui.ordered_elements[0]
        beat1 = beat_tlui.ordered_elements[1]

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

        beat0 = beat_tlui.ordered_elements[0]
        beat1 = beat_tlui.ordered_elements[1]
        beat2 = beat_tlui.ordered_elements[2]
        beat3 = beat_tlui.ordered_elements[3]

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

        beat0 = beat_tlui.ordered_elements[0]
        beat1 = beat_tlui.ordered_elements[1]
        beat2 = beat_tlui.ordered_elements[2]
        beat3 = beat_tlui.ordered_elements[3]

        beat_tlui.select_element(beat1)
        beat_tlui.select_element(beat2)
        beat_tlui.select_element(beat3)

        beat_tlui.on_side_arrow_press(Side.LEFT)
        assert beat_tlui.selected_elements == [beat0]

    def test_on_right_click_menu_inspect(self, tkui, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for element in beat_tlui.elements:
            beat_tlui.select_element(element)

        beat0 = beat_tlui.ordered_elements[0]

        beat_tlui.right_clicked_element = beat0
        beat_tlui.right_click_menu_inspect()

        assert beat_tlui.selected_elements == [beat0]
        assert tkui._windows[WindowKind.INSPECT]

        tkui._windows[WindowKind.INSPECT].destroy()

    def test_right_click_menu_change_measure_number_single_measure(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat0 = beat_tlui.ordered_elements[0]

        beat_tlui.right_clicked_element = beat0

        with PatchGet("tilia.ui.timelines.beat.timeline", Get.INT_FROM_USER, 11):
            beat_tlui.right_click_menu_change_measure_number()

        assert beat_tlui.timeline.measure_numbers[0] == 11

    def test_right_click_menu_change_measure_number_multiple_measures(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        target_beat = beat_tlui.ordered_elements[3]
        beat_tlui.right_clicked_element = target_beat

        with PatchGet("tilia.ui.timelines.beat.timeline", Get.INT_FROM_USER, 11):
            beat_tlui.right_click_menu_change_measure_number()

        assert beat_tlui.timeline.measure_numbers[1] == 11

    def test_right_click_menu_change_measure_number_not_first_beat_in_measure(
        self, beat_tlui
    ):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        target_beat = beat_tlui.ordered_elements[1]
        beat_tlui.right_clicked_element = target_beat

        with PatchGet("tilia.ui.timelines.beat.timeline", Get.INT_FROM_USER, 11):
            beat_tlui.right_click_menu_change_measure_number()

        assert beat_tlui.timeline.measure_numbers[0] == 11

    def test_right_click_menu_reset_measure_number(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat0 = beat_tlui.ordered_elements[0]

        beat_tlui.timeline.measure_numbers[0] = 11

        beat_tlui.right_clicked_element = beat0

        beat_tlui.right_click_menu_reset_measure_number()

        assert beat_tlui.timeline.measure_numbers[0] == 1

    def test_right_click_menu_distribute_beats(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        beat_tlui.create_beat(0.3)
        beat_tlui.create_beat(0.8)

        beat0 = beat_tlui.ordered_elements[0]
        beat_tlui.right_clicked_element = beat0

        beat_tlui.right_click_menu_distribute_beats()

        assert beat_tlui.ordered_elements[1].time == pytest.approx(0.2)
        assert beat_tlui.ordered_elements[2].time == pytest.approx(0.4)
        assert beat_tlui.ordered_elements[3].time == pytest.approx(0.6)

    def test_change_beats_in_measure(self, beat_tlui):
        beat_tlui.create_beat(0)

        beat0 = beat_tlui.ordered_elements[0]
        beat_tlui.right_clicked_element = beat0

        beat_tlui.timeline.change_beats_in_measure = MagicMock()
        with PatchGet("tilia.ui.timelines.beat.timeline", Get.INT_FROM_USER, 11):
            beat_tlui.right_click_menu_change_beats_in_measure()

        beat_tlui.timeline.change_beats_in_measure.assert_called_with(0, 11)

    def test_right_click_menu_delete(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat0 = beat_tlui.ordered_elements[0]
        beat_tlui.right_clicked_element = beat0

        beat_tlui.right_click_menu_delete()

        assert not beat_tlui.elements
        assert not beat_tlui.selected_elements

    def test_get_copy_data_from_beat_uis(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        beat_tlui.create_beat(0.3)

        for beat in beat_tlui.elements:
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

    def test_paste_single_into_selected_elements(self, beat_tlui, tluis):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui.elements[0])

        tl_state0 = beat_tlui.timeline.get_state()

        tluis._on_request_to_copy()
        tluis._on_request_to_paste()

        tl_state1 = beat_tlui.timeline.get_state()

        assert tl_state0 == tl_state1

    def test_paste_multiple_into_selected_elements(self, beat_tlui, tluis):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.select_element(beat_tlui.elements[0])
        beat_tlui.select_element(beat_tlui.elements[1])

        tl_state0 = beat_tlui.timeline.get_state()

        tluis._on_request_to_copy()
        tluis._on_request_to_paste()

        tl_state1 = beat_tlui.timeline.get_state()

        assert tl_state0 == tl_state1

    def test_paste_single_into_timeline(self, beat_tlui, tluis):
        with PatchGet(
            "tilia.ui.timelines.beat.timeline", Get.CURRENT_PLAYBACK_TIME, 0.5
        ):
            beat_tlui.create_beat(0)
            beat_tlui.select_element(beat_tlui.elements[0])

            tluis._on_request_to_copy()

            beat_tlui.deselect_element(beat_tlui.elements[0])

            tluis._on_request_to_paste()

            assert len(beat_tlui.elements) == 2
            assert beat_tlui.ordered_elements[1].time == 0.5

    def test_paste_multiple_into_timeline(self, beat_tlui, tluis):
        with PatchGet(
            "tilia.ui.timelines.beat.timeline", Get.CURRENT_PLAYBACK_TIME, 0.4
        ):
            beat_tlui.create_beat(0)
            beat_tlui.create_beat(0.1)
            beat_tlui.create_beat(0.2)
            beat_tlui.create_beat(0.3)

            for element in beat_tlui.elements:
                beat_tlui.select_element(element)

            tluis._on_request_to_copy()

            beat_tlui.deselect_all_elements()

            tluis._on_request_to_paste()

            assert len(beat_tlui.elements) == 8
            assert beat_tlui.ordered_elements[4].time == pytest.approx(0.4)
            assert beat_tlui.ordered_elements[5].time == pytest.approx(0.5)
            assert beat_tlui.ordered_elements[6].time == pytest.approx(0.6)
            assert beat_tlui.ordered_elements[7].time == pytest.approx(0.7)

    def test_on_add_beat_button(self, beat_tlui, tluis):
        with PatchGet(
            "tilia.ui.timelines.beat.timeline", Get.CURRENT_PLAYBACK_TIME, 0.101
        ):
            post(Post.BEAT_TOOLBAR_BUTTON_ADD)

        assert len(beat_tlui.elements) == 1
        assert list(beat_tlui.elements)[0].time == 0.101

    def test_undo_redo_add_beat(self, beat_tlui, tluis):
        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        with PatchGet(
            "tilia.ui.timelines.beat.timeline", Get.CURRENT_PLAYBACK_TIME, 0.101
        ):
            tluis.on_timeline_toolbar_button(TlKind.BEAT_TIMELINE, "add")

        post(Post.REQUEST_TO_UNDO)
        assert len(beat_tlui.elements) == 0

        post(Post.REQUEST_TO_REDO)
        assert len(beat_tlui.elements) == 1

    def test_on_delete_beat_button(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(list(beat_tlui.elements)[0])
        post(Post.BEAT_TOOLBAR_BUTTON_DELETE)

        assert len(beat_tlui.elements) == 0

    def test_on_delete_beat_button_multiple_beats(self, beat_tlui, tluis):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for beat_ui in list(beat_tlui.elements):
            beat_tlui.select_element(beat_ui)

        post(Post.BEAT_TOOLBAR_BUTTON_DELETE)

        assert len(beat_tlui.elements) == 0

    def test_undo_redo_delete_beat_multiple_beats(self, beat_tlui, tluis):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for beat_ui in list(beat_tlui.elements):
            beat_tlui.select_element(beat_ui)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tluis.on_timeline_toolbar_button(TlKind.BEAT_TIMELINE, "delete")

        post(Post.REQUEST_TO_UNDO)
        assert len(beat_tlui.elements) == 3

        post(Post.REQUEST_TO_REDO)
        assert len(beat_tlui.elements) == 0

    def test_undo_redo_delete_beat(self, beat_tlui, tluis):
        # 'tlui_clct' is needed as it subscriber to toolbar event
        # and forwards it to beat timeline

        beat_tlui.create_beat(0)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        beat_tlui.select_element(list(beat_tlui.elements)[0])
        tluis.on_timeline_toolbar_button(TlKind.BEAT_TIMELINE, "delete")

        post(Post.REQUEST_TO_UNDO)
        assert len(beat_tlui.elements) == 1

        post(Post.REQUEST_TO_REDO)
        assert len(beat_tlui.elements) == 0
