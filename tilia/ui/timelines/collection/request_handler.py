from __future__ import annotations

from pathlib import Path

import tilia.errors
from tilia.requests import Post, get, Get
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.request_handler import RequestHandler


def _get_media_is_loaded():
    if get(Get.MEDIA_DURATION) == 0:
        return False
    return True


def _get_timeline_name():
    name, confirmed = get(
        Get.FROM_USER_STRING,
        title="New timeline",
        prompt="Choose name for new timeline",
    )

    return confirmed, name


class TimelineUIsRequestHandler(RequestHandler):
    def __init__(self, timeline_uis):
        super().__init__(
            request_to_callback={
                Post.TIMELINE_ADD: self.on_timeline_add,
                Post.TIMELINES_CLEAR: self.on_timelines_clear,
            }
        )
        self.timeline_uis = timeline_uis
        self.timelines = get(Get.TIMELINE_COLLECTION)

    def on_timeline_add(self, kind: TimelineKind):
        if not _get_media_is_loaded():
            tilia.errors.display(tilia.errors.CREATE_TIMELINE_WITHOUT_MEDIA)
            return
        success, name = _get_timeline_name()
        kwargs = dict()
        if not success:
            return
        cls = self.timeline_uis.get_timeline_ui_class(kind)
        if hasattr(cls, "get_additional_args_for_creation"):
            success, additional_args = cls.get_additional_args_for_creation()
            if not success:
                return
            kwargs |= additional_args

        self.timelines.create_timeline(kind=kind, components=None, name=name, **kwargs)

    def on_timelines_clear(self, confirmed):
        if confirmed:
            self.timelines.clear_timelines()
