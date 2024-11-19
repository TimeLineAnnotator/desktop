from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem

from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.score.element.with_collision import TimelineUIElementWithCollision


class TimeSignatureUI(TimelineUIElementWithCollision):
    MARGIN_X = 2

    def __init__(self, *args, **kwargs):
        super().__init__(self.MARGIN_X,*args, **kwargs)
        self._setup_body()

    @property
    def x(self):
        return time_x_converter.get_x_by_time(self.get_data('time'))

    def _setup_body(self):
        self.body = TimeSignatureBody(self.x, self.timeline_ui.get_y_for_symbols_above_staff(self.get_data('staff_index')), self.get_data('numerator'), self.get_data('denominator'), self.timeline_ui.pixmaps['time signature'])
        self.body.moveBy(self.x_offset, 0)
        self.scene.addItem(self.body)

    def child_items(self):
        return [self.body]

    def update_position(self):
        self.body.set_position(self.x + self.x_offset + (self.margin_x if self.x_offset is not None else 0), self.timeline_ui.get_y_for_symbols_above_staff(self.get_data('staff_index')))

    def selection_triggers(self):
        return []


class TimeSignatureBody(QGraphicsItem):
    PIXMAP_HEIGHT = 12
    TOP_MARGIN = 10

    def __init__(self, x: float, y: float, numerator: int, denominator: int, pixmaps: dict[int, QPixmap]):
        super().__init__()
        self.pixmaps = pixmaps
        self.set_numerator_items(numerator)
        self.set_denominator_items(denominator)
        self.align_pixmaps(numerator, denominator)
        self.set_position(x, y)

    def set_numerator_items(self, numerator: int):
        self.numerator_items = []
        for i, digit in enumerate(str(numerator)):
            item = QGraphicsPixmapItem(self.pixmaps[int(digit)].scaledToHeight(self.PIXMAP_HEIGHT, mode=Qt.TransformationMode.SmoothTransformation), self)
            item.setPos(i * item.pixmap().width(), 0)
            self.numerator_items.append(item)

    def set_denominator_items(self, denominator: int):
        self.denominator_items = []
        for i, digit in enumerate(str(denominator)):
            item = QGraphicsPixmapItem(self.pixmaps[int(digit)].scaledToHeight(self.PIXMAP_HEIGHT, mode=Qt.TransformationMode.SmoothTransformation), self)
            item.setPos(i * item.pixmap().width(), item.pixmap().height())
            self.denominator_items.append(item)

    def align_pixmaps(self, numerator: int, denominator: int):
        difference = len(str(denominator)) - len(str(numerator))
        if difference > 0:
            # numerator is shorter than denominator
            for item in self.numerator_items:
                item.moveBy(difference * item.pixmap().width() / 2, 0)

        elif difference < 0:
            # denominator is shorter than numerator
            for item in self.denominator_items:
                item.moveBy(difference * item.pixmap().width() * -1 / 2, 0)

    def set_position(self, x: float, y: float):
        self.setPos(x, y + self.TOP_MARGIN)

    def canvas_items(self):
        return self.numerator_items + self.denominator_items

    def boundingRect(self):
        items = self.canvas_items()
        bounding_rect = items[0].boundingRect()
        for item in items[1:]:
            bounding_rect = bounding_rect.united(item.boundingRect())
        return bounding_rect

    def paint(self, painter, option, widget): ...
