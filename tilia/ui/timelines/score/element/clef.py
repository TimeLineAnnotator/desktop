from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsPixmapItem

from tilia.ui.timelines.score.element.with_collision import TimelineUIElementWithCollision

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene
    from tilia.ui.timelines.score import ScoreTimelineUI


class ClefUI(TimelineUIElementWithCollision):
    def __init__(self, id: int, timeline_ui: ScoreTimelineUI, scene: QGraphicsScene, **kwargs):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)
        self._setup_body()

    @property
    def icon_path(self):
        return Path('ui', 'img', self.get_data('icon'))

    def _setup_body(self):
        self.body = ClefBody(self.x, self.height(), self.icon_path)
        self.body.moveBy(self.x_offset, 0)
        self.scene.addItem(self.body)

    def height(self) -> float:
        return self.timeline_ui.get_height_for_symbols_above_staff()

    def child_items(self):
        return [self.body]

    def update_position(self):
        self.body.set_position(self.x + self.x_offset)

    def central_step(self) -> tuple[int, int]:
        return self.get_data('central_step')()


class ClefBody(QGraphicsPixmapItem):
    def __init__(self, x: float, height: float, path: Path):
        super().__init__()
        self.set_icon(str(path.resolve()))
        self.set_height(height)
        self.set_position(x)

    def set_icon(self, path: str):
        self.setPixmap(QPixmap(path))

    def set_height(self, height: float):
        self.setPixmap(self.pixmap().scaledToHeight(height, mode=Qt.TransformationMode.SmoothTransformation))

    def set_position(self, x: float):
        self.setPos(x, 0)
