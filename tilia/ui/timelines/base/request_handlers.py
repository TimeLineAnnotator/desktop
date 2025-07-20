from __future__ import annotations

import functools
from typing import Callable, Iterator

from tilia.requests import Post, get, Get, post
from tilia.ui.enums import PasteCardinality
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.request_handler import RequestHandler
from tilia.ui.timelines.copy_paste import get_copy_data_from_element


class TimelineRequestHandler(RequestHandler):
    def __init__(self, timeline_ui, request_to_callback: dict[Post, Callable]):
        base_request_to_callback = {
            Post.TIMELINE_CLEAR_FROM_MANAGE_TIMELINES: self.on_timeline_clear,
            Post.TIMELINE_DELETE_FROM_MANAGE_TIMELINES: self.on_timeline_delete,
            Post.TIMELINE_DELETE_FROM_CONTEXT_MENU: self.on_timeline_delete,
            Post.TIMELINE_DELETE_FROM_CLI: self.on_timeline_delete,
            Post.TIMELINE_NAME_SET: self.on_timeline_name_set,
            Post.TIMELINE_HEIGHT_SET: self.on_timeline_height_set,
            Post.TIMELINE_IS_VISIBLE_SET_FROM_MANAGE_TIMELINES: functools.partial(
                self.on_timeline_data_set, "is_visible"
            ),
        }
        super().__init__(
            request_to_callback=request_to_callback | base_request_to_callback
        )
        self.timeline_ui = timeline_ui

    @property
    def timeline(self):
        return get(Get.TIMELINE, self.timeline_ui.id)

    def on_timeline_name_set(self):
        accepted, name = get(
            Get.FROM_USER_STRING,
            "Change timeline name",
            "Choose new name",
            text=get(Get.TIMELINE, self.timeline_ui.id).name,
        )
        if not accepted:
            return False

        return self.on_timeline_data_set("name", name)

    def on_timeline_height_set(self):
        accepted, height = get(
            Get.FROM_USER_INT,
            "Change timeline height",
            "Insert new timeline height",
            value=self.timeline_ui.get_data("height"),
            min=10,
        )
        if not accepted:
            return False

        return self.on_timeline_data_set("height", height)

    def on_timeline_data_set(self, attr, value, **_):
        return get(Get.TIMELINE_COLLECTION).set_timeline_data(
            self.timeline_ui.id, attr, value
        )

    def on_timeline_delete(self):
        confirmed = get(
            Get.FROM_USER_YES_OR_NO,
            "Delete timeline",
            "Are you sure you want to delete the selected timeline? This can be undone later.",
        )

        if not confirmed:
            return False
        get(Get.TIMELINE_COLLECTION).delete_timeline(self.timeline_ui.timeline)
        return True

    def on_timeline_clear(self):
        confirmed = get(
            Get.FROM_USER_YES_OR_NO,
            "Clear timeline",
            "Are you sure you want to clear the selected timeline? This can be undone later.",
        )
        if not confirmed:
            return False
        get(Get.TIMELINE_COLLECTION).clear_timeline(self.timeline_ui.timeline)
        return True


class ElementRequestHandler(RequestHandler):
    def __init__(self, timeline_ui, request_to_callback: dict[Post, Callable]):
        base_request_to_callback = {}
        super().__init__(
            request_to_callback=request_to_callback | base_request_to_callback
        )
        self.timeline_ui = timeline_ui

    def on_request(self, request, selector, *args, **kwargs):
        return self.request_to_callback[request](
            self.timeline_ui.get_elements_by_selector(selector), *args, **kwargs
        )

    @property
    def timeline(self):
        return get(Get.TIMELINE, self.timeline_ui.id)

    @staticmethod
    def elements_to_components(elements: Iterator[TimelineUIElement]):
        return [e.tl_component for e in elements]

    def on_copy(self, elements: list[TimelineUIElement]):
        component_data = [
            get_copy_data_from_element(e, e.DEFAULT_COPY_ATTRIBUTES) for e in elements
        ]

        if not component_data:
            return False

        post(
            Post.TIMELINE_ELEMENT_COPY_DONE,
            {"components": component_data, "timeline_kind": self.timeline.KIND},
        )
        return True

    def on_paste(self, *_, **__):
        clipboard_contents = get(Get.CLIPBOARD_CONTENTS)
        components = clipboard_contents["components"]
        cardinality = (
            PasteCardinality.MULTIPLE
            if len(clipboard_contents["components"]) > 1
            else PasteCardinality.SINGLE
        )
        if self.timeline_ui.has_selected_elements:
            if cardinality == PasteCardinality.SINGLE and hasattr(
                self.timeline_ui, "paste_single_into_selected_elements"
            ):
                self.timeline_ui.paste_single_into_selected_elements(components)
            elif cardinality == PasteCardinality.MULTIPLE and hasattr(
                self.timeline_ui, "paste_multiple_into_selected_elements"
            ):
                self.timeline_ui.paste_multiple_into_selected_elements(components)
        else:
            if cardinality == PasteCardinality.SINGLE and hasattr(
                self.timeline_ui, "paste_single_into_timeline"
            ):
                self.timeline_ui.paste_single_into_timeline(components)
            elif cardinality == PasteCardinality.MULTIPLE and hasattr(
                self.timeline_ui, "paste_multiple_into_timeline"
            ):
                self.timeline_ui.paste_multiple_into_timeline(components)

        return True
