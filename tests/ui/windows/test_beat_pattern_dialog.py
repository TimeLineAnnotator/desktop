from fractions import Fraction as F

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator
from PySide6.QtTest import QTest

from tests.ui.timelines.beat.interact import (
    edit_bars_dialog_cell,
    patch_beat_pattern_dialog,
)
from tilia.timelines.beat.pattern import PlannedBar, parse
from tilia.ui import commands
from tilia.ui.windows.beat_pattern import (
    BARS_COLUMN,
    MAX_TABLE_HEIGHT,
    TAPS_COLUMN,
    TIME_SIGNATURE_COLUMN,
    UNTAPPED_COLOR,
    BeatPatternDialog,
    BeatPatternValidator,
    get_numbers,
    get_overrides,
    lay_out,
    parse_bar_numbers,
)


def add_beat_timeline():
    # The pattern dialog is what these tests are about, so only the name is
    # passed.
    commands.execute("timelines.add.beat", name="")


def bars(text):
    return parse(text).planned_bars


class TestValidator:
    @pytest.mark.parametrize(
        "text, state",
        [
            ("4 4 3", QValidator.State.Acceptable),
            ("10[4] 3", QValidator.State.Acceptable),
            ("4[4/4] 3/4", QValidator.State.Acceptable),
            ("6/8(3 3)", QValidator.State.Acceptable),
            ("2+3/8", QValidator.State.Acceptable),
            ("", QValidator.State.Intermediate),
            ("10[", QValidator.State.Intermediate),
            ("4/", QValidator.State.Intermediate),
            ("4/4(1 1", QValidator.State.Intermediate),
            ("4]", QValidator.State.Intermediate),
            ("0", QValidator.State.Intermediate),
            ("4a", QValidator.State.Invalid),
            ("4,4", QValidator.State.Invalid),
            ("-4", QValidator.State.Invalid),
        ],
    )
    def test_state(self, text, state):
        assert BeatPatternValidator().validate(text, len(text))[0] == state


class TestLayOut:
    def test_without_beats(self):
        assert lay_out(bars("4/4 3/4"), 0) == (bars("4/4 3/4"), 0)

    def test_beats_fill_part_of_the_pattern(self):
        assert lay_out(bars("4/4 3/4 2/4"), 5) == (bars("4/4 3/4 2/4"), 2)

    def test_beats_go_past_the_pattern(self):
        assert lay_out(bars("4/4 3/4"), 12) == (bars("4/4 3/4 4/4 3/4"), 4)


class TestBarNumbers:
    def test_numbers_count_on_from_the_bar_before(self):
        assert get_numbers(5, {2: 1}) == [1, 2, 1, 2, 3]

    def test_overrides_are_where_the_count_breaks(self):
        assert get_overrides([0, 1, 2, 1, 2, 9]) == {0: 0, 3: 1, 5: 9}

    @pytest.mark.parametrize(
        "text, count, numbers",
        [
            ("5", 3, [5, 6, 7]),
            ("5-7", 3, [5, 6, 7]),
            ("5–7", 3, [5, 6, 7]),
            ("1-4, 1-4", 8, [1, 2, 3, 4, 1, 2, 3, 4]),
            ("1-3, 3, 4", 5, [1, 2, 3, 3, 4]),
            (" 2 ", 1, [2]),
        ],
    )
    def test_valid(self, text, count, numbers):
        assert parse_bar_numbers(text, count) == (numbers, "")

    @pytest.mark.parametrize(
        "text, count, error",
        [
            ("1-4", 3, "'1-4' numbers 4 bars, not 3 bars."),
            ("1-2, 1", 4, "'1-2, 1' numbers 3 bars, not 4 bars."),
            ("a", 2, "'a' is not a bar number or a range such as 1-4."),
            ("1-2-3", 3, "'1-2-3' is not a bar number or a range such as 1-4."),
            ("4-1", 4, "'4-1' counts down."),
            ("", 2, "'' is not a bar number or a range such as 1-4."),
        ],
    )
    def test_invalid(self, text, count, error):
        assert parse_bar_numbers(text, count) == (None, error)


