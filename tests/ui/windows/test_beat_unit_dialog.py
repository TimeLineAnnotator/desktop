import pytest
from PySide6.QtGui import QValidator
from PySide6.QtTest import QTest

from tilia.ui.windows.beat_unit import (
    BeatUnitDialog,
    BeatUnitInput,
    UnitsValidator,
    get_units_preview,
)


class TestValidator:
    @pytest.mark.parametrize(
        "text, state",
        [
            ("1", QValidator.State.Acceptable),
            ("2+3", QValidator.State.Acceptable),
            ("1/3", QValidator.State.Acceptable),
            ("", QValidator.State.Intermediate),
            ("2+", QValidator.State.Intermediate),
            ("1/", QValidator.State.Intermediate),
            ("0", QValidator.State.Intermediate),
            ("1.5", QValidator.State.Invalid),
            ("-1", QValidator.State.Invalid),
            ("a", QValidator.State.Invalid),
        ],
    )
    def test_state(self, text, state):
        assert UnitsValidator().validate(text, len(text))[0] == state


class TestUnitsPreview:
    def test_one_unit(self):
        preview = get_units_preview(8, "3", None)

        assert preview.headers == ["Tap", "Units (1/8)", "Length"]
        assert preview.rows == [("1", "3", "1 1/2 quarters")]
        assert preview.footer == "Every tap is worth the same."

    def test_several_units_repeat(self):
        preview = get_units_preview(4, "2+3", 2)

        assert preview.rows == [("1", "2", "2 quarters"), ("2", "3", "3 quarters")]
        assert preview.footer == (
            "Repeats every 2 taps, from tap 1 in each measure.\n"
            "This measure (2 taps) becomes 5/4."
        )

    def test_fractional_units(self):
        preview = get_units_preview(4, "1/3", None)

        assert preview.rows == [("1", "1/3", "1/3 quarter")]

    def test_whole_and_fraction(self):
        assert get_units_preview(4, "1/3", 13).footer.endswith(
            "This measure (13 taps) becomes 4 1/3 over 4."
        )

    def test_ambiguous(self):
        assert get_units_preview(4, "2+3", 3).footer.endswith(
            "3 taps under 2+3: treated as 2+3+2."
        )

    def test_error(self):
        preview = get_units_preview(4, "2+", 3)

        assert preview.error == "Missing unit around '+'."
        assert preview.rows == []


class TestDialog:
    def test_initial_values(self, qtui):
        dialog = BeatUnitDialog(8, "3", beat_count=2)

        assert dialog.denominator_edit.value() == 8
        assert dialog.units_edit.text() == "3"
        assert dialog.ok_button.isEnabled()
        assert dialog.preview.footer.text().endswith("becomes 6/8.")

    def test_preview_follows_input(self, qtui):
        dialog = BeatUnitDialog(4, "1", beat_count=2)

        dialog.units_edit.clear()
        QTest.keyClicks(dialog.units_edit, "2+3")

        assert dialog.preview.footer.text().endswith("becomes 5/4.")

    def test_incomplete_units_disable_ok(self, qtui):
        dialog = BeatUnitDialog(4, "1")

        QTest.keyClicks(dialog.units_edit, "+")

        assert not dialog.ok_button.isEnabled()

    def test_characters_outside_the_syntax_are_blocked(self, qtui):
        dialog = BeatUnitDialog(4, "")

        QTest.keyClicks(dialog.units_edit, "1.5a")

        assert dialog.units_edit.text() == "15"

    def test_scope_defaults_to_onward(self, qtui):
        dialog = BeatUnitDialog(4, " 2 + 3 ")

        assert dialog.result_input == BeatUnitInput(4, "2+3", False)

        dialog.measure_option.click()
        assert dialog.result_input.only_this_measure

    def test_scope_can_be_hidden(self, qtui):
        dialog = BeatUnitDialog(4, "1", show_scope=False)

        assert dialog.onward_option.isHidden()
        assert dialog.measure_option.isHidden()
