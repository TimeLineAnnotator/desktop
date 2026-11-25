"""How the mark is drawn that stands in a label where TiLiA can't read what a file
holds: in Arial, the rest of the label in MusAnalysis, which draws a question mark as a
bar (Anne, 2026-11-25, TimeLineAnnotator/project-management#689, b)."""

import os
from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QImage, QPainter
from PySide6.QtWidgets import QGraphicsTextItem, QStyleOptionGraphicsItem

from tests.file.test_open_through_core import (
    HARMONIES,
    a_file,
    a_harmony,
    a_harmony_timeline,
    a_mode,
    open_file,
    together,
    with_media_length,
)
from tilia.ui import commands

MUSANALYSIS, ARIAL = "MusAnalysis", "Arial"
MARK = ("?", ARIAL)


@pytest.fixture
def arial(qtui):
    """A font for Arial that isn't MusAnalysis: Arial, or the one the system has for
    it. Qt's offscreen platform finds none of Windows' fonts."""
    added = -1
    if QFontInfo(QFont(ARIAL, 10)).family() == MUSANALYSIS:
        path = Path(os.environ.get("SystemRoot", "")) / "Fonts" / "arial.ttf"
        if path.is_file():
            added = QFontDatabase.addApplicationFont(str(path))
    if QFontInfo(QFont(ARIAL, 10)).family() == MUSANALYSIS:
        pytest.skip("This system has no font for Arial.")
    yield
    if added != -1:
        QFontDatabase.removeApplicationFont(added)


@pytest.fixture
def open_a_file_with(qtui, tmp_path):
    """Opens a file with these components in its harmony timeline, and gives that
    timeline's UI."""

    def open_(*components):
        change = together(a_harmony_timeline(*components), with_media_length(100.0))
        assert open_file(a_file(tmp_path, change))
        return qtui.timeline_uis.get_timeline_ui(HARMONIES)

    return open_


def in_order(elements):
    return sorted(elements, key=lambda element: element.get_data("time"))


def runs(body) -> list[tuple[str, str]]:
    """What a label draws, each part of its text with the font it is drawn in."""
    found = []
    part = body.document().firstBlock().begin()
    while not part.atEnd():
        fragment = part.fragment()
        families = fragment.charFormat().fontFamilies() or [body.font().family()]
        found.append((fragment.text(), families[0]))
        part += 1
    return found


def baseline(body) -> float:
    """Where the line a label's letters stand on is, in the timeline."""
    line = body.document().firstBlock().layout().lineAt(0)
    return body.y() + body.document().documentMargin() + line.y() + line.ascent()


