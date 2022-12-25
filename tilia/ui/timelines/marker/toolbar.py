from __future__ import annotations

from tilia import events
from tilia.events import Event
from tilia.ui.timelines.common import TimelineToolbar


class MarkerTimelineToolbar(TimelineToolbar):

    def __init__(self, parent):
        super().__init__(parent, text="Hierarchies")

        self.button_info = [
            (
                "add_marker30",
                lambda: events.post(Event.MARKER_TOOLBAR_BUTTON_ADD),
                "Add marker at current position (m)",
            ),
            (
                "delete_marker30",
                lambda: events.post(Event.MARKER_TOOLBAR_BUTTON_DELETE),
                "Delete marker (Delete)",
            )
        ]

        self.create_buttons()
