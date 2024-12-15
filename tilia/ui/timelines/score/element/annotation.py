from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.ui.timelines.base.element import TimelineUIElement

if TYPE_CHECKING:
    from ..timeline import ScoreTimelineUI


class ScoreAnnotationUI(TimelineUIElement):
    def child_items(self):
        return []

    def on_select(self) -> None:
        pass

    def on_deselect(self) -> None:
        pass

    def update_position(self) -> None:
        pass
