from __future__ import annotations

from functools import partial

from tilia.requests import Post, get, Get
from tilia.ui.request_handler import RequestHandler
from tilia.ui.strings import (
    BEAT_TIMELINE_FILL_TITLE,
    BEAT_TIMELINE_DELETE_EXISTING_BEATS_PROMPT,
)


class TimelineUIsRequestHandler(RequestHandler):
    def __init__(self, timeline_uis):
        super().__init__(
            request_to_callback={
                Post.TIMELINES_CLEAR: self.on_timelines_clear,
                Post.BEAT_TIMELINE_FILL: self.on_beat_timeline_fill,
                Post.TIMELINE_ORDINAL_PERMUTE_FROM_MANAGE_TIMELINES: partial(
                    self.on_timeline_ordinal_permute, "manage_timelines"
                ),
                Post.TIMELINE_ORDINAL_PERMUTE_FROM_CONTEXT_MENU: partial(
                    self.on_timeline_ordinal_permute, "context_menu"
                ),
                Post.TIMELINE_IS_VISIBLE_SET_FROM_MANAGE_TIMELINES: self.on_timeline_is_visible_set,
            }
        )
        self.timeline_uis = timeline_uis
        self.timelines = get(Get.TIMELINE_COLLECTION)

    def on_timeline_data_set(self, id, attr, value):
        return get(Get.TIMELINE_COLLECTION).set_timeline_data(id, attr, value)

    def on_timeline_is_visible_set(self, id, value):
        is_visible = get(Get.WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_CURRENT).get_data(
            "is_visible"
        )
        return self.on_timeline_data_set(id, "is_visible", not is_visible)

    def on_timeline_ordinal_permute(self, ui_component: str):
        if ui_component == "manage_timelines":
            tlui1, tlui2 = get(Get.WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_TO_PERMUTE)
        elif ui_component == "context_menu":
            tlui1, tlui2 = get(Get.CONTEXT_MENU_TIMELINE_UIS_TO_PERMUTE)

        id_to_ordinal = {
            tlui1.id: tlui2.get_data("ordinal"),
            tlui2.id: tlui1.get_data("ordinal"),
        }
        for id, ordinal in id_to_ordinal.items():
            self.on_timeline_data_set(id, attr="ordinal", value=ordinal)
        return True

    def on_timelines_clear(self):
        confirmed = get(
            Get.FROM_USER_YES_OR_NO,
            "Clear timelines",
            "Are you sure you want to clear ALL timelines? This can be undone later.",
        )

        if confirmed:
            self.timelines.clear_timelines()
            return True
        return False

    @staticmethod
    def on_beat_timeline_fill():
        accepted, result = get(Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD)
        if not accepted:
            return False

        timeline, method, value = result

        if not timeline.is_empty:
            confirmed = get(
                Get.FROM_USER_YES_OR_NO,
                BEAT_TIMELINE_FILL_TITLE,
                BEAT_TIMELINE_DELETE_EXISTING_BEATS_PROMPT,
            )
            if not confirmed:
                return False
            timeline.clear()

        timeline.fill_with_beats(method, value)

        return True
