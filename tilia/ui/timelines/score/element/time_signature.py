from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsPixmapItem

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
            self.tl_component.get_pairs(),
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

    def on_deselect(self):
        return

    def on_select(self):
        return


class TimeSignatureBody(QGraphicsItemGroup):
    """A time signature's numerators over its denominators, as written, such as
    3+2 over 8. Two pairs (2/4 + 3/8) are drawn side by side, with a plus
    halfway down between them."""

    def __init__(
        self,
        x: float,
        y: float,
        pairs: list[tuple[str, int]],
        digit_height: int,
        pixmaps: dict[str, QPixmap],
    ):
        super().__init__()
        self.pixmaps = pixmaps
        # Each pair's numerator and denominator glyphs, and each plus between
        # two pairs.
        self.columns: list[tuple[list[Glyph], list[Glyph]]] = []
        self.pluses: list[Glyph] = []
        for i, (numerator, denominator) in enumerate(pairs):
            if i > 0:
                self.pluses.append(Glyph("+", Glyph.BETWEEN, self))
            self.columns.append(
                (
                    [Glyph(c, Glyph.NUMERATOR, self) for c in numerator],
                    [Glyph(c, Glyph.DENOMINATOR, self) for c in str(denominator)],
                )
            )
        self.glyphs = self.pluses + [
            glyph
            for numerator, denominator in self.columns
            for glyph in numerator + denominator
        ]
        self.set_height(digit_height)
        self.set_position(x, y)

    def get_scaled_pixmap(self, character: str, height: int):
        return self.pixmaps[character].scaledToHeight(
            height, mode=Qt.TransformationMode.SmoothTransformation
        )

    def set_height(self, height: int):
        for glyph in self.glyphs:
            glyph.setPixmap(self.get_scaled_pixmap(glyph.character, height))

        x = 0
        for i, (numerator, denominator) in enumerate(self.columns):
            if i > 0:
                plus = self.pluses[i - 1]
                gap = height / 4
                plus.setPos(x + gap, height / 2)
                x += plus.pixmap().width() + 2 * gap
            width = max(_row_width(numerator), _row_width(denominator))
            _place_row(numerator, x + (width - _row_width(numerator)) / 2, 0)
            _place_row(denominator, x + (width - _row_width(denominator)) / 2, height)
            x += width

    def set_position(self, x: float, y: float):
        self.setPos(x, y)

    def canvas_items(self):
        return self.glyphs


def _row_width(glyphs: list[Glyph]) -> float:
    return sum(glyph.pixmap().width() for glyph in glyphs)


def _place_row(glyphs: list[Glyph], x: float, y: float):
    for glyph in glyphs:
        glyph.setPos(x, y)
        x += glyph.pixmap().width()


class Glyph(QGraphicsPixmapItem):
    """A digit or plus of a time signature, in the numerator's row, the
    denominator's, or between two pairs."""

    NUMERATOR = "numerator"
    DENOMINATOR = "denominator"
    BETWEEN = "between"

    def __init__(self, character: str, row: str, parent: QGraphicsItemGroup):
        super().__init__(parent)
        self.character = character
        self.row = row
