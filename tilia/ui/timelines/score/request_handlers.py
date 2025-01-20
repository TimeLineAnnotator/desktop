from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.requests import Post
from tilia.ui.timelines.base.request_handlers import ElementRequestHandler

if TYPE_CHECKING:
    from tilia.ui.timelines.score.timeline import ScoreTimelineUI


class ScoreTimelineUIElementRequestHandler(ElementRequestHandler):
    def __init__(self, timeline_ui: ScoreTimelineUI):

        super().__init__(
            timeline_ui,
            {
                Post.TIMELINE_ELEMENT_DELETE: self.on_delete,
                Post.TIMELINE_ELEMENT_COLOR_SET: self.on_color_set,
                Post.TIMELINE_ELEMENT_COLOR_RESET: self.on_color_reset,
            },
        )

    def on_color_set(self, elements, value, **_):
        self.timeline_ui.set_elements_attr(elements, "color", value.name())
        return True

    def on_color_reset(self, elements, *_, **__):
        self.timeline_ui.set_elements_attr(elements, "color", None)
        return True

    def on_delete(self, *_, **__):
        return False

    def on_copy(self, *_, **__):
        return False

    def on_paste(self, *_, **__):
        return False
