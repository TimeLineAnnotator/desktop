"""
Time signatures drawn as stacked engraved glyphs, shared by the score and
beat timelines.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsPixmapItem

GLYPH_ICON_NAMES = {str(n): f"time-signature-{n}" for n in range(10)} | {
    "+": "time-signature-plus",
    "/": "time-signature-slash",
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


class Glyph(QGraphicsPixmapItem):
    """A digit, slash or plus of a time signature, in the numerator's row, the
    denominator's, or between two pairs."""

    NUMERATOR = "numerator"
    DENOMINATOR = "denominator"
    BETWEEN = "between"

    def __init__(self, character: str, row: str, parent: QGraphicsItemGroup):
        super().__init__(parent)
        self.character = character
        self.row = row


class TimeSignatureBody(QGraphicsItemGroup):
    """
    A time signature's numerators over its denominators, as written. A
    numerator may be composite, such as 3+2, or hold a fraction after a space,
    such as "4 1/3". Several pairs (2/4 + 3/8) are drawn side by side, with a
    plus halfway down between them. Each numerator is centred over its
    denominator.
    """

    def __init__(
        self,
        x: float,
        y: float,
        pairs: Sequence[tuple[int | str, int | str]],
        digit_height: int,
        pixmaps: dict[str, QPixmap],
        color: QColor | None = None,
    ) -> None:
        super().__init__()
        self.pixmaps = pixmaps
        self.color = color
        self.digit_height = digit_height
        # Each pair's numerator and denominator as text, which keeps its
        # spaces, and as glyphs; and each plus between two pairs.
        self.texts: list[tuple[str, str]] = []
        self.columns: list[tuple[list[Glyph], list[Glyph]]] = []
        self.pluses: list[Glyph] = []
        for i, (numerator, denominator) in enumerate(pairs):
            if i > 0:
                self.pluses.append(Glyph("+", Glyph.BETWEEN, self))
            numerator, denominator = str(numerator), str(denominator)
            self.texts.append((numerator, denominator))
            self.columns.append(
                (
                    self._create_glyphs(numerator, Glyph.NUMERATOR),
                    self._create_glyphs(denominator, Glyph.DENOMINATOR),
                )
            )
        self.glyphs = self.pluses + [
            glyph
            for numerator, denominator in self.columns
            for glyph in numerator + denominator
        ]
        self.set_height(digit_height)
        self.set_position(x, y)

    def _create_glyphs(self, text: str, row: str) -> list[Glyph]:
        return [Glyph(character, row, self) for character in text if character != " "]

    def get_scaled_pixmap(self, character: str, height: int) -> QPixmap:
        pixmap = self.pixmaps[character].scaledToHeight(
            height, mode=Qt.TransformationMode.SmoothTransformation
        )
        if self.color is not None:
            pixmap = tint_pixmap(pixmap, self.color)
        return pixmap

    def set_height(self, height: int) -> None:
        self.digit_height = height
        for glyph in self.glyphs:
            glyph.setPixmap(self.get_scaled_pixmap(glyph.character, height))

        x = 0.0
        for i, (texts, (numerator, denominator)) in enumerate(
            zip(self.texts, self.columns, strict=True)
        ):
            numerator_text, denominator_text = texts
            if i > 0:
                plus = self.pluses[i - 1]
                gap = height / 4
                plus.setPos(x + gap, height / 2)
                x += plus.pixmap().width() + 2 * gap
            numerator_width = _row_width(numerator_text, numerator)
            denominator_width = _row_width(denominator_text, denominator)
            width = max(numerator_width, denominator_width)
            _place_row(numerator_text, numerator, x + (width - numerator_width) / 2, 0)
            _place_row(
                denominator_text,
                denominator,
                x + (width - denominator_width) / 2,
                height,
            )
            x += width

    @property
    def width(self) -> float:
        return self.childrenBoundingRect().width()

    def set_color(self, color: QColor | None) -> None:
        self.color = color
        self.set_height(self.digit_height)

    def set_position(self, x: float, y: float) -> None:
        self.setPos(x, y)

    def canvas_items(self) -> list[Glyph]:
        return self.glyphs


def _space_width(glyphs: list[Glyph]) -> float:
    return glyphs[0].pixmap().width() * SPACE_WIDTH_RATIO if glyphs else 0


def _row_width(text: str, glyphs: list[Glyph]) -> float:
    return sum(glyph.pixmap().width() for glyph in glyphs) + text.count(
        " "
    ) * _space_width(glyphs)


def _place_row(text: str, glyphs: list[Glyph], x: float, y: float) -> None:
    """Places a row's glyphs from `x`, leaving a gap for each space."""
    space = _space_width(glyphs)
    remaining = iter(glyphs)
    for character in text:
        if character == " ":
            x += space
            continue
        glyph = next(remaining)
        glyph.setPos(x, y)
        x += glyph.pixmap().width()
