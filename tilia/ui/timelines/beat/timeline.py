from __future__ import annotations
import logging
import copy

from tilia.requests import get, Get
from tilia.enums import Side
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.timeline import TimelineUI
from tilia.ui.timelines.beat.element import BeatUI
from tilia.ui.timelines.beat.request_handlers import BeatUIRequestHandler
from tilia.ui.timelines.beat.toolbar import BeatTimelineToolbar
from tilia.ui.timelines.collection.requests.enums import ElementSelector
from tilia.ui.timelines.copy_paste import (
    get_copy_data_from_element,
)

logger = logging.getLogger(__name__)


class BeatTimelineUI(TimelineUI):
    DEFAULT_HEIGHT = 35
    TOOLBAR_CLASS = BeatTimelineToolbar
    ELEMENT_CLASS = BeatUI
    TIMELINE_KIND = TimelineKind.BEAT_TIMELINE

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return BeatUIRequestHandler(self).on_request(request, selector, *args, **kwargs)

    def delete_selected_elements(self):
        if not self.selected_elements:
            return

        for component in self.selected_components:
            self.timeline.delete_components([component])

        self.timeline.recalculate_measures()

    def _deselect_all_but_last(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def _deselect_all_but_first(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[1:]:
                self.element_manager.deselect_element(element)

    def on_beat_position_change(self, id: int, is_first_in_measure: bool, label: str):
        """
        For when the position in relation to other beats changes.
        E.g. when a beat gets deleted or added.
        NOT for when the beat changes its *time*.
        For that, see on_beat_time_change.
        """
        beat_ui = self.id_to_element[id]
        beat_ui.update_is_first_in_measure(is_first_in_measure)
        beat_ui.label = label

    def on_beat_time_change(self, id: int):
        self.id_to_element[id].update_position()

    def should_display_measure_number(self, beat_ui):
        beat = self.timeline.get_component(beat_ui.id)
        beat_index = self.timeline.components.index(beat)
        measure_index, _ = self.timeline.get_measure_index(beat_index)
        return self.timeline.should_display_measure_number(measure_index)

    def on_side_arrow_press(self, side: Side):
        if not self.has_selected_elements:
            return

        if side == Side.RIGHT:
            self._deselect_all_but_last()
            selected_element = self.selected_elements[0]
            element_to_select = self.get_next_element(selected_element)
        elif side == Side.LEFT:
            self._deselect_all_but_first()
            selected_element = self.selected_elements[0]
            element_to_select = self.get_previous_element(selected_element)
        else:
            raise ValueError(f"Invalid side '{side}'.")

        if element_to_select:
            self.element_manager.deselect_element(selected_element)
            self.select_element(element_to_select)

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
            get(Get.MEDIA_CURRENT_TIME),
        )

    def create_pasted_beats(
        self, paste_data: list[dict], reference_time: float, target_time: float
    ) -> None:
        for beat_data in copy.deepcopy(
            paste_data
        ):  # deepcopying so popping won't affect original data
            beat_time = beat_data["support_by_component_value"].pop("time")

            self.timeline.create_timeline_component(
                ComponentKind.BEAT,
                target_time + (beat_time - reference_time),
                **beat_data["by_element_value"],
                **beat_data["by_component_value"],
                **beat_data["support_by_element_value"],
                **beat_data["support_by_component_value"],
            )
