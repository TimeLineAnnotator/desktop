from __future__ import annotations

from typing import TYPE_CHECKING

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
        return [self.body]

    def get_body_args(self):
        time = self.get_data('time')
        return (
            get_x_by_time(time),
            self.timeline_ui.get_barline_top_y(time),
            self.timeline_ui.get_barline_height(time),
        )

    def _setup_body(self):
        time = self.get_data('time')
        self.body = BarLineBody(*self.get_body_args())
        self.scene.addItem(self.body)

    def update_position(self):
        self.body.set_position(*self.get_body_args())


class BarLineBody(QGraphicsLineItem):
    def __init__(self, x, y, height):
        super().__init__()
        self.set_position(x, y, height)
        self.set_pen()

    def set_position(self, x, y, height):
        self.setLine(x, y, x, y + height)

    def set_pen(self):
        pen = QPen(QColor("black"))
        pen.setWidth(1)
        self.setPen(pen)


