from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem

from tilia.dirs import IMG_DIR
from tilia.timelines.score.components import Clef
from tilia.ui.timelines.score.element.with_collision import (
    TimelineUIElementWithCollision,
)


class ClefUI(TimelineUIElementWithCollision):
    def __init__(self, *args, **kwargs):
        super().__init__(0, *args, **kwargs)
        self._setup_body()

    @property
    def icon_path(self):
        if not self.get_data("icon"):
            return IMG_DIR / "clef-unknown.svg"
        return IMG_DIR / self.get_data("icon")

    def _setup_body(self):
        self.body = ClefBody(
            self.x,
            self.timeline_ui.get_y_for_symbols_above_staff(
                self.get_data("staff_index")
            ),
            self.height(),
            self.icon_path,
        )
        self.body.moveBy(self.x_offset, 0)
        self.scene.addItem(self.body)

    def height(self) -> float:
        return self.timeline_ui.get_height_for_symbols_above_staff()

    def child_items(self):
        return [self.body]

    def update_position(self):
        self.body.set_position(
            self.x + self.x_offset,
            self.timeline_ui.get_y_for_symbols_above_staff(
                self.get_data("staff_index")
            ),
        )
        self.body.set_height(self.height())

    def central_step(self) -> tuple[int, int]:
        return self.get_data("central_step")()

    def on_components_deserialized(self):
        self.update_position()

    def selection_triggers(self):
        return []

    def shorthand(self) -> Clef.Shorthand | None:
        return self.tl_component.shorthand()

    def on_deselect(self):
        return

    def on_select(self):
        return


class ClefBody(QGraphicsPixmapItem):
    def __init__(self, x: float, y: float, height: float, path: Path):
        super().__init__()
        self.set_icon(str(path.resolve()))
        self.set_height(height)
        self.set_position(x, y)

    def set_icon(self, path: str):
        self._pixmap = QPixmap(path)
        self.setPixmap(QPixmap(path))

    def set_height(self, height: float):
        self.setPixmap(
            self._pixmap.scaledToHeight(
                height, mode=Qt.TransformationMode.SmoothTransformation
            )
        )

    def set_position(self, x: float, y: float):
        self.setPos(x, y)
