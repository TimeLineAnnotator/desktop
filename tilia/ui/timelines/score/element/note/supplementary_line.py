from PyQt6.QtGui import QPen, QColor
from PyQt6.QtWidgets import QGraphicsLineItem


class NoteSupplementaryLine(QGraphicsLineItem):
    def __init__(self, x1: float, x2: float, y: float):
        super().__init__()
        self.set_position(x1, x2, y)
        self.set_pen("black", 2)

    def set_position(self, x1: float, x2: float, y: float):
        self.setLine(x1, y, x2, y)

    def set_pen(self, color: str, width: int):
        pen = QPen(QColor(color))
        pen.setWidth(width)
        self.setPen(pen)


