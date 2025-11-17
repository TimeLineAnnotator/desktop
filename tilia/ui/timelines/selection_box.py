from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from tilia.requests import Post, stop_listening_to_all, post


class SelectionBoxQt(QGraphicsRectItem):
    def __init__(self):
        super().__init__()
        self.set_pen_style_solid()
        self.x1 = 0
        self.y1 = 0

        self.overlap = set()

    def boundingRect(self):
        return QRectF(
            QPointF(min(0, self.x1), min(0, self.y1)),
            QPointF(max(0, self.x1), max(0, self.y1)),
        )

    def on_drag(self, x, y):
        self.prepareGeometryChange()  # needs to be called before a boundingRect change
        self.x1 = x - self.x()
        self.y1 = y - self.y()
        self.set_position(QPointF(0, 0), QPointF(self.x1, self.y1))
        new_overlap = set(self.collidingItems())

        # handle overlap change
        if new_overlap != self.overlap:
            if new_overlap - self.overlap:  # if an object was added
                for item in (new_overlap - self.overlap).copy():
                    post(
                        Post.SELECTION_BOX_SELECT_ITEM,
                        scene=self.scene(),
                        item=item,
                    )
            if self.overlap - new_overlap:  # if an object was removed
                for item in (self.overlap - new_overlap).copy():
                    post(
                        Post.SELECTION_BOX_DESELECT_ITEM,
                        scene=self.scene(),
                        item=item,
                    )

        self.overlap = new_overlap

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

    def set_position(self, upper_left, bottom_right):
        self.setRect(self.get_rect(upper_left, bottom_right))

    @staticmethod
    def get_rect(upper_left, bottom_right):
        return QRectF(upper_left, bottom_right)

    def destroy(self):
        stop_listening_to_all(self)
        self.scene().removeItem(self)
