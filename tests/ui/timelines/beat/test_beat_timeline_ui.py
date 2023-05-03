from unittest.mock import patch, MagicMock

import pytest

from tilia import events
from tilia.events import Event
from tilia.exceptions import CreateComponentError
from tilia.misc_enums import Side
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.timelines.beat.timeline import BeatTimelineUI
from tilia.timelines.create import create_timeline
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
        assert beat_tlui.get_next_beat(beat1) == None

    def test_get_previous_beat(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui.ordered_elements[0]
        beat1 = beat_tlui.ordered_elements[1]
        assert beat_tlui.get_previous_beat(beat1) == beat0
        assert beat_tlui.get_previous_beat(beat0) == None

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

    @patch("tilia.ui.common.ask_for_int")
    def test_right_click_menu_change_measure_number_single_measure(
        self, ask_int_mock, beat_tlui
    ):
        ask_int_mock.return_value = 11

        beat_tlui.create_beat(0)
        beat0 = beat_tlui.ordered_elements[0]

        beat_tlui.right_clicked_element = beat0

        beat_tlui.right_click_menu_change_measure_number()

        assert beat_tlui.timeline.measure_numbers[0] == 11

    @patch("tilia.ui.common.ask_for_int")
    def test_right_click_menu_change_measure_number_multiple_measures(
        self, ask_int_mock, beat_tlui
    ):
        ask_int_mock.return_value = 11
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        target_beat = beat_tlui.ordered_elements[3]
        beat_tlui.right_clicked_element = target_beat

        beat_tlui.right_click_menu_change_measure_number()

        assert beat_tlui.timeline.measure_numbers[1] == 11

    @patch("tilia.ui.common.ask_for_int")
    def test_right_click_menu_change_measure_number_not_first_beat_in_measure(
        self, ask_int_mock, beat_tlui
    ):
        ask_int_mock.return_value = 11
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        target_beat = beat_tlui.ordered_elements[1]
        beat_tlui.right_clicked_element = target_beat

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

    @patch("tilia.ui.common.ask_for_int")
    def test_change_beats_in_measure(self, ask_int_mock, beat_tlui):
        ask_int_mock.return_value = 11
        beat_tlui.create_beat(0)

        beat0 = beat_tlui.ordered_elements[0]
        beat_tlui.right_clicked_element = beat0

        beat_tlui.timeline.change_beats_in_measure = MagicMock()
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

    def test_paste_single_into_selected_elements(self, beat_tlui, tlui_clct):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui.elements[0])

        tl_state0 = beat_tlui.timeline.get_state()

        tlui_clct._on_request_to_copy()
        tlui_clct._on_request_to_paste()

        tl_state1 = beat_tlui.timeline.get_state()

        assert tl_state0 == tl_state1

    def test_paste_multiple_into_selected_elements(self, beat_tlui, tlui_clct):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.select_element(beat_tlui.elements[0])
        beat_tlui.select_element(beat_tlui.elements[1])

        tl_state0 = beat_tlui.timeline.get_state()

        tlui_clct._on_request_to_copy()
        tlui_clct._on_request_to_paste()

        tl_state1 = beat_tlui.timeline.get_state()

        assert tl_state0 == tl_state1

    @patch(
        "tilia.ui.timelines.collection.TimelineUICollection.get_current_playback_time"
    )
    def test_paste_single_into_timeline(self, playback_time_mock, beat_tlui, tlui_clct):
        playback_time_mock.return_value = 0.5

        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui.elements[0])

        tlui_clct._on_request_to_copy()

        beat_tlui.deselect_element(beat_tlui.elements[0])

        tlui_clct._on_request_to_paste()

        assert len(beat_tlui.elements) == 2
        assert beat_tlui.ordered_elements[1].time == 0.5

    @patch(
        "tilia.ui.timelines.collection.TimelineUICollection.get_current_playback_time"
    )
    def test_paste_multiple_into_timeline(
        self, playback_time_mock, beat_tlui, tlui_clct
    ):
        playback_time_mock.return_value = 0.4

        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        beat_tlui.create_beat(0.3)

        for element in beat_tlui.elements:
            beat_tlui.select_element(element)

        tlui_clct._on_request_to_copy()

        beat_tlui.deselect_all_elements()

        tlui_clct._on_request_to_paste()

        assert len(beat_tlui.elements) == 8
        assert beat_tlui.ordered_elements[4].time == pytest.approx(0.4)
        assert beat_tlui.ordered_elements[5].time == pytest.approx(0.5)
        assert beat_tlui.ordered_elements[6].time == pytest.approx(0.6)
        assert beat_tlui.ordered_elements[7].time == pytest.approx(0.7)

    def test_on_add_beat_button(self, beat_tlui, tlui_clct):
        with patch(
            "tilia.ui.timelines.collection.TimelineUICollection.get_current_playback_time",
            lambda _: 0.101,
        ):
            events.post(Event.BEAT_TOOLBAR_BUTTON_ADD)

        assert len(beat_tlui.elements) == 1
        assert list(beat_tlui.elements)[0].time == 0.101

    def test_undo_redo_add_beat(self, beat_tlui, tlui_clct):
        events.post(Event.REQUEST_RECORD_STATE, Action.TEST_STATE)

        with patch(
            "tilia.ui.timelines.collection.TimelineUICollection.get_current_playback_time",
            lambda _: 0.101,
        ):
            tlui_clct.on_timeline_toolbar_button(TlKind.BEAT_TIMELINE, "add")

        events.post(Event.REQUEST_TO_UNDO)
        assert len(beat_tlui.elements) == 0

        events.post(Event.REQUEST_TO_REDO)
        assert len(beat_tlui.elements) == 1

    def test_on_delete_beat_button(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(list(beat_tlui.elements)[0])
        events.post(Event.BEAT_TOOLBAR_BUTTON_DELETE)

        assert len(beat_tlui.elements) == 0

    def test_on_delete_beat_button_multiple_beats(self, beat_tlui, tlui_clct):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for beat_ui in list(beat_tlui.elements):
            beat_tlui.select_element(beat_ui)

        events.post(Event.BEAT_TOOLBAR_BUTTON_DELETE)

        assert len(beat_tlui.elements) == 0

    def test_undo_redo_delete_beat_multiple_beats(self, beat_tlui, tlui_clct):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for beat_ui in list(beat_tlui.elements):
            beat_tlui.select_element(beat_ui)

        events.post(Event.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tlui_clct.on_timeline_toolbar_button(TlKind.BEAT_TIMELINE, "delete")

        events.post(Event.REQUEST_TO_UNDO)
        assert len(beat_tlui.elements) == 3

        events.post(Event.REQUEST_TO_REDO)
        assert len(beat_tlui.elements) == 0

    def test_undo_redo_delete_beat(self, beat_tlui, tlui_clct):
        # 'tlui_clct' is needed as it subscriber to toolbar event
        # and forwards it to beat timeline

        beat_tlui.create_beat(0)

        events.post(Event.REQUEST_RECORD_STATE, Action.TEST_STATE)

        beat_tlui.select_element(list(beat_tlui.elements)[0])
        tlui_clct.on_timeline_toolbar_button(TlKind.BEAT_TIMELINE, "delete")

        events.post(Event.REQUEST_TO_UNDO)
        assert len(beat_tlui.elements) == 1

        events.post(Event.REQUEST_TO_REDO)
        assert len(beat_tlui.elements) == 0
