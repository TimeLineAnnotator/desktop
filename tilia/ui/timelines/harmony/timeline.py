from __future__ import annotations

import music21

from . import level_label
from tilia.requests import Get, get
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
    ACCEPTS_HORIZONTAL_ARROWS = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.UPDATE_TRIGGERS = self.UPDATE_TRIGGERS + [
            "level_count",
            "visible_level_count",
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

    def on_timeline_components_deserialized(self):
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
        self.harmony_level_label.set_position(get(Get.LEFT_MARGIN_X) - 5, self.get_y(1) - 5)
        self.key_level_label.setVisible(self.get_data("visible_level_count") == 2)

    def get_y(self, level: int):
        return self.get_data("level_height") * (
            self.get_data("visible_level_count") - level
        )

    def get_key_by_time(self, time: float) -> music21.key.Key:
        return self.timeline.get_key_by_time(time)

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
        if first_selected_element.kind == paste_data[0]["support_by_component_value"]['KIND']:
            self.deselect_element(self.selected_elements[0])
            paste_into_element(first_selected_element, paste_data[0])
            self.select_element(first_selected_element)

            self.create_pasted_components(
                paste_data[1:],
                paste_data[0]["support_by_component_value"]["time"],
                self.selected_elements[0].get_data("time"),
            )
        else:
            self.create_pasted_components(
                paste_data,
                paste_data[0]["support_by_component_value"]["time"],
                self.selected_elements[0].get_data("time"),
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

            self.timeline.create_component(
                harmony_data["support_by_component_value"]["KIND"],
                target_time + (harmony_time - reference_time),
                **harmony_data["by_component_value"],
            )
