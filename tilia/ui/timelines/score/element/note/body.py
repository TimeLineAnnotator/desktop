from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsPolygonItem

from tilia.ui.color import get_tinted_color, get_untinted_color
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.timelines.cursors import CursorMixIn


class NoteBody(CursorMixIn, QGraphicsPolygonItem):
    X_OFFSET = 0
    Y_OFFSET = 1

    def __init__(
        self, start_x: float, end_x: float, top_y: float, note_height: float, color: str
    ):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.set_position(start_x, end_x, top_y, note_height)
        self.set_pen()
        self.set_fill(color)

    def set_fill(self, color: str):
        self.setBrush(QColor(color))

    def set_pen(self):
        pen = QPen(QColor("#777777"))
        pen.setWidth(0)
        pen.setStyle(Qt.PenStyle.SolidLine)
        self.setPen(pen)

    def set_position(self, start_x: float, end_x: float, top_y: float, note_height: float):
        self.setPolygon(self.get_polygon(start_x, end_x, top_y, note_height))

    def on_select(self):
        self.setBrush(
            QColor(get_tinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )

    def on_deselect(self):
        self.setBrush(
            QColor(get_untinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )

    def get_polygon(self, start_x: float, end_x: float, top_y: float, note_height: float) -> QPolygonF:
        indent = 5
        mid_y = top_y + note_height / 2
        bottom_y = top_y + note_height
        x_left_outer = start_x
        x_left_inner = start_x + indent
        x_right_inner = end_x - indent
        x_right_outer = end_x
        return QPolygonF([
            QPointF(x_left_outer, mid_y),
            QPointF(x_left_inner, top_y),
            QPointF(x_right_inner, top_y),
            QPointF(x_right_outer, mid_y),
            QPointF(x_right_inner, bottom_y),
            QPointF(x_left_inner, bottom_y),
            QPointF(x_left_outer, mid_y),
            ]
        )

        # code for rectangle
        # x0 = top_y + self.Y_OFFSET / 2
        # x1 = end_x - self.X_OFFSET
        # y1 = top_y + note_height - self.Y_OFFSET / 2
        # return QPolygonF(QPointF(x0, y0), QPointF(x1, y1))