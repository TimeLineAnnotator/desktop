from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF, QLineF
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsLineItem, QGraphicsItemGroup

from tilia.ui.timelines.cursors import CursorMixIn


class HierarchyBodyHandle(CursorMixIn, QGraphicsRectItem):
    def __init__(
        self, x: float, width: int, height: int, tl_height: float, bottom_margin: float
    ):
        super().__init__(cursor_shape=Qt.CursorShape.SizeHorCursor)
        self.set_position(x, width, height, tl_height, bottom_margin)
        self.set_fill("black")
        self.set_pen_style_no_pen()

    def set_fill(self, color: str):
        self.setBrush(QColor(color))

    def set_pen_style_no_pen(self):
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.NoPen)
        self.setPen(pen)

    def set_position(self, x, width, height, tl_height, bottom_margin):
        self.setRect(self.get_rect(x, width, height, tl_height, bottom_margin))
        self.setZValue(0)

    @staticmethod
    def get_rect(x, width, height, tl_height, bottom_margin):
        base_height = tl_height - bottom_margin
        rect = QRectF(
            QPointF(x - (width / 2), base_height - height),
            QPointF(x + (width / 2), base_height),
        )
        return rect


class HierarchyFrameHandle(QGraphicsItemGroup):
    VERTICAL_LINE_WIDTH = 3
    HORIZONTAL_LINE_WIDTH = 1
    HEIGHT = 10

    def __init__(self, x, frame_x, y):
        super().__init__()
        self.horizontal_line = self.HLine(x, frame_x, y, self.HORIZONTAL_LINE_WIDTH)
        self.vertical_line = self.VLine(
            frame_x, y - self.HEIGHT / 2, y + self.HEIGHT / 2, self.VERTICAL_LINE_WIDTH
        )
        self.addToGroup(self.horizontal_line)
        self.addToGroup(self.vertical_line)
        self.setZValue(0)
        self.setVisible(False)

    def set_position(self, x, frame_x, y):
        self.horizontal_line.set_position(x, frame_x, y)
        self.vertical_line.set_position(
            frame_x, y - self.HEIGHT / 2, y + self.HEIGHT / 2
        )

    class VLine(QGraphicsLineItem):
        def __init__(self, x: float, y0: float, y1: float, width):
            super().__init__()
            self.set_position(x, y0, y1)
            self.set_pen(width)
            self.setZValue(0)

        def set_pen(self, width):
            pen = QPen(QColor("black"))
            pen.setStyle(Qt.PenStyle.SolidLine)
            pen.setWidth(width)
            self.setPen(pen)

        def set_position(self, x: float, y0: float, y1: float):
            self.setLine(self.get_line(x, y0, y1))

        @staticmethod
        def get_line(x, y0, y1):
            return QLineF(x, y0, x, y1)

    class HLine(QGraphicsLineItem):
        def __init__(self, x0: float, x1: float, y: float, width):
            super().__init__()
            self.set_position(x0, x1, y)
            self.set_pen(width)
            self.setZValue(0)

        def set_pen(self, width):
            pen = QPen(QColor("black"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(width)
            self.setPen(pen)

        def set_position(self, x0: float, x1: float, y: float):
            self.setLine(self.get_line(x0, x1, y))

        @staticmethod
        def get_line(x0, x1, y):
            return QLineF(x0, y, x1, y)
