from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QGraphicsRectItem

from tilia.ui.color import get_tinted_color, get_untinted_color
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.timelines.cursors import CursorMixIn


class NoteBody(CursorMixIn, QGraphicsRectItem):
    X_OFFSET = 0
    Y_OFFSET = 1

    def __init__(
        self, start_x: float, end_x: float, top_y: float, note_height: float, color: str
    ):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.set_position(start_x, end_x, top_y, note_height)
        self.set_pen_style_no_pen()
        self.set_fill(color)

    def set_fill(self, color: str):
        self.setBrush(QColor(color))

    def set_pen_style_solid(self):
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.SolidLine)
        self.setPen(pen)

    def set_pen_style_no_pen(self):
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.NoPen)
        self.setPen(pen)

    def set_position(self, start_x: float, end_x: float, top_y: float, note_height: float):
        self.setRect(self.get_rect(start_x, end_x, top_y, note_height))

    def on_select(self):
        self.set_pen_style_solid()
        self.setBrush(
            QColor(get_tinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )

    def on_deselect(self):
        self.set_pen_style_no_pen()
        self.setBrush(
            QColor(get_untinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )

    def get_rect(self, start_x: float, end_x: float, top_y: float, note_height: float) -> QRectF:
        x0 = start_x + self.X_OFFSET
        y0 = top_y + self.Y_OFFSET / 2
        x1 = end_x - self.X_OFFSET
        y1 = top_y + note_height - self.Y_OFFSET / 2
        return QRectF(QPointF(x0, y0), QPointF(x1, y1))
