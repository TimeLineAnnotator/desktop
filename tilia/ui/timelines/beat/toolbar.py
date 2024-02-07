from __future__ import annotations

from tilia.requests import Post, post
from tilia.ui.timelines.common import TimelineToolbar


class BeatTimelineToolbar(TimelineToolbar):
    def __init__(self, parent):
        super().__init__(parent, text="Beats")

        self.button_info = [
            (
                "add_beat30",
                lambda: post(Post.BEAT_TOOLBAR_BUTTON_ADD),
                "Add beat at current position (b)",
            ),
            (
                "delete_beat30",
                lambda: post(Post.BEAT_TOOLBAR_BUTTON_DELETE),
                "Delete beat (Delete)",
            ),
        ]

        self.create_buttons()
