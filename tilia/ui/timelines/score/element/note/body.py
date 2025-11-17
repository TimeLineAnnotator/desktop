from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from tilia.timelines.score.components import Note
from tilia.ui.color import get_tinted_color, get_untinted_color
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.timelines.cursors import CursorMixIn


class NoteBody(CursorMixIn, QGraphicsRectItem):
    X_OFFSET = 0.5
    Y_OFFSET = 1

    def __init__(
        self,
        start_x: float,
        end_x: float,
        top_y: float,
        note_height: float,
        color: str,
        tie_type: Note.TieType,
    ):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.tie_type = tie_type
        self.set_position(start_x, end_x, top_y, note_height)
        self.set_no_pen()
        self.set_fill(color)

    def set_fill(self, color: str):
        self.setBrush(QColor(color))

    def set_no_pen(self):
        pen = QPen(QColor("#777777"))
        pen.setStyle(Qt.PenStyle.NoPen)
        self.setPen(pen)

    def set_pen_outlined(self):
        pen = self.pen()
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setColor(QColor("white"))
        pen.setWidth(2)
        self.setPen(pen)

    def set_position(
        self, start_x: float, end_x: float, top_y: float, note_height: float
    ):
        x0 = start_x + (
            -1
            if self.tie_type in {Note.TieType.STOP, Note.TieType.START_STOP}
            else self.X_OFFSET
        )
        x1 = end_x - (
            -1
            if self.tie_type in {Note.TieType.START, Note.TieType.START_STOP}
            else self.X_OFFSET
        )
        y0 = top_y + self.Y_OFFSET / 2
        self.setRect(x0, y0, x1 - x0, note_height - self.Y_OFFSET)

    def on_select(self):
        self.setBrush(
            QColor(get_tinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )
        self.set_pen_outlined()
        self.setZValue(2)

    def on_deselect(self):
        self.setBrush(
            QColor(get_untinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )
        self.set_no_pen()
        self.setZValue(1)
