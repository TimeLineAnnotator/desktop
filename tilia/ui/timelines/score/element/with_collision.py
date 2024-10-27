from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsScene

from tilia.ui.coords import get_x_by_time
from tilia.ui.timelines.base.element import TimelineUIElement

if TYPE_CHECKING:
    from tilia.ui.timelines.score import ScoreTimelineUI


class TimelineUIElementWithCollision(TimelineUIElement):
    def __init__(self, id: int, timeline_ui: ScoreTimelineUI, scene: QGraphicsScene, margin_x: float = 0, **kwargs):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)
        self.margin_x = margin_x
        self._x_offset = None

    @property
    def width(self):
        return self.body.boundingRect().width() + self.margin_x * 2

    @property
    def x(self):
        return get_x_by_time(self.get_data('time'))

    @property
    def x_offset(self):
        return - self.width / 2 if self._x_offset is None else self._x_offset

    @x_offset.setter
    def x_offset(self, value):
        self._x_offset = value
        self.update_position()
