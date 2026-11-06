from __future__ import annotations

from tilia.ui.timelines.base.element import TimelineUIElement


class NoteGroupUI(TimelineUIElement):
    """Has no items on the timeline: `ScoreView` draws note groups on the score."""

    UPDATE_TRIGGERS = []

    def child_items(self) -> list:
        return []

    def on_select(self) -> None:
        pass

    def on_deselect(self) -> None:
        pass

    def update_position(self) -> None:
        pass
