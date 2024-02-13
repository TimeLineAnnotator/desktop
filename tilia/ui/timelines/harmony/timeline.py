from __future__ import annotations

import copy
import bisect

import music21

from . import level_label
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import Get, get
from tilia.enums import Side
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
)
from tilia.ui.timelines.collection.requests.enums import ElementSelector
from tilia.ui.timelines.harmony.context_menu import HarmonyTimelineUIContextMenu
from tilia.ui.timelines.harmony import HarmonyUI, ModeUI
from tilia.ui.timelines.harmony.request_handlers import (
    HarmonyUIRequestHandler,
    HarmonyTimelineUIRequestHandler,
)
from tilia.ui.timelines.harmony.toolbar import HarmonyTimelineToolbar

from tilia.ui.timelines.copy_paste import (
    paste_into_element,
)


class HarmonyTimelineUI(TimelineUI):
    TOOLBAR_CLASS = HarmonyTimelineToolbar
    ELEMENT_CLASS = [HarmonyUI, ModeUI]
    CONTEXT_MENU_CLASS = HarmonyTimelineUIContextMenu
    TIMELINE_KIND = TimelineKind.HARMONY_TIMELINE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.UPDATE_TRIGGERS = self.UPDATE_TRIGGERS + [
            "level_count",
            "visible_level_count",
            "level_height",
        ]
        self._setup_level_labels()

    def _setup_level_labels(self):
        self.harmony_level_label = level_label.LevelLabel(
            get(Get.LEFT_MARGIN_X) - 5, self.get_y(1) - 5, "Harmonies"
        )
        self.key_level_label = level_label.LevelLabel(
            get(Get.LEFT_MARGIN_X) - 5, self.get_y(2) - 5, "Keys"
        )

        self.scene.addItem(self.harmony_level_label)
        self.scene.addItem(self.key_level_label)

    def modes(self):
        return self.element_manager.get_elements_by_condition(
            lambda elm: isinstance(elm, ModeUI)
        )

    def harmonies(self):
        return self.element_manager.get_elements_by_condition(
            lambda elm: isinstance(elm, HarmonyUI)
        )

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return HarmonyUIRequestHandler(self).on_request(
            request, selector, *args, **kwargs
        )

    def on_timeline_request(self, request, *args, **kwargs):
        return HarmonyTimelineUIRequestHandler(self).on_request(
            request, *args, **kwargs
        )

    def on_mode_add_done(self):
        self.update_harmony_labels()

    def on_mode_delete_done(self):
        self.update_harmony_labels()

    def on_element_drag_done(self):
        self.update_harmony_labels()

    def update_harmony_labels(self):
        for harmony in self.harmonies():
            harmony.update_label()

    def update_level_count(self):
        self.update_height()

    def update_height(self):
        new_height = self.get_data("level_height") * self.get_data(
            "visible_level_count"
        )
        self.scene.set_height(new_height)
        self.view.set_height(new_height)
        self.element_manager.update_time_on_elements()

    def update_visible_level_count(self):
        self.update_height()
        self.element_manager.update_time_on_elements()
        self.update_level_labels()

    def update_level_labels(self):
        self.harmony_level_label.set_position(get(Get.LEFT_MARGIN_X) - 5, self.get_y(1))
        self.key_level_label.setVisible(self.get_data("visible_level_count") == 2)

    def get_y(self, level: int):
        return self.get_data("level_height") * (
            self.get_data("visible_level_count") - level
        )

    def get_key_by_time(self, time: float):
        return self.timeline.get_key_by_time(time)

    def _deselect_all_but_last(self):
        ordered_selected_elements = sorted(
            self.element_manager.get_selected_elements(),
            key=lambda x: x.tl_component.time,
        )
        if len(ordered_selected_elements) > 1:
            for element in ordered_selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def on_side_arrow_press(self, side: Side):
        def _get_next_harmony(elm):
            later_elements = self.element_manager.get_elements_by_condition(
                lambda m: m.time > elm.time
            )
            if later_elements:
                return sorted(later_elements, key=lambda m: m.time)[0]
            else:
                return None

        def _get_previous_harmony(elm):
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
            element_to_select = _get_next_harmony(selected_element)
        elif side == Side.LEFT:
            element_to_select = _get_previous_harmony(selected_element)
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
        selected_elements = self.element_manager.get_selected_elements()
        self.validate_paste(paste_data, selected_elements)

        paste_data = sorted(
            paste_data, key=lambda md: md["support_by_component_value"]["time"]
        )
        selected_elements = sorted(selected_elements)

        self.deselect_element(selected_elements[0])
        paste_into_element(selected_elements[0], paste_data[0])
        self.select_element(selected_elements[0])

        self.create_pasted_components(
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

        self.create_pasted_components(
            paste_data,
            reference_time,
            get(Get.MEDIA_CURRENT_TIME),
        )

    def create_pasted_components(
        self, paste_data: list[dict], reference_time: float, target_time: float
    ) -> None:
        for harmony_data in paste_data:
            harmony_time = harmony_data["support_by_component_value"]["time"]

            self.timeline.create_timeline_component(
                harmony_data["support_by_component_value"]["KIND"],
                target_time + (harmony_time - reference_time),
                **harmony_data["by_component_value"],
            )
