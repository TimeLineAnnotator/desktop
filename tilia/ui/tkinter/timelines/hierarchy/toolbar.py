from __future__ import annotations

from tilia import events
from tilia.events import Event
from tilia.ui.tkinter import event_handler
from tilia.ui.tkinter.timelines.common import TimelineToolbar


class HierarchyTimelineToolbar(TimelineToolbar):
    padx = 5
    pady = 3

    def __init__(self, parent):
        super(HierarchyTimelineToolbar, self).__init__(parent, text="Hierarchies")

        self.button_info = [
            (
                "split30",
                lambda: events.post(Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_SPLIT),
                "Split unit at current position (s)",
            ),
            (
                "merge30",
                lambda: events.post(Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_MERGE),
                "Merge units (Shift+m)",
            ),
            (
                "group30",
                lambda: events.post(Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_GROUP),
                "Group units (g)",
            ),
            (
                "lvlup30",
                lambda: events.post(
                    Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_INCREASE, "plus"
                ),
                "Increase level",
            ),
            (
                "lvldwn30",
                lambda: events.post(
                    Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_DECREASE, "minus"
                ),
                "Decrease level",
            ),
            (
                "below30",
                lambda: events.post(
                    Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_CREATE_CHILD
                ),
                "Create unit below",
            ),
            (
                "delete30",
                lambda: events.post(Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_DELETE),
                "Delete unit (Delete)",
            ),
            (
                "paste30",
                lambda: events.post(
                    Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT
                ),
                "Paste unit (Ctrl + V",
            ),
            (
                "paste_with_data30",
                lambda: events.post(
                    Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT_WITH_CHILDREN
                ),
                "Paste unit with all attributes\n(including children) (Ctrl + Shift + V)",
            ),
        ]

        self.create_buttons()
