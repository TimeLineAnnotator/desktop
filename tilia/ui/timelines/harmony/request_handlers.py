from __future__ import annotations

import tilia.errors
from tilia.requests import Post, get, Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.request_handlers import (
    ElementRequestHandler,
    TimelineRequestHandler,
)
from tilia.ui.timelines.copy_paste import get_copy_data_from_element
from tilia.ui.timelines.harmony import HarmonyUI, ModeUI


class HarmonyUIRequestHandler(ElementRequestHandler):
    def __init__(self, timeline_ui):
        super().__init__(
            timeline_ui,
            {
                Post.HARMONY_ADD: self.on_harmony_add,
                Post.HARMONY_DELETE: self.on_harmony_delete,
                Post.HARMONY_DISPLAY_AS_ROMAN_NUMERAL: self.on_display_as_roman_numeral,
                Post.HARMONY_DISPLAY_AS_CHORD_SYMBOL: self.on_display_as_chord_symbol,
                Post.MODE_ADD: self.on_mode_add,
                Post.MODE_DELETE: self.on_mode_delete,
                Post.TIMELINE_ELEMENT_DELETE: self.on_element_delete,
                Post.TIMELINE_ELEMENT_COPY: self.on_copy,
                Post.TIMELINE_ELEMENT_PASTE: self.on_paste,
            },
        )

    @staticmethod
    def filter_harmonies(elements: list[HarmonyUI | ModeUI]):
        return filter(lambda e: isinstance(e, HarmonyUI), elements)

    def on_mode_add(self, *_, **__):
        time = get(Get.SELECTED_TIME)
        valid, reason = self.timeline.component_manager._validate_component_creation(
            ComponentKind.MODE, time
        )

        if not valid:
            tilia.errors.display(tilia.errors.ADD_MODE_FAILED, reason)
            return

        confirmed, kwargs = get(Get.FROM_USER_MODE_PARAMS)
        if not confirmed:
            return
        mode, reason = self.timeline.create_component(
            ComponentKind.MODE, time, **kwargs
        )
        if not mode:
            tilia.errors.display(tilia.errors.ADD_MODE_FAILED, reason)
        self.timeline_ui.on_mode_add_done()

    def on_mode_delete(self, elements, *_, **__):
        self.timeline.delete_components(self.elements_to_components(elements))
        self.timeline_ui.on_mode_delete_done()

    def on_harmony_add(self, *_, **__):
        time = get(Get.SELECTED_TIME)
        valid, reason = self.timeline.component_manager._validate_component_creation(
            ComponentKind.HARMONY, time
        )

        if not valid:
            tilia.errors.display(tilia.errors.ADD_HARMONY_FAILED, reason)
            return

        confirmed, kwargs = get(Get.FROM_USER_HARMONY_PARAMS)
        if not confirmed:
            return

        harmony, reason = self.timeline.create_component(
            ComponentKind.HARMONY, time, **kwargs
        )

        if not harmony:
            tilia.errors.display(tilia.errors.ADD_HARMONY_FAILED, reason)

    def on_harmony_delete(self, elements, *_, **__):
        self.timeline.delete_components(self.elements_to_components(elements))

    def on_element_delete(self, elements, *_, **__):

        if any((elm for elm in elements if elm.get_data("KIND") == ComponentKind.MODE)):
            needs_recalculation = True
        else:
            needs_recalculation = False

        self.timeline.delete_components(self.elements_to_components(elements))

        if needs_recalculation:
            self.timeline_ui.on_mode_delete_done()

    def on_display_as_chord_symbol(self, elements, *_, **__):
        elements = self.filter_harmonies(elements)
        self.timeline_ui.set_elements_attr(elements, "display_mode", "chord")

    def on_display_as_roman_numeral(self, elements, *_, **__):
        elements = self.filter_harmonies(elements)
        self.timeline_ui.set_elements_attr(elements, "display_mode", "roman")

    @staticmethod
    def _get_copy_data_from_element(element: HarmonyUI | ModeUI):
        return {
            "components": get_copy_data_from_element(
                element, element.DEFAULT_COPY_ATTRIBUTES
            ),
            "timeline_kind": TimelineKind.HARMONY_TIMELINE,
        }

    def on_copy(self, elements):
        return [self._get_copy_data_from_element(e) for e in elements]


class HarmonyTimelineUIRequestHandler(TimelineRequestHandler):
    def __init__(self, timeline_ui):
        super().__init__(
            timeline_ui,
            {
                Post.HARMONY_TIMELINE_SHOW_KEYS: self.on_show_keys,
                Post.HARMONY_TIMELINE_HIDE_KEYS: self.on_hide_keys,
            },
        )

    def on_show_keys(self):
        get(Get.TIMELINE_COLLECTION).set_timeline_data(
            self.timeline_ui.id,
            "visible_level_count",
            2,
        )

    def on_hide_keys(self):
        get(Get.TIMELINE_COLLECTION).set_timeline_data(
            self.timeline_ui.id,
            "visible_level_count",
            1,
        )
