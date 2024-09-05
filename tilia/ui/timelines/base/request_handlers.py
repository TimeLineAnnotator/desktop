from __future__ import annotations

import functools
from typing import Callable

from tilia.requests import Post, get, Get
from tilia.ui.enums import PasteCardinality
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.request_handler import RequestHandler


class TimelineRequestHandler(RequestHandler):
    def __init__(self, timeline_ui, request_to_callback: dict[Post, Callable]):
        base_request_to_callback = {
            Post.TIMELINE_DELETE_FROM_MANAGE_TIMELINES: self.on_timeline_delete,
            Post.TIMELINE_CLEAR_FROM_MANAGE_TIMELINES: self.on_timeline_clear,
            Post.TIMELINE_DELETE_FROM_CLI: functools.partial(self.on_timeline_delete, True),
            Post.TIMELINE_NAME_SET: functools.partial(
                self.on_timeline_data_set, "name"
            ),
            Post.TIMELINE_HEIGHT_SET: functools.partial(
                self.on_timeline_data_set, "height"
            ),
            Post.TIMELINE_IS_VISIBLE_SET_FROM_MANAGE_TIMELINES: functools.partial(
                self.on_timeline_data_set, "is_visible"
            ),
            Post.TIMELINE_ORDINAL_INCREASE_FROM_MANAGE_TIMELINES: self.on_timeline_ordinal_permute_from_manage_timelines,
            Post.TIMELINE_ORDINAL_DECREASE_FROM_MANAGE_TIMELINES: self.on_timeline_ordinal_permute_from_manage_timelines,
            Post.TIMELINE_DELETE_FROM_CONTEXT_MENU: self.on_timeline_delete,
            Post.TIMELINE_ORDINAL_DECREASE_FROM_CONTEXT_MENU: self.on_timeline_ordinal_permute_from_context_menu,
            Post.TIMELINE_ORDINAL_INCREASE_FROM_CONTEXT_MENU: self.on_timeline_ordinal_permute_from_context_menu,
        }
        super().__init__(
            request_to_callback=request_to_callback | base_request_to_callback
        )
        self.timeline_ui = timeline_ui

    @property
    def timeline(self):
        return get(Get.TIMELINE, self.timeline_ui.id)

    def on_timeline_data_set(self, attr, value, **_):
        get(Get.TIMELINE_COLLECTION).set_timeline_data(self.timeline_ui.id, attr, value)

    def on_timeline_ordinal_permute_from_manage_timelines(self, id_to_ordinal):
        self.on_timeline_data_set("ordinal", id_to_ordinal[self.timeline_ui.id])

    def on_timeline_ordinal_permute_from_context_menu(self, id_to_ordinal):
        self.on_timeline_data_set("ordinal", id_to_ordinal[self.timeline_ui.id])

    def on_timeline_delete(self, confirmed):
        if confirmed:
            get(Get.TIMELINE_COLLECTION).delete_timeline(self.timeline_ui.timeline)

    def on_timeline_clear(self, confirmed):
        if confirmed:
            get(Get.TIMELINE_COLLECTION).clear_timeline(self.timeline_ui.timeline)


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
    def elements_to_components(elements: list[TimelineUIElement]):
        return [e.tl_component for e in elements]

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
