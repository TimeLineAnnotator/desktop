from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem


class NoteAccidental(QGraphicsPixmapItem):
    def __init__(self, x: float, y: float, height: float, path: Path):
        super().__init__()
        self.set_icon(str(path.resolve()))
        self.set_height(height)
        self.set_position(x, y)
        self.setZValue(3)  # in front of notes

    def set_icon(self, path: str):
        self._pixmap = QPixmap(path)
        self.setPixmap(self._pixmap)

    def set_height(self, height: float):
        if height == 0:
            self.setVisible(False)
        else:
            self.setPixmap(
                self._pixmap.scaledToHeight(
                    height, mode=Qt.TransformationMode.SmoothTransformation
                )
            )
            self.setVisible(True)

    def set_position(self, x: float, y: float):
        self.setPos(
            x - self.boundingRect().width(), y - self.boundingRect().height() / 2
        )
