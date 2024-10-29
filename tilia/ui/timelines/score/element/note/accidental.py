from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsPixmapItem


class NoteAccidental(QGraphicsPixmapItem):
    def __init__(self, x: float, y: float, height: float, path: Path):
        super().__init__()
        self.set_icon(str(path.resolve()))
        self.set_height(height)
        self.set_position(x, y)

    def set_icon(self, path: str):
        self.setPixmap(QPixmap(path))

    def set_height(self, height: float):
        self.setPixmap(self.pixmap().scaledToHeight(height, mode=Qt.TransformationMode.SmoothTransformation))

    def set_position(self, x: float, y: float):
        self.setPos(x - self.boundingRect().width(), y)
