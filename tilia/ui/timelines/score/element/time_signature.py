from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem

from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.score.element.with_collision import (
    TimelineUIElementWithCollision,
)


class TimeSignatureUI(TimelineUIElementWithCollision):
    MARGIN_X = 2
    MARGIN_Y = 10
    MAX_PIXMAP_HEIGHT = 12

    def __init__(self, *args, **kwargs):
        super().__init__(self.MARGIN_X, *args, **kwargs)
        self._setup_body()

    @property
    def x(self):
        return time_x_converter.get_x_by_time(self.get_data("time"))

    def body_y(self):
        return (
            self.MARGIN_Y * self.timeline_ui.get_scale_for_symbols_above_staff()
            + self.timeline_ui.get_y_for_symbols_above_staff(
                self.get_data("staff_index")
            )
        )

    def _setup_body(self):
        self.body = TimeSignatureBody(
            self.x,
            self.body_y(),
            self.get_data("numerator"),
            self.get_data("denominator"),
            self.get_body_digit_height(),
            self.timeline_ui.pixmaps["time signature"],
        )
        self.body.moveBy(self.x_offset, 0)
        self.scene.addItem(self.body)

    def get_body_digit_height(self) -> int:
        return min(
            self.MAX_PIXMAP_HEIGHT,
            int(
                (self.timeline_ui.get_height_for_symbols_above_staff() - self.MARGIN_Y)
                / 2
            ),
        )

    def child_items(self):
        return [self.body]

    def update_position(self):
        self.body.set_position(
            self.x
            + self.x_offset
            + (self.margin_x if self.x_offset is not None else 0),
            self.body_y(),
        )
        self.body.set_height(self.get_body_digit_height())

    def on_components_deserialized(self):
        self.update_position()

    def selection_triggers(self):
        return []


class TimeSignatureBody(QGraphicsItem):
    def __init__(
        self,
        x: float,
        y: float,
        numerator: int,
        denominator: int,
        digit_height: int,
        pixmaps: dict[int, QPixmap],
    ):
        super().__init__()
        self.pixmaps = pixmaps
        self.numerator = numerator
        self.denominator = denominator
        self.set_numerator_items(numerator, digit_height)
        self.set_denominator_items(denominator, digit_height)
        self.align_pixmaps(numerator, denominator)
        self.set_position(x, y)

    def get_scaled_pixmap(self, digit: int | str, height: int):
        return self.pixmaps[int(digit)].scaledToHeight(
            height, mode=Qt.TransformationMode.SmoothTransformation
        )

    def set_numerator_items(self, numerator: int, height: int):
        self.numerator_items = []
        for i, digit in enumerate(str(numerator)):
            item = QGraphicsPixmapItem(self.get_scaled_pixmap(digit, height), self)
            item.digit = int(digit)
            item.setPos(i * item.pixmap().width(), 0)
            self.numerator_items.append(item)

    def set_denominator_items(self, denominator: int, height: int):
        self.denominator_items = []
        for i, digit in enumerate(str(denominator)):
            item = QGraphicsPixmapItem(self.get_scaled_pixmap(digit, height), self)
            item.digit = int(digit)
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

    def set_height(self, height: int):
        for i, item in enumerate(self.numerator_items):
            item.setPixmap(self.get_scaled_pixmap(item.digit, height))
            item.setPos(i * item.pixmap().width(), 0)

        for i, item in enumerate(self.denominator_items):
            item.setPixmap(self.get_scaled_pixmap(item.digit, height))
            item.setPos(i * item.pixmap().width(), item.pixmap().height())

        self.align_pixmaps(self.numerator, self.denominator)

    def set_position(self, x: float, y: float):
        self.setPos(x, y)

    def canvas_items(self):
        return self.numerator_items + self.denominator_items

    def boundingRect(self):
        items = self.canvas_items()
        bounding_rect = items[0].boundingRect()
        for item in items[1:]:
            bounding_rect = bounding_rect.united(item.boundingRect())
        return bounding_rect

    def paint(self, painter, option, widget):
        ...