def drawn(item: QGraphicsTextItem) -> QImage:
    """What an item draws, alone."""
    size = item.boundingRect().size().toSize()
    image = QImage(size, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    return image


def a_text(text: str, family: str, bold: bool = False) -> QGraphicsTextItem:
    item = QGraphicsTextItem(text)
    font = QFont(family, 10)
    font.setBold(bold)
    item.setFont(font)
    return item


# Each label with a mark: what the file holds, and what is drawn.
HARMONIES_WITH_A_MARK = {
    "quality, letters": ({"quality": "some-quality"}, [("G", MUSANALYSIS), MARK]),
    "quality, letters, with an accidental": (
        {"quality": "some-quality", "accidental": -1},
        [("G`b", MUSANALYSIS), MARK],
    ),
    "quality, roman numeral": (
        {"quality": "some-quality", "display_mode": "roman"},
        [("V", MUSANALYSIS), MARK],
    ),
    "applied to": (
        {"applied_to": 9, "display_mode": "roman"},
        [("V/", MUSANALYSIS), MARK],
    ),
    "quality and applied to": (
        {"quality": "some-quality", "applied_to": 9, "display_mode": "roman"},
        [("V", MUSANALYSIS), MARK, ("/", MUSANALYSIS), MARK],
    ),
    "root, letters": ({"step": 9}, [MARK]),
    "root, roman numeral": ({"step": 9, "display_mode": "roman"}, [MARK]),
    "root, a display TiLiA doesn't know": (
        {"step": 9, "display_mode": "some-display"},
        [MARK],
    ),
}
MODES_WITH_A_MARK = {
    "tonic": ({"step": 9}, [MARK]),
    "type": ({"type": "some-future-type"}, [("C", MUSANALYSIS), MARK]),
    "type, with an accidental": (
        {"type": "some-future-type", "step": 6, "accidental": -1},
        [("B`b", MUSANALYSIS), MARK],
    ),
}


class TestTheMarkIsDrawnInArial:
    @pytest.mark.parametrize(
        "attrs, expected",
        HARMONIES_WITH_A_MARK.values(),
        ids=HARMONIES_WITH_A_MARK.keys(),
    )
    def test_in_a_harmony_s_label(
        self, open_a_file_with, tilia, tilia_errors, attrs, expected
    ):
        (harmony,) = open_a_file_with(a_mode(), a_harmony(**attrs)).harmonies()

        assert runs(harmony.body) == expected
        assert harmony.body.toPlainText() == harmony.label
        assert not tilia.is_file_modified()
        tilia_errors.assert_no_error()

    def test_in_a_roman_numeral_after_a_key_it_can_t_read(self, open_a_file_with):
        (harmony,) = open_a_file_with(
            a_mode(type="some-future-type"), a_harmony(display_mode="roman")
        ).harmonies()

        assert runs(harmony.body) == [MARK]

    @pytest.mark.parametrize(
        "attrs, expected", MODES_WITH_A_MARK.values(), ids=MODES_WITH_A_MARK.keys()
    )
    def test_in_a_mode_s_label(self, open_a_file_with, tilia, attrs, expected):
        (mode,) = open_a_file_with(a_mode(**attrs)).modes()

        assert runs(mode.body) == expected
        assert mode.body.toPlainText() == mode.label
        assert not tilia.is_file_modified()

    def test_it_draws_arial_s_question_mark(self, arial, open_a_file_with):
        timeline_ui = open_a_file_with(a_mode(step=9), a_harmony(step=9))
        (mode,), (harmony,) = timeline_ui.modes(), timeline_ui.harmonies()

        for body in (mode.body, harmony.body):
            assert drawn(body) == drawn(a_text("?", ARIAL))
            assert drawn(body) != drawn(a_text("?", MUSANALYSIS))


class TestAnotherLabelIsDrawnAsBefore:
    @pytest.mark.parametrize(
        "attrs, expected",
        [
            ({}, [("G", MUSANALYSIS)]),
            ({"display_mode": "roman"}, [("V", MUSANALYSIS)]),
        ],
        ids=["letters", "roman numeral"],
    )
    def test_a_harmony_s(self, open_a_file_with, attrs, expected):
        (harmony,) = open_a_file_with(a_mode(), a_harmony(**attrs)).harmonies()

        assert runs(harmony.body) == expected

    @pytest.mark.parametrize(
        "mode_type, expected",
        [
            ("major", [("C", MUSANALYSIS)]),
            ("dorian", [("C\xa0", MUSANALYSIS), ("Dorian", ARIAL)]),
            ("ionian", [("C\xa0", MUSANALYSIS), ("Ionian", ARIAL)]),
        ],
    )
    def test_a_mode_s(self, open_a_file_with, mode_type, expected):
        (mode,) = open_a_file_with(a_mode(type=mode_type)).modes()

        assert runs(mode.body) == expected

    @pytest.mark.parametrize("text", ["?", "V?", "why? <b>C?</b> & so on"])
    @pytest.mark.parametrize(
        "font_type, family", [("analytic", MUSANALYSIS), ("normal", ARIAL)]
    )
    @pytest.mark.parametrize("root", [4, 9], ids=["a root", "a root it can't read"])
    def test_a_question_mark_of_a_person_s_own(
        self, open_a_file_with, text, font_type, family, root
    ):
        # In a custom text, in the font they chose.
        (harmony,) = open_a_file_with(
            a_harmony(
                step=root,
                display_mode="custom",
                custom_text=text,
                custom_text_font_type=font_type,
            )
        ).harmonies()

        assert runs(harmony.body) == [(text, family)]
        assert drawn(harmony.body) == drawn(a_text(text, family))

    def test_once_its_quality_can_be_read(self, open_a_file_with):
        (harmony,) = open_a_file_with(
            a_mode(), a_harmony(quality="some-quality")
        ).harmonies()
        harmony.set_data("quality", "major")
        harmony.update_label()

        assert runs(harmony.body) == [("G", MUSANALYSIS)]

    def test_once_its_type_can_be_read(self, open_a_file_with):
        (mode,) = open_a_file_with(a_mode(type="some-future-type")).modes()
        mode.set_data("type", "dorian")
        mode.update_label()

        assert runs(mode.body) == [("C\xa0", MUSANALYSIS), ("Dorian", ARIAL)]
        # Where a font for Arial higher than MusAnalysis would move it.
        assert not mode.body.has_marks
        assert mode.body.y() == mode.y


@pytest.mark.usefixtures("arial")
class TestItsPlace:
    """The line of a label with a mark is where the others' is, and the label is
    centred on its time."""

    @staticmethod
    def open_labels(open_a_file_with):
        """A label without a mark, and each with one, of harmonies and of modes."""
        harmonies = [
            a_harmony(time=10.0 + n, **attrs)
            for n, (attrs, _) in enumerate(HARMONIES_WITH_A_MARK.values())
        ]
        modes = [
            a_mode(time=50.0 + n, **attrs)
            for n, (attrs, _) in enumerate(MODES_WITH_A_MARK.values())
        ]
        return open_a_file_with(
            a_mode(),
            a_harmony(time=1.0),
            a_harmony(time=2.0, display_mode="roman"),
            *harmonies,
            *modes,
        )

    def test_the_lines_of_the_harmonies(self, open_a_file_with):
        timeline_ui = self.open_labels(open_a_file_with)
        letters, numeral, *marked = in_order(timeline_ui.harmonies())

        assert len(marked) == len(HARMONIES_WITH_A_MARK)
        assert baseline(numeral.body) == baseline(letters.body)
        for harmony in marked:
            assert baseline(harmony.body) == pytest.approx(baseline(letters.body))

    def test_the_lines_of_the_modes(self, open_a_file_with):
        timeline_ui = self.open_labels(open_a_file_with)
        plain, *marked = in_order(timeline_ui.modes())

        assert len(marked) == len(MODES_WITH_A_MARK)
        for mode in marked:
            assert baseline(mode.body) == pytest.approx(baseline(plain.body))

    def test_they_are_centred_on_their_times(self, open_a_file_with):
        timeline_ui = self.open_labels(open_a_file_with)

        for element in timeline_ui:
            centre = element.body.sceneBoundingRect().center().x()
            assert centre == pytest.approx(element.x)

    def test_they_stay_there_when_the_timeline_is_zoomed(self, open_a_file_with):
        timeline_ui = self.open_labels(open_a_file_with)
        before = [baseline(element.body) for element in in_order(timeline_ui)]

        commands.execute("view.zoom.in")

        assert [baseline(element.body) for element in in_order(timeline_ui)] == before
        for element in timeline_ui:
            centre = element.body.sceneBoundingRect().center().x()
            assert centre == pytest.approx(element.x)

    @pytest.mark.parametrize("font_type", ["analytic", "normal"])
    @pytest.mark.parametrize("attrs", [{"step": 9}, {"quality": "some-quality"}])
    def test_a_custom_text_shown_as_letters(self, open_a_file_with, attrs, font_type):
        # The font changes with it, from the one the person chose.
        timeline_ui = open_a_file_with(
            a_mode(),
            a_harmony(),
            a_harmony(
                time=5.0,
                display_mode="custom",
                custom_text="a text much longer than the mark",
                custom_text_font_type=font_type,
                **attrs,
            ),
        )
        plain, changed = in_order(timeline_ui.harmonies())

        timeline_ui.set_elements_attr([changed], "display_mode", "letter")

        assert runs(changed.body)[-1] == MARK
        assert baseline(changed.body) == pytest.approx(baseline(plain.body))
        centre = changed.body.sceneBoundingRect().center().x()
        assert centre == pytest.approx(changed.x)

    @pytest.mark.parametrize("font_type", ["analytic", "normal"])
    def test_a_custom_text_shown_as_a_roman_numeral(self, open_a_file_with, font_type):
        timeline_ui = open_a_file_with(
            a_mode(type="some-future-type"),
            a_harmony(),
            a_harmony(
                time=5.0,
                display_mode="custom",
                custom_text="a text much longer than the mark",
                custom_text_font_type=font_type,
            ),
        )
        plain, changed = in_order(timeline_ui.harmonies())
        timeline_ui.select_element(changed)

        commands.execute("timeline.harmony.component.display_as_roman")

        assert runs(changed.body) == [MARK]
        assert baseline(changed.body) == pytest.approx(baseline(plain.body))
        centre = changed.body.sceneBoundingRect().center().x()
        assert centre == pytest.approx(changed.x)


@pytest.mark.usefixtures("arial")
class TestWhenSelected:
    @pytest.mark.parametrize(
        "component",
        [a_mode(step=9), a_harmony(step=9)],
        ids=["a mode", "a harmony"],
    )
    def test_the_mark_is_bold(self, open_a_file_with, component):
        timeline_ui = open_a_file_with(component)
        (element,) = timeline_ui

        timeline_ui.select_element(element)
        assert drawn(element.body) == drawn(a_text("?", ARIAL, bold=True))

        timeline_ui.deselect_element(element)
        assert drawn(element.body) == drawn(a_text("?", ARIAL))

    @pytest.mark.parametrize(
        "component",
        [a_mode(type="some-future-type"), a_harmony(quality="some-quality")],
        ids=["a mode", "a harmony"],
    )
    def test_so_is_one_after_a_letter(self, open_a_file_with, component):
        timeline_ui = open_a_file_with(component)
        (element,) = timeline_ui
        plain = drawn(element.body)

        timeline_ui.select_element(element)
        assert element.body.font().bold()
        assert runs(element.body)[-1] == MARK
        assert drawn(element.body) != plain

        timeline_ui.deselect_element(element)
        assert drawn(element.body) == plain

    def test_one_shown_while_it_is_selected_is_bold(self, open_a_file_with):
        # As "Display as roman numeral" shows it.
        timeline_ui = open_a_file_with(a_mode(type="some-future-type"), a_harmony())
        (harmony,) = timeline_ui.harmonies()
        timeline_ui.select_element(harmony)

        commands.execute("timeline.harmony.component.display_as_roman")

        assert drawn(harmony.body) == drawn(a_text("?", ARIAL, bold=True))
