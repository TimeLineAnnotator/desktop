from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.requests import serve, Get, stop_serving_all

if TYPE_CHECKING:
    from tilia.ui.timelines.base.timeline import TimelineUI


class ServeTimelineUIFromCLI:
    def __init__(self, timeline_ui: TimelineUI):
        self.timeline_ui = timeline_ui

    def serve(self):
        return self.timeline_ui

    def __enter__(self):
        serve(self, Get.TIMELINES_FROM_CLI, self.serve)

    def __exit__(self, type, value, traceback):
        stop_serving_all(self)
