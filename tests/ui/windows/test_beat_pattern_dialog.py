import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator
from PySide6.QtTest import QTest

from tests.ui.timelines.beat.interact import patch_beat_pattern_dialog
from tilia.timelines.beat.pattern import parse
from tilia.ui import commands
from tilia.ui.windows.beat_pattern import (
    BeatPatternDialog,
    BeatPatternValidator,
    get_pattern_preview,
)
from tilia.ui.windows.pattern_preview import MAX_TABLE_HEIGHT


def add_beat_timeline():
    # The pattern dialog is what these tests are about, so only the name is
    # passed.
    commands.execute("timelines.add.beat", name="")


class TestValidator:
    @pytest.mark.parametrize(
        "text, state",
        [
            ("4 4 3", QValidator.State.Acceptable),
            ("10[4] 3", QValidator.State.Acceptable),
            ("", QValidator.State.Intermediate),
            ("10[", QValidator.State.Intermediate),
            ("4]", QValidator.State.Intermediate),
            ("0", QValidator.State.Intermediate),
            ("4a", QValidator.State.Invalid),
            ("4,4", QValidator.State.Invalid),
            ("-4", QValidator.State.Invalid),
        ],
    )
    def test_state(self, text, state):
        assert BeatPatternValidator().validate(text, len(text))[0] == state


class TestPatternPreview:
    def test_rows_and_footer(self):
        preview = get_pattern_preview(parse("10[4] 3 15[4]"))

        assert preview.headers == ["Bars", "Beats per bar"]
        assert preview.rows == [("1\u201310", "4"), ("11", "3"), ("12\u201326", "4")]
        assert (
            preview.footer == "26 bars, 103 beats, then the pattern repeats from bar 1."
        )
        assert preview.error == ""

    def test_singular(self):
        preview = get_pattern_preview(parse("1"), beat_count=1)

        assert preview.footer == (
            "1 bar, 1 beat, then the pattern repeats from bar 1.\n1 beat tapped."
        )

    def test_every_run_is_listed(self):
        preview = get_pattern_preview(parse("50[1 2]"))

        assert len(preview.rows) == 100

    def test_beat_count(self):
        footer = get_pattern_preview(parse("4"), beat_count=12).footer

        assert footer.endswith("12 beats tapped.")

    def test_overwritten_bars(self):
        assert get_pattern_preview(
            parse("4"), overwritten_bars=[10, 13]
        ).footer.endswith("Bars 11, 14 were set by hand and will be overwritten.")
        assert get_pattern_preview(parse("4"), overwritten_bars=[2]).footer.endswith(
            "Bar 3 was set by hand and will be overwritten."
        )

    def test_overwritten_bars_highlight_their_rows(self):
        # Bar 22 is the 11th bar of the second pass through the pattern.
        preview = get_pattern_preview(parse("10[4] 3"), overwritten_bars=[21])

        assert preview.highlighted_rows == {1}

    def test_incomplete_shows_error_with_position(self):
        preview = get_pattern_preview(parse("10["))

        assert preview.error == "Unclosed '['. (at character 3)"
        assert preview.rows == []

    def test_empty(self):
        assert get_pattern_preview(parse("")).error == "Enter at least one bar length."


