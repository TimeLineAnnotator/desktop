from __future__ import annotations

import functools
from abc import ABC
from typing import Callable, TYPE_CHECKING

import tilia
from tilia import errors
from tilia.requests import Post, get, Get, post
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.enums import PasteCardinality
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.collection.requests.enums import ElementSelector

if TYPE_CHECKING:
    from tilia.ui.timelines.base.timeline import TimelineUI


class RequestHandler(ABC):
    def __init__(
        self, timeline_ui: TimelineUI, request_to_callback: dict[Post, Callable]
    ):
        base_request_to_callback = {
            Post.TIMELINE_ADD_HIERARCHY_TIMELINE: self.on_timeline_add_hierarchy_timeline,
            Post.TIMELINE_ADD_MARKER_TIMELINE: self.on_timeline_add_marker_timeline,
            Post.TIMELINE_ADD_BEAT_TIMELINE: self.on_timeline_add_beat_timeline,
            Post.TIMELINE_ADD_HARMONY_TIMELINE: self.on_timeline_add_harmony_timeline,
            Post.TIMELINE_DELETE_FROM_MANAGE_TIMELINES: self.on_timeline_delete,
            Post.TIMELINE_CLEAR_FROM_MANAGE_TIMELINES: self.on_timeline_clear,
            Post.TIMELINES_CLEAR: self.on_timelines_clear,
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
        }
        self.request_to_callback = base_request_to_callback | request_to_callback
        self.timeline_ui = timeline_ui

    @property
    def timeline(self):
        return get(Get.TIMELINE, self.timeline_ui.id)

    def on_request(self, request, *args, **kwargs): ...

    def on_timeline_data_set(self, attr, value, **_):
        get(Get.TIMELINE_COLLECTION).set_timeline_data(self.timeline_ui.id, attr, value)

    def on_timeline_ordinal_permute_from_manage_timelines(self, id_to_ordinal):
        self.on_timeline_data_set("ordinal", id_to_ordinal[self.timeline_ui.id])

    def on_timeline_delete(self, confirmed):
        if confirmed:
            get(Get.TIMELINE_COLLECTION).delete_timeline(self.timeline_ui.timeline)

    def on_timeline_clear(self, confirmed):
        if confirmed:
            get(Get.TIMELINE_COLLECTION).clear_timeline(self.timeline_ui.timeline)


    @staticmethod
    def _display_create_timeline_without_media_error():
        post(Post.DISPLAY_ERROR, *tilia.errors.CREATE_TIMELINE_WITHOUT_MEDIA)

    @staticmethod
    def _validate_media_duration_for_timeline_creation():
        if get(Get.MEDIA_DURATION) == 0:
            return False
        return True

    def on_timeline_add_hierarchy_timeline(self, confirmed: bool, name: str):
        if not self._validate_media_duration_for_timeline_creation():
            self._display_create_timeline_without_media_error()

        if confirmed:
            get(Get.TIMELINE_COLLECTION).create_timeline(
                TimelineKind.HIERARCHY_TIMELINE, None, name=name
            )

    def on_timeline_add_marker_timeline(self, confirmed: bool, name: str):
        if not self._validate_media_duration_for_timeline_creation():
            self._display_create_timeline_without_media_error()

        if confirmed:
            get(Get.TIMELINE_COLLECTION).create_timeline(
                TimelineKind.MARKER_TIMELINE, None, name=name
            )

    def on_timeline_add_beat_timeline(
        self, confirmed: bool, name: str, beat_pattern: list[int]
    ):
        if not self._validate_media_duration_for_timeline_creation():
            self._display_create_timeline_without_media_error()
        if confirmed:
            get(Get.TIMELINE_COLLECTION).create_timeline(
                TimelineKind.BEAT_TIMELINE,
                None,
                name=name,
                beat_pattern=beat_pattern,
            )

    @staticmethod
    def on_timeline_add_harmony_timeline(confirmed: bool, name: str):
        if confirmed:
            get(Get.TIMELINE_COLLECTION).create_timeline(
                TimelineKind.HARMONY_TIMELINE, None, name=name
            )

    @staticmethod
    def on_timelines_clear(confirmed):
        if confirmed:
            get(Get.TIMELINE_COLLECTION).clear_timelines()


class ElementRequestHandler(RequestHandler):
    DO_NOT_RECORD = [Post.TIMELINE_ELEMENT_COPY]

    @staticmethod
    def elements_to_components(elements: [TimelineUIElement]):
        return [e.tl_component for e in elements]

    def on_request(self, request, selector: ElementSelector, *args, **kwargs):
        return self.request_to_callback[request](
            self.timeline_ui.get_elements_by_selector(selector), *args, **kwargs
        )

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


class TimelineRequestHandler(RequestHandler):
    def on_request(self, request, *args, **kwargs):
        return self.request_to_callback[request](*args, **kwargs)
