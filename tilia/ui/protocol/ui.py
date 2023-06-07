from typing import Protocol

from tilia.ui.timelines.collection import TimelineUIs


class UI(Protocol):
    def get_timeline_ui_collection(self) -> TimelineUIs:
        ...
