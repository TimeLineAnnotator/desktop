from PySide6.QtGui import QColor

from tilia.ui.timelines.time_signature_glyphs import (
    GLYPH_ICON_NAMES,
    TimeSignatureBody,
    load_time_signature_pixmaps,
)


def test_every_glyph_has_an_icon(qtui):
    pixmaps = load_time_signature_pixmaps()

    assert set(pixmaps) == set(GLYPH_ICON_NAMES)
    assert all(not pixmap.isNull() for pixmap in pixmaps.values())


def test_whole_and_fraction_numerator(qtui):
    body = TimeSignatureBody(0, 0, "4 1/3", 4, 10, load_time_signature_pixmaps())

    assert [item.char for item in body.numerator_items] == ["4", "1", "/", "3"]
    assert [item.char for item in body.denominator_items] == ["4"]
    # The space leaves a gap between the whole number and the fraction.
    whole, fraction_start = body.numerator_items[0], body.numerator_items[1]
    assert fraction_start.x() > whole.x() + whole.pixmap().width()


def test_narrower_row_is_centered(qtui):
    body = TimeSignatureBody(0, 0, 12, 8, 10, load_time_signature_pixmaps())

    (eight,) = body.denominator_items
    numerator_width = sum(i.pixmap().width() for i in body.numerator_items)
    assert eight.x() == (numerator_width - eight.pixmap().width()) / 2
    assert eight.y() == 10


def test_set_height_keeps_layout(qtui):
    body = TimeSignatureBody(0, 0, 3, 4, 10, load_time_signature_pixmaps())

    body.set_height(20)

    assert body.denominator_items[0].y() == 20
    assert body.numerator_items[0].pixmap().height() == 20


def test_color(qtui):
    body = TimeSignatureBody(0, 0, 3, 4, 10, load_time_signature_pixmaps())

    body.set_color(QColor("red"))

    image = body.numerator_items[0].pixmap().toImage()
    colors = {
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    }
    assert colors == {"#ff0000"}
