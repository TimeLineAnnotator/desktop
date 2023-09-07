from __future__ import annotations

from tilia.requests import Post, get, Get
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.request_handler import RequestHandler


class TimelineUIsRequestHandler(RequestHandler):
    def __init__(self, timeline_uis):
        super().__init__(
            request_to_callback={
                Post.TIMELINE_ADD_HIERARCHY_TIMELINE: self.on_timeline_add_hierarchy_timeline,
                Post.TIMELINE_ADD_MARKER_TIMELINE: self.on_timeline_add_marker_timeline,
                Post.TIMELINE_ADD_BEAT_TIMELINE: self.on_timeline_add_beat_timeline,
                Post.TIMELINE_ADD_HARMONY_TIMELINE: self.on_timeline_add_harmony_timeline,
                Post.TIMELINES_CLEAR: self.on_timelines_clear,
            }
        )
        self.timeline_uis = timeline_uis
        self.timelines = get(Get.TIMELINE_COLLECTION)

    @staticmethod
    def _display_create_timeline_without_media_error():
        post(Post.DISPLAY_ERROR, *tilia.errors.CREATE_TIMELINE_WITHOUT_MEDIA)

    def on_timeline_add_hierarchy_timeline(self, confirmed: bool, name: str):
        if confirmed:
            self.timelines.create_timeline(
                TimelineKind.HIERARCHY_TIMELINE, None, name=name
            )

    def on_timeline_add_marker_timeline(self, confirmed: bool, name: str):
        if confirmed:
            self.timelines.create_timeline(
                TimelineKind.MARKER_TIMELINE, None, name=name
            )

    def on_timeline_add_beat_timeline(
        self, confirmed: bool, name: str, beat_pattern: list[int]
    ):
        if confirmed:
            self.timelines.create_timeline(
                TimelineKind.BEAT_TIMELINE,
                None,
                name=name,
                beat_pattern=beat_pattern,
            )

    def on_timeline_add_harmony_timeline(self, confirmed: bool, name: str):
        if confirmed:
            self.timelines.create_timeline(
                TimelineKind.HARMONY_TIMELINE, None, name=name
            )

    def on_timelines_clear(self, confirmed):
        if confirmed:
            self.timelines.clear_timelines()
