from __future__ import annotations

from tilia.requests import Get, get, listen, Post
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
)
from tilia.ui.timelines.collection.requests.enums import ElementSelector
from tilia.ui.timelines.score.element import NoteUI
from tilia.ui.timelines.score.request_handlers import ScoreTimelineUIElementRequestHandler
from tilia.ui.timelines.score.toolbar import ScoreTimelineToolbar


class ScoreTimelineUI(TimelineUI):
    TOOLBAR_CLASS = ScoreTimelineToolbar
    ELEMENT_CLASS = NoteUI
    ACCEPTS_HORIZONTAL_ARROWS = True

    TIMELINE_KIND = TimelineKind.SCORE_TIMELINE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listen(self, Post.SETTINGS_UPDATED, lambda updated_settings: self.on_settings_updated(updated_settings))

    def on_settings_updated(self, updated_settings):        
        if "score_timeline" in updated_settings:  
            get(Get.TIMELINE_COLLECTION).set_timeline_data(self.id, "height", self.timeline.default_height)
            for score_ui in self:
                score_ui.update_time()
                score_ui.update_color()

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return ScoreTimelineUIElementRequestHandler(self).on_request(
            request, selector, *args, **kwargs
        )