class TestTable:
    def test_rows_group_alike_bars(self, qtui):
        dialog = BeatPatternDialog("4[4/4] 3/4 3[4/4(3/2 3/2 1)]")

        assert dialog.get_table_rows() == [
            ("1–4", "4/4", "1 1 1 1"),
            ("5", "3/4", "1 1 1"),
            ("6–8", "4/4", "3/2 3/2 1"),
        ]

    def test_rows_of_bars_given_only_their_beats(self, qtui):
        dialog = BeatPatternDialog("2[3] 4")

        assert dialog.get_table_rows() == [
            ("1–2", "3/4 (assumed)", "1 1 1"),
            ("3", "4/4 (assumed)", "1 1 1 1"),
        ]

    def test_rows_cover_the_tapped_beats(self, qtui):
        dialog = BeatPatternDialog("4/4", beat_count=10)

        assert dialog.get_table_rows() == [("1–3", "4/4", "1 1 1 1")]
        assert dialog.footer.text() == (
            "1 bar, then the list starts again from bar 1.\n"
            "10 beats tapped, in 3 bars."
        )

    def test_untapped_bars_are_grey_and_keep_no_number(self, qtui):
        dialog = BeatPatternDialog("4[4/4] 3/4", beat_count=8)

        assert [row.is_tapped for row in dialog.rows] == [True, False, False]
        untapped = dialog.table.item(1, BARS_COLUMN)
        assert untapped.foreground().color() == UNTAPPED_COLOR
        assert not untapped.flags() & Qt.ItemFlag.ItemIsEditable
        assert dialog.table.item(1, TAPS_COLUMN).flags() & Qt.ItemFlag.ItemIsEditable

    def test_numbers_split_rows(self, qtui):
        dialog = BeatPatternDialog("4/4", beat_count=16, numbers=[1, 2, 1, 2])

        assert [row[0] for row in dialog.get_table_rows()] == [
            "1–2",
            "1–2",
        ]

    def test_table_scrolls_instead_of_growing(self, qtui):
        dialog = BeatPatternDialog("50[1 2]")

        assert dialog.table.rowCount() == 100
        assert dialog.table.maximumHeight() == MAX_TABLE_HEIGHT

    def test_bars_that_change_are_highlighted(self, qtui):
        current = bars("4/4 3/4 4/4")
        dialog = BeatPatternDialog(
            "4/4 3/4 4/4", beat_count=11, current_bars=current, numbers=[1, 2, 3]
        )
        assert dialog.get_highlighted_rows() == set()

        dialog.line_edit.setText("4/4")

        assert dialog.get_table_rows()[0][0] == "1–3"
        assert dialog.get_highlighted_rows() == {0}


class TestEditingCells:
    def test_taps_change_the_time_signature(self, qtui):
        dialog = BeatPatternDialog("4[4/4] 3/4")

        edit_bars_dialog_cell(dialog, 1, TAPS_COLUMN, "3")

        assert dialog.get_table_rows()[1] == ("5", "3/4", "3")
        assert dialog.text == "4[4/4] 3/4(3)"

    def test_taps_that_add_up_to_another_numerator(self, qtui):
        dialog = BeatPatternDialog("4/4")

        edit_bars_dialog_cell(dialog, 0, TAPS_COLUMN, "1 1 1")

        assert dialog.text == "3/4"

    def test_fractional_taps(self, qtui):
        dialog = BeatPatternDialog("2[4/4]")

        edit_bars_dialog_cell(dialog, 0, TAPS_COLUMN, "3/2 3/2 1")

        assert dialog.text == "2[4/4(3/2 3/2 1)]"
        assert dialog.rows[0].bar.values == [F(3, 2), F(3, 2), F(1)]

    def test_time_signature(self, qtui):
        dialog = BeatPatternDialog("4[4/4] 3/4")

        edit_bars_dialog_cell(dialog, 0, TIME_SIGNATURE_COLUMN, "6/8(3 3)")

        assert dialog.text == "4[6/8(3 3)] 3/4"

    def test_editing_a_row_of_a_repeated_pattern(self, qtui):
        dialog = BeatPatternDialog("4/4", beat_count=12)

        edit_bars_dialog_cell(dialog, 0, TAPS_COLUMN, "1 1 1")

        # The three bars edited become the pattern, which the twelve beats
        # go through again for a fourth bar.
        assert dialog.text == "3[3/4]"
        assert dialog.get_table_rows() == [("1–4", "3/4", "1 1 1")]

    def test_a_tapped_bar_keeps_its_taps(self, qtui):
        dialog = BeatPatternDialog("2/4", beat_count=4)

        edit_bars_dialog_cell(dialog, 0, TIME_SIGNATURE_COLUMN, "6/8")

        assert dialog.get_table_rows() == [("1–2", "6/8", "3 3")]
        assert dialog.text == "2[6/8(3 3)]"

    def test_a_tapped_bar_takes_the_taps_given(self, qtui):
        dialog = BeatPatternDialog("2/4", beat_count=4)

        edit_bars_dialog_cell(dialog, 0, TIME_SIGNATURE_COLUMN, "6/8(1 1 1 1 1 1)")

        assert dialog.text == "2[6/8]"

    def test_a_bar_not_tapped_yet_takes_the_time_signatures_taps(self, qtui):
        dialog = BeatPatternDialog("2/4 2/4", beat_count=2)

        edit_bars_dialog_cell(dialog, 1, TIME_SIGNATURE_COLUMN, "6/8")

        assert dialog.text == "2/4 6/8"

    def test_confirming_an_assumed_time_signature(self, qtui):
        dialog = BeatPatternDialog("4", beat_count=8)

        edit_bars_dialog_cell(dialog, 0, TIME_SIGNATURE_COLUMN, "4/4")

        assert dialog.text == "2[4/4]"
        assert not dialog.rows[0].bar.assumed

    def test_invalid_cell_is_reported_and_reverted(self, qtui):
        dialog = BeatPatternDialog("4/4")

        edit_bars_dialog_cell(dialog, 0, TAPS_COLUMN, "1 0")

        assert dialog.error.text() == "Units must be greater than 0."
        assert dialog.get_table_rows() == [("1", "4/4", "1 1 1 1")]
        assert dialog.text == "4/4"

    def test_more_than_one_time_signature_is_refused(self, qtui):
        dialog = BeatPatternDialog("4/4")

        edit_bars_dialog_cell(dialog, 0, TIME_SIGNATURE_COLUMN, "4/4 3/4")

        assert dialog.error.text() == "Enter one time signature, such as 3/4."

    def test_bar_numbers_make_a_repeat(self, qtui):
        dialog = BeatPatternDialog("4/4", beat_count=40)

        edit_bars_dialog_cell(dialog, 0, BARS_COLUMN, "1-4, 1-6")

        assert [row[0] for row in dialog.get_table_rows()] == [
            "1–4",
            "1–6",
        ]
        assert dialog.get_result().numbers == [1, 2, 3, 4, 1, 2, 3, 4, 5, 6]

    def test_bars_after_count_on(self, qtui):
        dialog = BeatPatternDialog("4/4 3/4", beat_count=21)

        edit_bars_dialog_cell(dialog, 1, BARS_COLUMN, "10")

        assert dialog.get_result().numbers == [1, 10, 11, 12, 13, 14]

    def test_numbers_set_further_on_are_kept(self, qtui):
        dialog = BeatPatternDialog("4/4 3/4", beat_count=21, numbers=[1, 2, 3, 1, 2, 3])

        edit_bars_dialog_cell(dialog, 1, BARS_COLUMN, "5")

        assert dialog.get_result().numbers == [1, 5, 6, 1, 2, 3]

    def test_editing_the_pattern_keeps_the_numbers(self, qtui):
        dialog = BeatPatternDialog("4/4", beat_count=16, numbers=[1, 2, 1, 2])

        dialog.line_edit.setText("2/4")

        assert dialog.get_result().numbers == [1, 2, 1, 2, 3, 4, 5, 6]