class TestDialog:
    def test_complete_pattern_enables_ok(self, qtui):
        dialog = BeatPatternDialog()
        QTest.keyClicks(dialog.line_edit, "2[3] 4")
        assert dialog.ok_button.isEnabled()
        assert dialog.preview.rows() == [("1\u20132", "3"), ("3", "4")]
        assert dialog.text == "2[3] 4"

    def test_incomplete_pattern_disables_ok(self, qtui):
        dialog = BeatPatternDialog()
        # Typed brackets are paired, so set the text to leave one unclosed.
        dialog.line_edit.setText("2[3")
        assert not dialog.ok_button.isEnabled()
        assert dialog.preview.error.text().startswith("Unclosed '['.")
        assert dialog.preview.table.isHidden()
        assert dialog.preview.footer.isHidden()

    def test_table_comes_back_when_the_pattern_is_complete(self, qtui):
        dialog = BeatPatternDialog()
        dialog.line_edit.setText("2[3")
        dialog.line_edit.setText("2[3]")

        assert not dialog.preview.table.isHidden()
        assert dialog.preview.error.isHidden()

    def test_table_scrolls_instead_of_growing(self, qtui):
        dialog = BeatPatternDialog("50[1 2]")

        assert dialog.preview.table.rowCount() == 100
        assert dialog.preview.table.maximumHeight() == MAX_TABLE_HEIGHT

    def test_empty_dialog_disables_ok(self, qtui):
        dialog = BeatPatternDialog()
        assert not dialog.ok_button.isEnabled()

    def test_characters_outside_the_syntax_are_blocked(self, qtui):
        dialog = BeatPatternDialog()
        QTest.keyClicks(dialog.line_edit, "4a,4")
        assert dialog.text == "44"

    def test_initial_text(self, qtui):
        dialog = BeatPatternDialog("3 4", beat_count=7)
        assert dialog.text == "3 4"
        assert dialog.ok_button.isEnabled()
        assert dialog.preview.footer.text().endswith("7 beats tapped.")

    def test_overwritten_bars_follow_the_text(self, qtui):
        dialog = BeatPatternDialog(
            get_overwritten_bars=lambda bars: [0] if bars[0] != 4 else []
        )
        QTest.keyClicks(dialog.line_edit, "3")
        assert "Bar 1 was set by hand" in dialog.preview.footer.text()
        assert dialog.preview.highlighted_rows() == {0}
        dialog.line_edit.setText("4")
        assert "set by hand" not in dialog.preview.footer.text()
        assert dialog.preview.highlighted_rows() == set()


class TestCreateTimeline:
    def test_typed_pattern_reaches_the_timeline(self, tluis):
        with patch_beat_pattern_dialog("2[3] 4"):
            add_beat_timeline()

        assert len(tluis) == 1
        assert tluis[0].timeline.beat_pattern == "2[3] 4"

    def test_cancel_creates_no_timeline(self, tluis):
        with patch_beat_pattern_dialog(None):
            add_beat_timeline()

        assert len(tluis) == 0


class TestBracketPairing:
    def test_opening_bracket_adds_closing_one(self, qtui):
        dialog = BeatPatternDialog()

        QTest.keyClicks(dialog.line_edit, "2[")

        assert dialog.line_edit.text() == "2[]"
        assert dialog.line_edit.cursorPosition() == 2

    def test_typing_through_the_closing_bracket(self, qtui):
        dialog = BeatPatternDialog()

        QTest.keyClicks(dialog.line_edit, "10[4] 3 2[4 3[3]]")

        assert dialog.text == "10[4] 3 2[4 3[3]]"
        assert dialog.ok_button.isEnabled()

    def test_backspace_removes_an_empty_pair(self, qtui):
        dialog = BeatPatternDialog()
        QTest.keyClicks(dialog.line_edit, "2[")

        QTest.keyClick(dialog.line_edit, Qt.Key.Key_Backspace)

        assert dialog.line_edit.text() == "2"

    def test_backspace_elsewhere_deletes_one_character(self, qtui):
        dialog = BeatPatternDialog("2[3]")
        dialog.line_edit.setCursorPosition(3)

        QTest.keyClick(dialog.line_edit, Qt.Key.Key_Backspace)

        assert dialog.line_edit.text() == "2[]"

    def test_bracket_wraps_the_selection(self, qtui):
        dialog = BeatPatternDialog("4 3")
        dialog.line_edit.selectAll()

        QTest.keyClicks(dialog.line_edit, "[")

        assert dialog.line_edit.text() == "[4 3]"
        assert dialog.line_edit.cursorPosition() == 5

    def test_closing_bracket_without_one_after_the_cursor(self, qtui):
        dialog = BeatPatternDialog("2[3")
        dialog.line_edit.end(False)

        QTest.keyClicks(dialog.line_edit, "]")

        assert dialog.line_edit.text() == "2[3]"
