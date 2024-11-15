from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsPixmapItem

from tilia.timelines.score.components import Clef
from tilia.ui.timelines.score.element.with_collision import TimelineUIElementWithCollision


class KeySignatureUI(TimelineUIElementWithCollision):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_body()

    @staticmethod
    def _clef_shorthand_to_icon_path_string(shorthand: Clef.Shorthand | None) -> str:
        if not shorthand:
            # Key signature not implmemented
            # for custom clefs. Using "treble"
            # just to prevent a crash
            return 'treble'
        return {
            Clef.Shorthand.BASS: 'bass',
            Clef.Shorthand.TREBLE: 'treble',
            Clef.Shorthand.TREBLE_8VB: 'treble',
            Clef.Shorthand.ALTO: 'alto',
        }[shorthand]

    @property
    def icon_path(self) -> Path | None:
        fifths = self.get_data('fifths')
        if fifths == 0:
            return Path('ui', 'img', 'key-signature-no-accidentals.svg')
        accidental_count = abs(fifths)
        accidental_type = 'flats' if fifths < 0 else 'sharps'
        clef = self.timeline_ui.get_clef_by_time(self.get_data('time'), self.get_data('staff_index'))
        if not clef:
            return None
        clef_string = self._clef_shorthand_to_icon_path_string(clef.shorthand())
        path = Path('ui', 'img', f'key-signature-{clef_string}-{accidental_count}-{accidental_type}.svg')
        return path

    def _setup_body(self):
        self.body = KeySignatureBody(self.x, self.timeline_ui.get_y_for_symbols_above_staff(self.get_data('staff_index')), self.height(), self.icon_path)
        self.body.moveBy(self.x_offset, 0)
        self.scene.addItem(self.body)

    def height(self) -> int:
        return self.timeline_ui.get_height_for_symbols_above_staff()

    def child_items(self):
        return [self.body]

    def update_position(self):
        self.body.set_position(self.x + self.x_offset, self.timeline_ui.get_y_for_symbols_above_staff(self.get_data('staff_index')))

    def selection_triggers(self):
        return []


class KeySignatureBody(QGraphicsPixmapItem):
    def __init__(self, x: float, y: float, height: int, path: Path):
        super().__init__()
        self.set_icon(str(path.resolve()))
        self.set_height(height)
        self.set_position(x, y)

    def set_icon(self, path: str):
        self.setPixmap(QPixmap(path))

    def set_height(self, height: int):
        self.setPixmap(self.pixmap().scaledToHeight(height, mode=Qt.TransformationMode.SmoothTransformation))

    def set_position(self, x: float, y: float):
        self.setPos(x, y)
