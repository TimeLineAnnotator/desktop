"""
Defines the tkinter ui corresponding a MarkerTimeline.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from tilia.timelines.component_kinds import ComponentKind
from tilia.events import Event, subscribe
from tilia.misc_enums import Side
from tilia.timelines.state_actions import Action

from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.ui.timelines.common import TimelineCanvas
    from tilia.ui.timelines.collection import TimelineUICollection

import logging

logger = logging.getLogger(__name__)

from tilia import events, settings
from tilia import ui
from tilia.ui.timelines.timeline import (
    TimelineUI,
    RightClickOption,
    TimelineUIElementManager,
)
from tilia.ui.timelines.marker.element import MarkerUI
from tilia.ui.timelines.marker.toolbar import MarkerTimelineToolbar

from tilia.ui.timelines.copy_paste import (
    Copyable,
    get_copy_data_from_element,
    paste_into_element,
)
from tilia.ui.element_kinds import UIElementKind


class MarkerTimelineUI(TimelineUI):
    DEFAULT_HEIGHT = settings.get("marker_timeline", "default_height")

    TOOLBAR_CLASS = MarkerTimelineToolbar
    ELEMENT_KINDS_TO_ELEMENT_CLASSES = {UIElementKind.MARKER_TKUI: MarkerUI}
    COMPONENT_KIND_TO_UIELEMENT_KIND = {ComponentKind.MARKER: UIElementKind.MARKER_TKUI}

    TIMELINE_KIND = TimelineKind.MARKER_TIMELINE

    def __init__(
        self,
        *args,
        timeline_ui_collection: TimelineUICollection,
        element_manager: TimelineUIElementManager,
        canvas: TimelineCanvas,
        toolbar: MarkerTimelineToolbar,
        name: str,
        height: int = DEFAULT_HEIGHT,
        is_visible: bool = True,
        **kwargs,
    ):

        super().__init__(
            *args,
            timeline_ui_collection=timeline_ui_collection,
            timeline_ui_element_manager=element_manager,
            component_kinds_to_classes=self.ELEMENT_KINDS_TO_ELEMENT_CLASSES,
            component_kinds_to_ui_element_kinds=self.COMPONENT_KIND_TO_UIELEMENT_KIND,
            canvas=canvas,
            toolbar=toolbar,
            name=name,
            height=height,
            is_visible=is_visible,
            **kwargs,
        )

    def _setup_user_actions_to_callbacks(self):

        self.action_to_callback = {
            "add": self.add_marker,
            "delete": self.delete_selected_elements,
        }

    def get_timeline_height(self):
        return self.height

    def add_marker(self):
        self.create_marker(self.timeline_ui_collection.get_current_playback_time())

    def create_marker(self, time: float, **kwargs) -> None:
        return self.timeline.create_timeline_component(
            ComponentKind.MARKER, time, **kwargs
        )

    def on_delete_marker_button(self):
        self.delete_selected_elements()

    def _deselect_all_but_last(self):
        ordered_selected_elements = sorted(
            self.element_manager.get_selected_elements(),
            key=lambda x: x.tl_component.time,
        )
        if len(ordered_selected_elements) > 1:
            for element in ordered_selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def on_side_arrow_press(self, side: Side):
        def _get_next_marker(elm):
            later_elements = self.element_manager.get_elements_by_condition(
                lambda m: m.time > elm.time, UIElementKind.MARKER_TKUI
            )
            if later_elements:
                return sorted(later_elements, key=lambda m: m.time)[0]
            else:
                return None

        def _get_previous_marker(elm):
            earlier_elements = self.element_manager.get_elements_by_condition(
                lambda m: m.time < elm.time, UIElementKind.MARKER_TKUI
            )
            if earlier_elements:
                return sorted(earlier_elements, key=lambda m: m.time)[-1]
            else:
                return None

        if not self.has_selected_elements:
            logger.debug(f"User pressed {side} arrow but no elements were selected.")
            return

        self._deselect_all_but_last()

        selected_element = self.element_manager.get_selected_elements()[0]
        if side == Side.RIGHT:
            element_to_select = _get_next_marker(selected_element)
        elif side == Side.LEFT:
            element_to_select = _get_previous_marker(selected_element)
        else:
            raise ValueError(f"Invalid side '{side}'.")

        if element_to_select:
            self.deselect_element(selected_element)
            self.select_element(element_to_select)
        elif side == Side.RIGHT:
            logger.debug(f"Selected element is last. Can't select next.")
        else:
            logger.debug(f"Selected element is first. Can't select previous.")

    def on_right_click_menu_option_click(self, option: RightClickOption):
        option_to_callback = {
            RightClickOption.CHANGE_TIMELINE_HEIGHT: self.right_click_menu_change_timeline_height,
            RightClickOption.CHANGE_TIMELINE_NAME: self.right_click_menu_change_timeline_name,
            RightClickOption.EDIT: self.right_click_menu_edit,
            RightClickOption.CHANGE_COLOR: self.right_click_menu_change_color,
            RightClickOption.RESET_COLOR: self.right_click_menu_reset_color,
            RightClickOption.COPY: self.right_click_menu_copy,
            RightClickOption.PASTE: self.right_click_menu_paste,
            RightClickOption.DELETE: self.right_click_menu_delete,
        }
        option_to_callback[option]()

    def right_click_menu_edit(self) -> None:
        self.deselect_all_elements()
        self.select_element(self.right_clicked_element)
        events.post(Event.UI_REQUEST_WINDOW_INSPECTOR)

    def right_click_menu_change_color(self) -> None:
        if color := ui.common.ask_for_color(self.right_clicked_element.color):
            self.right_clicked_element.color = color

    def right_click_menu_reset_color(self) -> None:
        self.right_clicked_element.reset_color()

    def right_click_menu_copy(self) -> None:
        events.post(
            Event.TIMELINE_COMPONENT_COPIED,
            self.get_copy_data_from_marker_uis([self.right_clicked_element]),
        )

    def right_click_menu_paste(self) -> None:
        self.element_manager.deselect_all_elements()
        self.element_manager.select_element(self.right_clicked_element)
        self.paste_single_into_selected_elements(
            self.timeline_ui_collection.get_elements_for_pasting()
        )

    def right_click_menu_delete(self) -> None:
        self.timeline.on_request_to_delete_components(
            [self.right_clicked_element.tl_component]
        )

    def validate_copy(self, elements: list[Copyable]) -> None:
        pass

    def get_copy_data_from_selected_elements(self):
        selected_elements = self.element_manager.get_selected_elements()

        self.validate_copy(selected_elements)

        return self.get_copy_data_from_marker_uis(selected_elements)

    def get_copy_data_from_marker_uis(self, marker_uis: list[MarkerUI]):

        copy_data = []
        for ui in marker_uis:
            copy_data.append(self.get_copy_data_from_marker_ui(ui))

        return copy_data

    @staticmethod
    def get_copy_data_from_marker_ui(marker_ui: MarkerUI):
        return get_copy_data_from_element(marker_ui, MarkerUI.DEFAULT_COPY_ATTRIBUTES)

    def paste_single_into_selected_elements(self, paste_data: list[dict] | dict):
        selected_elements = self.element_manager.get_selected_elements()

        self.validate_paste(paste_data, selected_elements)

        for element in self.element_manager.get_selected_elements():
            self.deselect_element(element)
            paste_into_element(element, paste_data[0])
            self.select_element(element)

        events.post(Event.REQUEST_RECORD_STATE, Action.PASTE)

    def paste_multiple_into_selected_elements(self, paste_data: list[dict] | dict):

        selected_elements = self.element_manager.get_selected_elements()
        self.validate_paste(paste_data, selected_elements)

        paste_data = sorted(
            paste_data, key=lambda md: md["support_by_component_value"]["time"]
        )
        selected_elements = sorted(selected_elements, key=lambda e: e.time)

        self.deselect_element(selected_elements[0])
        paste_into_element(selected_elements[0], paste_data[0])
        self.select_element(selected_elements[0])

        self.create_pasted_markers(
            paste_data[1:],
            paste_data[0]["support_by_component_value"]["time"],
            selected_elements[0].time,
        )

        events.post(Event.REQUEST_RECORD_STATE, Action.PASTE)

    def paste_single_into_timeline(self, paste_data: list[dict] | dict):
        return self.paste_multiple_into_timeline(paste_data)

    def paste_multiple_into_timeline(self, paste_data: list[dict] | dict):
        reference_time = min(
            md["support_by_component_value"]["time"] for md in paste_data
        )

        self.create_pasted_markers(
            paste_data,
            reference_time,
            self.timeline_ui_collection.get_current_playback_time(),
        )

        events.post(Event.REQUEST_RECORD_STATE, Action.PASTE)

    def create_pasted_markers(
        self, paste_data: list[dict], reference_time: float, target_time: float
    ) -> None:
        for marker_data in copy.deepcopy(
            paste_data
        ):  # deepcopying so popping won't affect original data
            marker_time = marker_data["support_by_component_value"].pop("time")

            self.create_marker(
                target_time + (marker_time - reference_time),
                **marker_data["by_element_value"],
                **marker_data["by_component_value"],
                **marker_data["support_by_element_value"],
                **marker_data["support_by_component_value"],
            )
