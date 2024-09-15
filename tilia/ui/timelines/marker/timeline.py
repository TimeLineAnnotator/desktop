from __future__ import annotations

import copy

from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import Get, get, listen, Post
from tilia.enums import Side
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
)
from tilia.ui.timelines.collection.requests.enums import ElementSelector
from tilia.ui.timelines.marker.element import MarkerUI
from tilia.ui.timelines.marker.request_handlers import MarkerUIRequestHandler
from tilia.ui.timelines.marker.toolbar import MarkerTimelineToolbar

from tilia.ui.timelines.copy_paste import (
    paste_into_element,
)


class MarkerTimelineUI(TimelineUI):
    TOOLBAR_CLASS = MarkerTimelineToolbar
    ELEMENT_CLASS = MarkerUI
    ACCEPTS_HORIZONTAL_ARROWS = True

    TIMELINE_KIND = TimelineKind.MARKER_TIMELINE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listen(self, Post.SETTINGS_UPDATED, lambda updated_settings: self.on_settings_updated(updated_settings))

    def on_settings_updated(self, updated_settings):        
        if "marker_timeline" in updated_settings:  
            get(Get.TIMELINE_COLLECTION).set_timeline_data(self.id, "height", self.timeline.default_height)
            for marker_ui in self:
                marker_ui.update_time()
                marker_ui.update_color()


    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return MarkerUIRequestHandler(self).on_request(
            request, selector, *args, **kwargs
        )

    def _deselect_all_but_last(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def on_side_arrow_press(self, side: Side):
        if not self.has_selected_elements:
            return

        self._deselect_all_but_last()

        selected_element = self.element_manager.get_selected_elements()[0]
        if side == Side.RIGHT:
            element_to_select = self.get_next_element(selected_element)
        elif side == Side.LEFT:
            element_to_select = self.get_previous_element(selected_element)
        else:
            raise ValueError(f"Invalid side '{side}'.")

        if element_to_select:
            self.deselect_element(selected_element)
            self.select_element(element_to_select)

    def validate_copy(self, elements: list[TimelineUIElement]) -> None:
        pass

    def paste_single_into_selected_elements(self, paste_data: list[dict] | dict):
        selected_elements = self.element_manager.get_selected_elements()

        self.validate_paste(paste_data, selected_elements)

        for element in self.element_manager.get_selected_elements():
            self.deselect_element(element)
            paste_into_element(element, paste_data[0])
            self.select_element(element)

    def paste_multiple_into_selected_elements(self, paste_data: list[dict] | dict):
        self.validate_paste(paste_data, self.selected_elements)

        paste_data = sorted(
            paste_data, key=lambda md: md["support_by_component_value"]["time"]
        )

        first_selected_element = self.selected_elements[0]

        self.deselect_element(self.selected_elements[0])
        paste_into_element(first_selected_element, paste_data[0])
        self.select_element(first_selected_element)

        self.create_pasted_markers(
            paste_data[1:],
            paste_data[0]["support_by_component_value"]["time"],
            self.selected_elements[0].get_data("time"),
        )

    def paste_single_into_timeline(self, paste_data: list[dict] | dict):
        return self.paste_multiple_into_timeline(paste_data)

    def paste_multiple_into_timeline(self, paste_data: list[dict] | dict):
        reference_time = min(
            md["support_by_component_value"]["time"] for md in paste_data
        )

        self.create_pasted_markers(
            paste_data,
            reference_time,
            get(Get.SELECTED_TIME),
        )

    def create_pasted_markers(
        self, paste_data: list[dict], reference_time: float, target_time: float
    ) -> None:
        for marker_data in copy.deepcopy(paste_data):
            # deepcopying so popping won't affect original data
            marker_time = marker_data["support_by_component_value"].pop("time")

            self.timeline.create_component(
                ComponentKind.MARKER,
                target_time + (marker_time - reference_time),
                **marker_data["by_element_value"],
                **marker_data["by_component_value"],
                **marker_data["support_by_element_value"],
                **marker_data["support_by_component_value"],
            )