class TestDialog:
    def test_complete_pattern_enables_ok(self, qtui):
        dialog = BeatPatternDialog()
        QTest.keyClicks(dialog.line_edit, "2[3/4] 4/4")
        assert dialog.ok_button.isEnabled()
        assert dialog.get_table_rows() == [
            ("1–2", "3/4", "1 1 1"),
            ("3", "4/4", "1 1 1 1"),
        ]
        assert dialog.text == "2[3/4] 4/4"

    def test_incomplete_pattern_disables_ok(self, qtui):
        dialog = BeatPatternDialog()
        # Typed brackets are paired, so set the text to leave one unclosed.
        dialog.line_edit.setText("2[3")
        assert not dialog.ok_button.isEnabled()
        assert dialog.error.text().startswith("Unclosed '['.")
        assert dialog.table.isHidden()
        assert dialog.footer.isHidden()

    def test_error_names_the_character(self, qtui):
        dialog = BeatPatternDialog("4/4(1 1 1)")

        assert dialog.error.text() == "The taps add up to 3, not 4. (at character 4)"

    def test_table_comes_back_when_the_pattern_is_complete(self, qtui):
        dialog = BeatPatternDialog()
        dialog.line_edit.setText("2[3")
        dialog.line_edit.setText("2[3]")

        assert not dialog.table.isHidden()
        assert dialog.error.isHidden()

    def test_empty_dialog_disables_ok(self, qtui):
        dialog = BeatPatternDialog()
        assert not dialog.ok_button.isEnabled()
        assert dialog.error.text() == "Enter at least one bar."

    def test_characters_outside_the_syntax_are_blocked(self, qtui):
        dialog = BeatPatternDialog()
        QTest.keyClicks(dialog.line_edit, "4a,4")
        assert dialog.text == "44"

    def test_initial_text(self, qtui):
        dialog = BeatPatternDialog("3 4", beat_count=7)
        assert dialog.text == "3 4"
        assert dialog.ok_button.isEnabled()
        assert dialog.footer.text().endswith("7 beats tapped, in 2 bars.")

    def test_result(self, qtui):
        dialog = BeatPatternDialog("4/4", beat_count=8, numbers=[0, 1])

        result = dialog.get_result()

        assert result.pattern == "4/4"
        assert result.numbers == [0, 1]


class TestCreateTimeline:
    def test_typed_pattern_reaches_the_timeline(self, tluis):
        with patch_beat_pattern_dialog("2[3/4] 4/4"):
            add_beat_timeline()

        assert len(tluis) == 1
        assert tluis[0].timeline.beat_pattern == "2[3/4] 4/4"

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


def test_planned_bars_compare_by_value():
    assert PlannedBar.from_values([F(1)] * 4, 4) == bars("4/4")[0]
