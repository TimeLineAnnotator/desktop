from enum import Enum

from PySide6.QtCore import QLineF
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QGraphicsLineItem


class NoteLedgerLines:
    class Direction(Enum):
        UP = -1
        DOWN = 1

    def __init__(
        self,
        direction: Direction,
        line_count: int,
        x1: float,
        x2: float,
        y1: float,
        line_spacing: int,
    ):
        super().__init__()
        self.direction = direction
        self._setup_lines(line_count, x1, x2, y1, line_spacing)
        self.set_position(x1, x2, y1, line_spacing)

    def _setup_lines(
        self, line_count: int, x1: float, x2: float, y1: float, line_spacing: int
    ):
        self.lines = [QGraphicsLineItem() for _ in range(line_count)]

        from tilia.ui.timelines.score.element.staff import StaffLines

        pen = QPen(QColor(StaffLines.COLOR))
        pen.setWidth(2)

        for line in self.lines:
            line.setPen(pen)
            line.setZValue(-1)
        self.set_position(x1, x2, y1, line_spacing)

    def set_position(self, x1: float, x2: float, y1: float, line_spacing: int):
        for i in range(len(self.lines)):
            y = y1 + (line_spacing * (i + 1) * self.direction.value)
            self.lines[i].setLine(QLineF(x1, y, x2, y))
