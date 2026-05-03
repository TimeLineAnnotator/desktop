from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from tilia.requests import Get, Post, get, listen
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.ui.menus import MarkerMenu
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
)
from tilia.ui.timelines.collection.collection import TimelineSelector
from tilia.ui.timelines.copy_paste import (
    paste_into_element,
)
from tilia.ui.timelines.marker.context_menu import MarkerTimelineUIContextMenu
from tilia.ui.timelines.marker.element import MarkerUI
from tilia.ui.timelines.marker.toolbar import MarkerTimelineToolbar

if TYPE_CHECKING:
    from tilia.ui.timelines.base.timeline import TimelineUIs


class MarkerTimelineUI(TimelineUI):
    TOOLBAR_CLASS = MarkerTimelineToolbar
    ELEMENT_CLASS = MarkerUI
    ACCEPTS_HORIZONTAL_ARROWS = True
    CONTEXT_MENU_CLASS = MarkerTimelineUIContextMenu
    timeline_class = MarkerTimeline
    menu_class = MarkerMenu

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listen(
            self,
            Post.SETTINGS_UPDATED,
            self.on_settings_updated,
        )

    def on_settings_updated(self, updated_settings):
        if "marker_timeline" in updated_settings:
            get(Get.TIMELINE_COLLECTION).set_timeline_data(
                self.id, "height", self.timeline.default_height
            )
            for marker_ui in self:
                marker_ui.update_time()
                marker_ui.update_color()

    @classmethod
    def register_commands(cls, collection: TimelineUIs):
        cls.register_timeline_command(
            collection,
            "add",
            cls.on_add,
            TimelineSelector.FIRST,
            text="Add marker at current position",
            shortcut="m",
            icon="marker-add",
        )

    def on_add(self, time: float | None = None):
        if time is None:
            time = get(Get.SELECTED_TIME)
        component, failure_reason = self.timeline.create_component(
            ComponentKind.MARKER, time
        )
        return bool(component)

    def _deselect_all_but_last(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def paste_single_into_selected_elements(self, paste_data: list[dict] | dict):
        for element in self.element_manager.get_selected_elements():
            self.deselect_element(element)
            paste_into_element(element, paste_data[0])
            self.select_element(element)

    def paste_multiple_into_selected_elements(self, paste_data: list[dict] | dict):
        paste_data = sorted(paste_data, key=lambda md: md["context"]["time"])

        first_selected_element = self.selected_elements[0]

        self.deselect_element(self.selected_elements[0])
        paste_into_element(first_selected_element, paste_data[0])
        self.select_element(first_selected_element)

        self.create_pasted_markers(
            paste_data[1:],
            paste_data[0]["context"]["time"],
            self.selected_elements[0].get_data("time"),
        )

    def paste_single_into_timeline(self, paste_data: list[dict] | dict):
        return self.paste_multiple_into_timeline(paste_data)

    def paste_multiple_into_timeline(self, paste_data: list[dict] | dict):
        reference_time = min(md["context"]["time"] for md in paste_data)

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
            marker_time = marker_data["context"].pop("time")

            self.timeline.create_component(
                ComponentKind.MARKER,
                target_time + (marker_time - reference_time),
                **marker_data["values"],
                **marker_data["context"],
            )
