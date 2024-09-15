from __future__ import annotations
import copy

from tilia.requests import get, Get, Post, listen
from tilia.enums import Side
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.timeline import TimelineUI
from tilia.ui.timelines.beat.context_menu import BeatTimelineUIContextMenu
from tilia.ui.timelines.beat.element import BeatUI
from tilia.ui.timelines.beat.request_handlers import BeatUIRequestHandler
from tilia.ui.timelines.beat.toolbar import BeatTimelineToolbar
from tilia.ui.timelines.collection.requests.enums import ElementSelector
from tilia.ui.timelines.copy_paste import (
    get_copy_data_from_element,
)


class BeatTimelineUI(TimelineUI):
    CONTEXT_MENU_CLASS = BeatTimelineUIContextMenu
    TOOLBAR_CLASS = BeatTimelineToolbar
    ELEMENT_CLASS = BeatUI
    ACCEPTS_HORIZONTAL_ARROWS = True
    TIMELINE_KIND = TimelineKind.BEAT_TIMELINE
    UPDATE_TRIGGERS = TimelineUI.UPDATE_TRIGGERS + [
        "beat_pattern",
        "measure_numbers",
        "beats_that_start_measures",
        "measures_to_force_display",
        "beats_in_measure"
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listen(self, Post.SETTINGS_UPDATED, lambda updated_settings: self.on_settings_updated(updated_settings))

    def on_settings_updated(self, updated_settings):        
        if "beat_timeline" in updated_settings:
            for beat_ui in self:
                beat_ui.update_label()

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return BeatUIRequestHandler(self).on_request(request, selector, *args, **kwargs)

    def _deselect_all_but_last(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def _deselect_all_but_first(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[1:]:
                self.element_manager.deselect_element(element)

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

            self.timeline.create_component(
                ComponentKind.BEAT,
                target_time + (beat_time - reference_time),
                **beat_data["by_element_value"],
                **beat_data["by_component_value"],
                **beat_data["support_by_element_value"],
                **beat_data["support_by_component_value"],
            )

    def update_beat_pattern(self):
        pass  # not implemented

    def update_measure_numbers(self):
        for beat_ui in self:
            beat_ui.update_label()

    def update_measures_to_force_display(self):
        for beat_ui in self:
            beat_ui.update_label()

    def update_beats_in_measure(self):
        for beat_ui in self:
            beat_ui.update_is_first_in_measure()

    def beats_that_start_measures(self):
        for beat_ui in self:
            beat_ui.update_is_first_in_measure()
