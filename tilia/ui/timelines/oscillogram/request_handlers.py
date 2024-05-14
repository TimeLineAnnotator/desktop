from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.requests import Post
from tilia.ui.timelines.base.request_handlers import ElementRequestHandler

if TYPE_CHECKING:
    from tilia.ui.timelines.oscillogram import OscillogramTimelineUI


class OscillogramTimelineUIRequestHandler(ElementRequestHandler):
    def __init__(self, timeline_ui: OscillogramTimelineUI):
        super().__init__(
            timeline_ui, 
            {
                Post.OSCILLOGRAM_REFRESH: self.on_refresh,
                Post.TIMELINE_ELEMENT_DELETE: self.on_delete,
                Post.TIMELINE_ELEMENT_COPY: self.on_copy,
                Post.TIMELINE_ELEMENT_PASTE: self.on_paste,
            }
        )

    def on_refresh(self, *_, **__):
        self.timeline.refresh()

    def on_delete(self, *_, **__):
        pass

    def on_copy(self, *_, **__):
        pass

    def on_paste(self, *_, **__):
        pass