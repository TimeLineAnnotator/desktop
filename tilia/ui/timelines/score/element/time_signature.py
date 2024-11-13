from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsItem, QGraphicsPixmapItem

from tilia.ui.coords import get_x_by_time
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.score.element.with_collision import TimelineUIElementWithCollision

if TYPE_CHECKING:
    from tilia.ui.timelines.score import ScoreTimelineUI


class TimeSignatureUI(TimelineUIElementWithCollision):
    MARGIN_X = 2

    def __init__(self, id: int, timeline_ui: ScoreTimelineUI, scene: QGraphicsScene, **kwargs):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene, margin_x=TimeSignatureUI.MARGIN_X)
        self._setup_body()

    def get_icon_path(self, number: int) -> Path:
        return Path('ui', 'img', f'time-signature-{number}.svg')

    @property
    def x(self):
        return get_x_by_time(self.get_data('time'))

    def _setup_body(self):
        self.body = TimeSignatureBody(self.x, self.timeline_ui.get_y_for_symbols_above_staff(self.get_data('staff_index')), self.get_icon_path(self.get_data('numerator')), self.get_icon_path(self.get_data('denominator')))
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

    def __init__(self, x: float, y: float, numerator_path: Path, denominator_path: Path):
        super().__init__()
        self.set_numerator_item(str(numerator_path.resolve()))
        self.set_denominator_item(str(denominator_path.resolve()))
        self.set_position(x, y)

    def set_numerator_item(self, path: str):
        self.numerator_item = QGraphicsPixmapItem(QPixmap(path).scaledToHeight(self.PIXMAP_HEIGHT, mode=Qt.TransformationMode.SmoothTransformation), self)

    def set_denominator_item(self, path: str):
        self.denominator_item = QGraphicsPixmapItem(QPixmap(path).scaledToHeight(self.PIXMAP_HEIGHT, mode=Qt.TransformationMode.SmoothTransformation), self)
        self.denominator_item.setPos(0, self.numerator_item.pixmap().height())

    def set_position(self, x: float, y: float):
        self.setPos(x, y + self.TOP_MARGIN)

    def boundingRect(self):
        return self.numerator_item.boundingRect().united(self.denominator_item.boundingRect())

    def paint(self, painter, option, widget): ...
