from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QLineF
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from tilia.ui.coords import get_x_by_time
from tilia.ui.timelines.base.element import TimelineUIElement

if TYPE_CHECKING:
    from tilia.ui.timelines.score.timeline import ScoreTimelineUI


class BarLineUI(TimelineUIElement):
    UPDATE_TRIGGERS = ['time']

    def __init__(self, id: int, timeline_ui: ScoreTimelineUI, scene: QGraphicsScene, **kwargs):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene, **kwargs)

        self._setup_body()

    def child_items(self):
        return self.body.lines

    def get_body_args(self):
        time = self.get_data('time')
        return (
            get_x_by_time(time),
            self.timeline_ui.get_staves_y_coordinates(),
        )

    def _setup_body(self):
        self.body = BarLineBody(*self.get_body_args())
        for line in self.body.lines:
            self.scene.addItem(line)

    def update_position(self):
        self.body.set_position(*self.get_body_args())

    def selection_triggers(self):
        return []


class BarLineBody:
    def __init__(self, x, ys: list[tuple[float, float]]):
        super().__init__()
        self._setup_lines(x, ys)

    def _setup_lines(self, x: float, ys: list[tuple[float, float]]):
        self.lines = [QGraphicsLineItem() for _ in range(len(ys))]
        pen = QPen(QColor("black"))
        pen.setWidth(1)
        for line in self.lines:
            line.setPen(pen)
        self.set_position(x, ys)

    def set_position(self, x: float, ys: list[tuple[float, float]]):
        for line in self.lines:
            y0, y1 = ys.pop(0)
            line.setLine(QLineF(x, y0, x, y1))
