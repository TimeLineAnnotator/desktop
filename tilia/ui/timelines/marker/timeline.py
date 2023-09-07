from __future__ import annotations

import copy
import logging

from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import Get, get
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

logger = logging.getLogger(__name__)


class MarkerTimelineUI(TimelineUI):
    TOOLBAR_CLASS = MarkerTimelineToolbar
    ELEMENT_CLASS = MarkerUI

    TIMELINE_KIND = TimelineKind.MARKER_TIMELINE

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return MarkerUIRequestHandler(self).on_request(
            request, selector, *args, **kwargs
        )

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
                lambda m: m.time > elm.time
            )
            if later_elements:
                return sorted(later_elements, key=lambda m: m.time)[0]
            else:
                return None

        def _get_previous_marker(elm):
            earlier_elements = self.element_manager.get_elements_by_condition(
                lambda m: m.time < elm.time
            )
            if earlier_elements:
                return sorted(earlier_elements, key=lambda m: m.time)[-1]
            else:
                return None

        if not self.has_selected_elements:
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
            logger.debug("Selected element is last. Can't select next.")
        else:
            logger.debug("Selected element is first. Can't select previous.")

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
        selected_elements = self.element_manager.get_selected_elements()
        self.validate_paste(paste_data, selected_elements)

        paste_data = sorted(
            paste_data, key=lambda md: md["support_by_component_value"]["time"]
        )
        selected_elements = sorted(selected_elements)

        self.deselect_element(selected_elements[0])
        paste_into_element(selected_elements[0], paste_data[0])
        self.select_element(selected_elements[0])

        self.create_pasted_markers(
            paste_data[1:],
            paste_data[0]["support_by_component_value"]["time"],
            selected_elements[0].get_data("time"),
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
            get(Get.MEDIA_CURRENT_TIME),
        )

    def create_pasted_markers(
        self, paste_data: list[dict], reference_time: float, target_time: float
    ) -> None:
        for marker_data in copy.deepcopy(
            paste_data
        ):  # deepcopying so popping won't affect original data
            marker_time = marker_data["support_by_component_value"].pop("time")

            return self.timeline.create_timeline_component(
                ComponentKind.MARKER,
                target_time + (marker_time - reference_time),
                **marker_data["by_element_value"],
                **marker_data["by_component_value"],
                **marker_data["support_by_element_value"],
                **marker_data["support_by_component_value"],
            )
