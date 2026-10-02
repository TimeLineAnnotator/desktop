"""
Time signatures drawn as stacked engraved glyphs, shared by the score and
beat timelines.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsPixmapItem

GLYPH_ICON_NAMES = {str(n): f"time-signature-{n}" for n in range(10)} | {
    "/": "time-signature-slash"
}
GLYPH_PIXMAP_SIZE = 48
# A space between the whole part and the fraction of a numerator such as
# "4 1/3" is this fraction of a glyph's width.
SPACE_WIDTH_RATIO = 0.5


def load_time_signature_pixmaps() -> dict[str, QPixmap]:
    return {
        char: QIcon.fromTheme(name).pixmap(GLYPH_PIXMAP_SIZE, GLYPH_PIXMAP_SIZE)
        for char, name in GLYPH_ICON_NAMES.items()
    }


def tint_pixmap(pixmap: QPixmap, color: QColor) -> QPixmap:
    tinted = QPixmap(pixmap.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()
    return tinted


class GlyphPixmap(QGraphicsPixmapItem):
    char = "0"


class TimeSignatureBody(QGraphicsItemGroup):
    """
    A numerator stacked over a denominator. Either may be any text made of
    digits, "/" and spaces, so a numerator can be "4 1/3".
    """

    def __init__(
        self,
        x: float,
        y: float,
        numerator: int | str,
        denominator: int | str,
        digit_height: int,
        pixmaps: dict[str, QPixmap],
        color: QColor | None = None,
    ):
        super().__init__()
        self.pixmaps = pixmaps
        self.numerator = str(numerator)
        self.denominator = str(denominator)
        self.color = color
        self.digit_height = digit_height
        self.numerator_items = self._create_items(self.numerator)
        self.denominator_items = self._create_items(self.denominator)
        self._layout()
        self.set_position(x, y)

    def _get_scaled_pixmap(self, char: str, height: int) -> QPixmap:
        pixmap = self.pixmaps[char].scaledToHeight(
            height, mode=Qt.TransformationMode.SmoothTransformation
        )
        if self.color is not None:
            pixmap = tint_pixmap(pixmap, self.color)
        return pixmap

    def _create_items(self, text: str) -> list[GlyphPixmap]:
        items = []
        for char in text:
            if char == " ":
                continue
            item = GlyphPixmap(self._get_scaled_pixmap(char, self.digit_height), self)
            item.char = char
            items.append(item)
        return items

    def _layout_row(self, text: str, items: list[GlyphPixmap], y: float) -> float:
        """Places a row's glyphs from x=0 and returns the row's width."""
        glyph_width = items[0].pixmap().width() if items else 0
        x = 0.0
        item_iter = iter(items)
        for char in text:
            if char == " ":
                x += glyph_width * SPACE_WIDTH_RATIO
                continue
            item = next(item_iter)
            item.setPos(x, y)
            x += item.pixmap().width()
        return x

    def _layout(self) -> None:
        row_height = self.digit_height
        numerator_width = self._layout_row(self.numerator, self.numerator_items, 0)
        denominator_width = self._layout_row(
            self.denominator, self.denominator_items, row_height
        )
        # Center the narrower row under or over the wider one.
        difference = denominator_width - numerator_width
        shorter = self.numerator_items if difference > 0 else self.denominator_items
        for item in shorter:
            item.moveBy(abs(difference) / 2, 0)

    @property
    def width(self) -> float:
        return self.childrenBoundingRect().width()

    def set_height(self, height: int) -> None:
        self.digit_height = height
        for item in self.numerator_items + self.denominator_items:
            item.setPixmap(self._get_scaled_pixmap(item.char, height))
        self._layout()

    def set_color(self, color: QColor | None) -> None:
        self.color = color
        self.set_height(self.digit_height)

    def set_position(self, x: float, y: float) -> None:
        self.setPos(x, y)

    def canvas_items(self) -> list[GlyphPixmap]:
        return self.numerator_items + self.denominator_items
