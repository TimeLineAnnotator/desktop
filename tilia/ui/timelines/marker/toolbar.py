from __future__ import annotations

from tilia.requests import Post, post
from tilia.ui.timelines.common import TimelineToolbar


class MarkerTimelineToolbar(TimelineToolbar):
    def __init__(self, parent):
        super().__init__(parent, text="Markers")

        self.button_info = [
            (
                "add_marker30",
                lambda: post(Post.MARKER_TOOLBAR_BUTTON_ADD),
                "Add marker at current position (m)",
            ),
            (
                "delete_marker30",
                lambda: post(Post.MARKER_TOOLBAR_BUTTON_DELETE),
                "Delete marker (Delete)",
            ),
        ]

        self.create_buttons()
