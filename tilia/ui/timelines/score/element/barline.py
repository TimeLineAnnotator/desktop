from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QGraphicsLineItem

from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.base.element import TimelineUIElement


class BarLineUI(TimelineUIElement):
    UPDATE_TRIGGERS = ["time"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body = None

    def x(self):
        return time_x_converter.get_x_by_time(self.get_data("time"))

    def child_items(self):
        try:
            return self.body.lines
        except AttributeError:
            return []

    def get_body_args(self):
        return (
            self.x(),
            self.timeline_ui.staff_y_cache.values(),
        )

    def _setup_body(self):
        self.body = BarLineBody(*self.get_body_args())
        for line in self.body.lines:
            self.scene.addItem(line)

    def update_position(self):
        self.body.set_position(*self.get_body_args())

    def on_components_deserialized(self):
        self._setup_body()

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
        for line, (y0, y1) in zip(self.lines, ys):
            line.setLine(x, y0, x, y1)
