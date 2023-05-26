from typing import Protocol


class UI(Protocol):
    def get_timeline_ui_collection(self) -> TimelineUICollection:
        ...
