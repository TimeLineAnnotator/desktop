from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QGraphicsTextItem


class LevelLabel(QGraphicsTextItem):
    def __init__(
        self,
        x: float,
        y: float,
        text: str,
    ):
        super().__init__()
        self._setup_font()
        self.setPlainText(text)
        self.set_position(x, y)

    def _setup_font(self):
        font = QFont("Liberation Sans", 9)
        self.setFont(font)
        self.setDefaultTextColor(QColor("gray"))

    @staticmethod
    def get_point(x: float, y: float):
        return QPointF(x, y)

    def set_position(self, x, y):
        self.setPos(self.get_point(x, y))
