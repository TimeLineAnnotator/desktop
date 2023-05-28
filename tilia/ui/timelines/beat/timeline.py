"""
Defines the tkinter ui corresponding a BeatTimeline.
"""

from __future__ import annotations
import logging
import copy

import tilia.ui.common
from tilia.timelines.component_kinds import ComponentKind
from tilia.events import Event
from tilia.misc_enums import Side
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind
from tilia import events
from tilia.ui.timelines.timeline import (
    TimelineUI,
    RightClickOption,
)
from tilia.ui.timelines.beat.element import BeatUI
from tilia.ui.timelines.beat.toolbar import BeatTimelineToolbar
from tilia.ui.timelines.copy_paste import (
    get_copy_data_from_element,
)

logger = logging.getLogger(__name__)


class BeatTimelineUI(TimelineUI):
    DEFAULT_HEIGHT = 35
    TOOLBAR_CLASS = BeatTimelineToolbar
    ELEMENT_CLASS = BeatUI
    TIMELINE_KIND = TimelineKind.BEAT_TIMELINE

    def _setup_user_actions_to_callbacks(self):
        self.action_to_callback = {
            "add": self.add_beat,
            "delete": self.delete_selected_elements,
        }

    @property
    def ordered_elements(self):
        return sorted(self.elements, key=lambda b: b.time)

    @property
    def beats(self):
        return self.elements

    @property
    def ordered_selected_elements(self):
        return sorted(self.selected_elements, key=lambda b: b.time)

    def add_beat(self):
        self.create_beat(self.collection.get_current_playback_time())

    def create_beat(self, time: float, **kwargs) -> None:
        beat = self.timeline.create_timeline_component(
            ComponentKind.BEAT, time=time, **kwargs
        )
        self.timeline.recalculate_measures()

        return beat

    def delete_selected_elements(self):
        if not self.selected_elements:
            return

        for component in self.selected_components:
            self.timeline.on_request_to_delete_components([component])

        self.timeline.recalculate_measures()

    def _deselect_all_but_last(self):
        if len(self.ordered_selected_elements) > 1:
            for element in self.ordered_selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def _deselect_all_but_first(self):
        if len(self.ordered_selected_elements) > 1:
            for element in self.ordered_selected_elements[1:]:
                self.element_manager.deselect_element(element)

    def get_next_beat(self, elm):
        later_elements = self.element_manager.get_elements_by_condition(
            lambda m: m.time > elm.time
        )
        if later_elements:
            return sorted(later_elements, key=lambda m: m.time)[0]
        else:
            return None

    def get_previous_beat(self, elm):
        earlier_elements = self.element_manager.get_elements_by_condition(
            lambda m: m.time < elm.time
        )
        if earlier_elements:
            return sorted(earlier_elements, key=lambda m: m.time)[-1]
        else:
            return None

    def get_measure_number(self, beat_ui: BeatUI):
        beat_index = self.timeline.get_beat_index(beat_ui.tl_component)
        measure_index = self.timeline.get_measure_index(beat_index)

        return self.timeline.measure_numbers[measure_index]

    def on_beat_position_change(self, id: str, is_first_in_measure: bool, label: str):
        """
        For when the position in relation to other beats changes. E.g. when a beat gets deleted or added. NOT for when the beat changes its *time*. For that, see on_beat_time_change.
        """
        beat_ui = self.id_to_element[id]
        beat_ui.update_drawing_as_first_in_measure(is_first_in_measure)
        beat_ui.label = label

    def on_beat_time_change(self, id: str):
        self.id_to_element[id].update_position()

    def on_side_arrow_press(self, side: Side):
        if not self.has_selected_elements:
            logger.debug(f"User pressed left arrow but no elements were selected.")
            return

        if side == Side.RIGHT:
            self._deselect_all_but_last()
            selected_element = self.element_manager.get_selected_elements()[0]
            element_to_select = self.get_next_beat(selected_element)
        elif side == Side.LEFT:
            self._deselect_all_but_first()
            selected_element = self.element_manager.get_selected_elements()[0]
            element_to_select = self.get_previous_beat(selected_element)
        else:
            raise ValueError(f"Invalid side '{side}'.")

        if element_to_select:
            self.element_manager.deselect_element(selected_element)
            self.select_element(element_to_select)
        elif side == Side.RIGHT:
            logger.debug(f"Selected element is last. Can't select next.")
        else:
            logger.debug(f"Selected element is first. Can't select previous.")

    def on_right_click_menu_option_click(self, option: RightClickOption):
        option_to_callback = {
            RightClickOption.INSPECT: self.right_click_menu_inspect,
            RightClickOption.CHANGE_TIMELINE_HEIGHT: self.right_click_menu_change_timeline_height,
            RightClickOption.CHANGE_TIMELINE_NAME: self.right_click_menu_change_timeline_name,
            RightClickOption.CHANGE_MEASURE_NUMBER: self.right_click_menu_change_measure_number,
            RightClickOption.RESET_MEASURE_NUMBER: self.right_click_menu_reset_measure_number,
            RightClickOption.DISTRIBUTE_BEATS: self.right_click_menu_distribute_beats,
            RightClickOption.CHANGE_BEATS_IN_MEASURE: self.right_click_menu_change_beats_in_measure,
            RightClickOption.DELETE: self.right_click_menu_delete,
        }
        option_to_callback[option]()

    def right_click_menu_inspect(self) -> None:
        self.deselect_all_elements()
        self.select_element(self.right_clicked_element)
        events.post(Event.UI_REQUEST_WINDOW_INSPECTOR)

    def right_click_menu_change_measure_number(self):
        number = tilia.ui.common.ask_for_int(
            title="Change measure number", prompt="Change measure number to:"
        )

        if number <= 0:
            raise ValueError("Measure number must be a positive number.")

        beat_index = self.timeline.get_beat_index(
            self.right_clicked_element.tl_component
        )
        measure_index = self.timeline.get_measure_index(beat_index)
        self.timeline.change_measure_number(measure_index, number)

        events.post(Event.REQUEST_RECORD_STATE, Action.MEASURE_NUMBER_CHANGE)

    def right_click_menu_reset_measure_number(self):
        beat_index = self.timeline.get_beat_index(
            self.right_clicked_element.tl_component
        )
        measure_index = self.timeline.get_measure_index(beat_index)
        self.timeline.reset_measure_number(measure_index)

        events.post(Event.REQUEST_RECORD_STATE, Action.MEASURE_NUMBER_RESET)

    def right_click_menu_distribute_beats(self):
        beat_index = self.timeline.get_beat_index(
            self.right_clicked_element.tl_component
        )
        measure_index = self.timeline.get_measure_index(beat_index)
        self.timeline.distribute_beats(measure_index)

        events.post(Event.REQUEST_RECORD_STATE, Action.DISTRIBUTE_BEATS)

    def right_click_menu_change_beats_in_measure(self):
        number = tilia.ui.common.ask_for_int(
            title="Change beats in measure", prompt="Change beats in measure to:"
        )

        if number <= 0:
            raise ValueError("Beats in measure must be a positive number.")

        beat_index = self.timeline.get_beat_index(
            self.right_clicked_element.tl_component
        )
        measure_index = self.timeline.get_measure_index(beat_index)
        self.timeline.change_beats_in_measure(measure_index, number)

        events.post(Event.REQUEST_RECORD_STATE, Action.BEATS_IN_MEASURE_CHANGE)

    def right_click_menu_delete(self) -> None:
        self.timeline.on_request_to_delete_components(
            [self.right_clicked_element.tl_component]
        )

        self.timeline.recalculate_measures()

    def get_copy_data_from_selected_elements(self):
        self.validate_copy(self.selected_elements)

        return self.get_copy_data_from_beat_uis(self.selected_elements)

    def get_copy_data_from_beat_uis(self, beat_uis: list[BeatUI]):
        copy_data = []
        for ui in beat_uis:
            copy_data.append(self.get_copy_data_from_beat_ui(ui))

        return copy_data

    @staticmethod
    def get_copy_data_from_beat_ui(beat_ui: BeatUI):
        return get_copy_data_from_element(beat_ui, BeatUI.DEFAULT_COPY_ATTRIBUTES)

    def paste_single_into_timeline(self, paste_data: list[dict] | dict):
        return self.paste_multiple_into_timeline(paste_data)

    def paste_multiple_into_timeline(self, paste_data: list[dict] | dict):
        reference_time = min(
            md["support_by_component_value"]["time"] for md in paste_data
        )

        self.create_pasted_beats(
            paste_data,
            reference_time,
            self.collection.get_current_playback_time(),
        )

        events.post(Event.REQUEST_RECORD_STATE, Action.PASTE)

    def create_pasted_beats(
        self, paste_data: list[dict], reference_time: float, target_time: float
    ) -> None:
        for beat_data in copy.deepcopy(
            paste_data
        ):  # deepcopying so popping won't affect original data
            beat_time = beat_data["support_by_component_value"].pop("time")

            self.create_beat(
                target_time + (beat_time - reference_time),
                **beat_data["by_element_value"],
                **beat_data["by_component_value"],
                **beat_data["support_by_element_value"],
                **beat_data["support_by_component_value"],
            )
