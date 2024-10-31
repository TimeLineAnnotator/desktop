from __future__ import annotations

from typing import TYPE_CHECKING

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem

from tilia.ui.timelines.score.element.with_collision import TimelineUIElementWithCollision

if TYPE_CHECKING:
    from tilia.ui.timelines.score import ScoreTimelineUI


class KeySignatureUI(TimelineUIElementWithCollision):
    def __init__(self, id: int, timeline_ui: ScoreTimelineUI, scene: QGraphicsScene):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)
        self._setup_body()

    @property
    def icon_path(self):
        fifths = self.get_data('fifths')
        if fifths == 0:
            return Path('ui', 'img', 'key-signature-no-accidentals.svg')
        accidental_count = abs(fifths)
        accidental_type = 'flats' if fifths < 0 else 'sharps'
        path = Path('ui', 'img', f'key-signature-{accidental_count}-{accidental_type}.svg')
        return path

    def _setup_body(self):
        self.body = KeySignatureBody(self.x, self.height(), self.icon_path)
        self.body.moveBy(self.x_offset, 0)
        self.scene.addItem(self.body)

    def height(self) -> int:
        return self.timeline_ui.get_height_for_symbols_above_staff()

    def child_items(self):
        return [self.body]

    def update_position(self):
        self.body.set_position(self.x + self.x_offset)

    def selection_triggers(self):
        return []


class KeySignatureBody(QGraphicsPixmapItem):
    def __init__(self, x: float, height: int, path: Path):
        super().__init__()
        self.set_icon(str(path.resolve()))
        self.set_height(height)
        self.set_position(x)

    def set_icon(self, path: str):
        self.setPixmap(QPixmap(path))

    def set_height(self, height: int):
        self.setPixmap(self.pixmap().scaledToHeight(height, mode=Qt.TransformationMode.SmoothTransformation))

    def set_position(self, x: float):
        self.setPos(x, 0)
