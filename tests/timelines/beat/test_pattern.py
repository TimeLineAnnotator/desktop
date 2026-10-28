from fractions import Fraction as F

import pytest

from tilia.timelines.beat.pattern import (
    MAX_BARS,
    MAX_BEATS_PER_BAR,
    MAX_DEPTH,
    MAX_DIGITS,
    BarRun,
    ParseStatus,
    PlannedBar,
    format_planned_bars,
    group_runs,
    parse,
    parse_time_signature_over_taps,
)


class TestComplete:
    @pytest.mark.parametrize(
        "text, bars",
        [
            ("4", [4]),
            ("4 4 3", [4, 4, 3]),
            ("  4\t4\n3  ", [4, 4, 3]),
            ("10[4] 3 15[4]", [4] * 10 + [3] + [4] * 15),
            ("2[4 3[3]]", [4, 3, 3, 3, 4, 3, 3, 3]),
            ("2[[4] 3[3]]", [4, 3, 3, 3, 4, 3, 3, 3]),
            ("[4 3]", [4, 3]),
            ("1[4]", [4]),
            ("3 [2]", [2, 2, 2]),
            ("2[3]4", [3, 3, 4]),
            ("12", [12]),
            ("007", [7]),
        ],
    )
    def test_expands(self, text, bars):
        result = parse(text)
        assert result.status == ParseStatus.COMPLETE
        assert result.is_complete
        assert result.bars == bars
        assert result.error == ""

    def test_max_bars_is_allowed(self):
        assert parse(f"{MAX_BARS}[1]").bars == [1] * MAX_BARS


class TestIncomplete:
    @pytest.mark.parametrize(
        "text, position",
        [
            ("", 0),
            ("   ", 0),
            ("10[", 2),
            ("2[4 3", 1),
            ("2[4 3[3]", 1),
            ("2[4 3[3", 5),
        ],
    )
    def test_incomplete(self, text, position):
        result = parse(text)
        assert result.status == ParseStatus.INCOMPLETE
        assert not result.is_complete
        assert result.bars == []
        assert result.error
        assert result.position == position


class TestInvalid:
    @pytest.mark.parametrize(
        "text, position, message",
        [
            ("4 ]", 2, "Unmatched ']'."),
            ("2[4]]", 4, "Unmatched ']'."),
            ("4 a", 2, "Unexpected 'a'."),
            ("4, 4", 1, "Unexpected ','."),
            ("-4", 0, "Unexpected '-'."),
            ("0", 0, "Bars must have at least 1 beat."),
            ("4 0", 2, "Bars must have at least 1 beat."),
            ("0[4]", 0, "Repeat count must be at least 1."),
            ("2[]", 1, "Empty group '[]'."),
            ("2[ ]", 1, "Empty group '[]'."),
        ],
    )
    def test_invalid(self, text, position, message):
        result = parse(text)
        assert result.status == ParseStatus.INVALID
        assert result.bars == []
        assert result.error == message
        assert result.position == position

    @pytest.mark.parametrize(
        "text",
        [f"{MAX_BARS + 1}[1]", "999999999[999999999[4]]", f"{MAX_BARS}[1] 1"],
    )
    def test_too_many_bars(self, text):
        result = parse(text)
        assert result.status == ParseStatus.INVALID
        assert "more than" in result.error

    @pytest.mark.parametrize("text", ["²", "4 ²", "①[4]", "٣"])
    def test_non_ascii_digits(self, text):
        result = parse(text)
        assert result.status == ParseStatus.INVALID
        assert result.error.startswith("Unexpected")

    @pytest.mark.parametrize("text", ["9" * 5000, f"{'9' * 10}[4]"])
    def test_too_many_digits(self, text):
        result = parse(text)
        assert result.status == ParseStatus.INVALID
        assert result.error == f"Numbers can have at most {MAX_DIGITS} digits."
        assert result.position == 0

    def test_leading_zeros_do_not_count_as_digits(self):
        assert parse("0" * 20 + "4").bars == [4]

    def test_max_depth_is_allowed(self):
        text = "[" * MAX_DEPTH + "4" + "]" * MAX_DEPTH
        assert parse(text).bars == [4]

    @pytest.mark.parametrize("closed", [True, False])
    def test_too_deep(self, closed):
        depth = MAX_DEPTH + 1
        text = "[" * depth + "4" + ("]" * depth if closed else "")
        result = parse(text)
        assert result.status == ParseStatus.INVALID
        assert result.error == f"Groups can be nested at most {MAX_DEPTH} deep."
        assert result.position == MAX_DEPTH

    def test_very_deep_nesting_does_not_recurse(self):
        result = parse("[" * 5000 + "4" + "]" * 5000)
        assert result.status == ParseStatus.INVALID


class TestGroupRuns:
    def test_empty(self):
        assert group_runs([]) == []

    def test_groups_consecutive_equal_bars(self):
        assert group_runs([4] * 10 + [3] + [4] * 15) == [
            BarRun(0, 10, 4),
            BarRun(10, 1, 3),
            BarRun(11, 15, 4),
        ]

    def test_does_not_merge_non_consecutive_bars(self):
        assert group_runs([4, 3, 4]) == [
            BarRun(0, 1, 4),
            BarRun(1, 1, 3),
            BarRun(2, 1, 4),
        ]


def bar_values(text):
    return [
        (bar.beat_count, bar.denominator, bar.units, bar.assumed)
        for bar in parse(text).planned_bars
    ]


class TestTimeSignatures:
    @pytest.mark.parametrize(
        "text, bars",
        [
            # A number of beats alone assumes quarter notes.
            ("3", [(3, 4, (F(1),), True)]),
            ("4/4", [(4, 4, (F(1),), False)]),
            ("6/8", [(6, 8, (F(1),), False)]),
            ("2/2", [(2, 2, (F(1),), False)]),
            # An added numerator is tapped once per part.
            ("2+3/8", [(2, 8, (F(2), F(3)), False)]),
            ("3+3+2/8", [(3, 8, (F(3), F(3), F(2)), False)]),
            # Taps say what each beat is worth.
            ("6/8(3 3)", [(2, 8, (F(3),), False)]),
            ("3/4(3)", [(1, 4, (F(3),), False)]),
            ("4/4(3/2 3/2 1)", [(3, 4, (F(3, 2), F(3, 2), F(1)), False)]),
            ("4/4(1 2 1)", [(3, 4, (F(1), F(2), F(1)), False)]),
            ("4/4(2 2)", [(2, 4, (F(2),), False)]),
            ("4/4(1+1+1+1)", [(4, 4, (F(1),), False)]),
            ("8/8(1 2 1 2 2)", [(5, 8, (F(1), F(2), F(1), F(2), F(2)), False)]),
            # A fractional numerator, with its taps.
            (
                "11/2/4(3/2 3/2 1 3/2)",
                [(4, 4, (F(3, 2), F(3, 2), F(1), F(3, 2)), False)],
            ),
            # Spaces around the operators.
            ("4 / 4", [(4, 4, (F(1),), False)]),
            ("2 + 3 / 8 (2 3)", [(2, 8, (F(2), F(3)), False)]),
        ],
    )
    def test_bars(self, text, bars):
        result = parse(text)
        assert result.is_complete, result.error
        assert bar_values(text) == bars

    def test_groups_of_time_signatures(self):
        assert parse("4[4/4] 3/4 3[4/4]").bars == [4, 4, 4, 4, 3, 4, 4, 4]
        assert [bar.numerator for bar in parse("2[4/4 3/4]").planned_bars] == [
            4,
            3,
            4,
            3,
        ]

    def test_values_and_numerator(self):
        (bar,) = parse("4/4(3/2 3/2 1)").planned_bars
        assert bar.values == [F(3, 2), F(3, 2), F(1)]
        assert bar.numerator == 4
        assert bar.units_text == "3/2+3/2+1"

    @pytest.mark.parametrize(
        "text, position",
        [
            ("4/", 2),
            ("4/ ", 3),
            ("2+", 2),
            ("2+3", 3),
            ("4/4(", 3),
            ("4/4(1 1", 3),
            ("2[4/", 4),
        ],
    )
    def test_incomplete(self, text, position):
        result = parse(text)
        assert result.status == ParseStatus.INCOMPLETE
        assert result.position == position

    @pytest.mark.parametrize(
        "text, message",
        [
            ("4/4(1 1 1)", "The taps add up to 3, not 4."),
            ("6/8(3 2)", "The taps add up to 5, not 6."),
            ("4/0", "Denominators go from 1 to 128."),
            ("4/129", "Denominators go from 1 to 128."),
            ("0/4", "Numerators must be greater than 0."),
            ("3/2/4", "Give the taps of a fractional numerator."),
            ("4/4()", "Empty taps '()'."),
            ("4/4(1 0 3)", "Units must be greater than 0."),
            ("4/4(a)", "'a' is not a whole number or fraction such as 1/2."),
            ("4/a", "Unexpected 'a'."),
            (
                f"{MAX_BEATS_PER_BAR + 1}/4",
                f"Bars can have at most {MAX_BEATS_PER_BAR} beats.",
            ),
            (
                f"{MAX_BEATS_PER_BAR + 1}",
                f"Bars can have at most {MAX_BEATS_PER_BAR} beats.",
            ),
        ],
    )
    def test_invalid(self, text, message):
        result = parse(text)
        assert result.status == ParseStatus.INVALID
        assert result.error == message

    @pytest.mark.parametrize(
        "text",
        [
            "4",
            "4 4 3",
            "4/4",
            "4[4/4] 3/4 3[4/4]",
            "6/8(3 3)",
            "3/4(3)",
            "2+3/8",
            "4/4(3/2 3/2 1)",
            "11/2/4(3/2 3/2 1 3/2)",
            "2[4/4 3[3/4]]",
            "12/8(3 3 3 3) 4 2/2",
        ],
    )
    def test_formatting_reads_back_as_the_same_bars(self, text):
        bars = parse(text).planned_bars
        assert parse(format_planned_bars(bars)).planned_bars == bars

    @pytest.mark.parametrize(
        "text, formatted",
        [
            ("4 4 4 3", "3[4] 3"),
            ("4/4 4/4 3/4", "2[4/4] 3/4"),
            ("8/8(1 1 1 1 1 1 1 1)", "8/8"),
            ("6/8(3 3)", "6/8(3 3)"),
            ("8/8(3 3 2)", "3+3+2/8"),
        ],
    )
    def test_formatting(self, text, formatted):
        assert format_planned_bars(parse(text).planned_bars) == formatted

    def test_planned_bar_from_values_finds_the_repeating_units(self):
        bar = PlannedBar.from_values([F(1), F(2)] * 3, 8)
        assert bar.units == (F(1), F(2))
        assert bar.beat_count == 6


class TestTimeSignatureOverTaps:
    @pytest.mark.parametrize(
        "text, beat_count, values, denominator",
        [
            # As many taps as the time signature's own.
            ("4/4", 4, [F(1)] * 4, 4),
            # Each tap gets an equal share of the numerator.
            ("6/8", 2, [F(3), F(3)], 8),
            ("3/4", 4, [F(3, 4)] * 4, 4),
            ("2/2", 4, [F(1, 2)] * 4, 2),
            # An added numerator with a part per tap.
            ("2+3/8", 2, [F(2), F(3)], 8),
            ("2+3/8", 5, [F(1)] * 5, 8),
            # Taps given in brackets are kept, however many.
            ("6/8(3 3)", 6, [F(3), F(3)], 8),
        ],
    )
    def test_values(self, text, beat_count, values, denominator):
        bar, error = parse_time_signature_over_taps(text, beat_count)
        assert error == ""
        assert (bar.values, bar.denominator) == (values, denominator)

    def test_a_share_too_fine_is_refused(self):
        bar, error = parse_time_signature_over_taps("1/4", 129)
        assert bar is None
        assert error == "1/4 can't be shared between 129 taps."

    def test_more_than_one_bar_is_refused(self):
        assert parse_time_signature_over_taps("4/4 3/4", 4) == (
            None,
            "Enter one time signature, such as 3/4.",
        )


class TestReviewedEdgeCases:
    def test_a_number_after_an_added_numerator_is_unexpected(self):
        result = parse("3+2 4/8")
        assert result.status == ParseStatus.INVALID
        assert result.error == "Unexpected '4'."

    def test_an_added_numerator_waits_for_its_denominator(self):
        result = parse("3+2")
        assert result.status == ParseStatus.INCOMPLETE
        assert result.error == "Enter '/' and a denominator."

    @pytest.mark.timeout(1)
    def test_a_huge_numerator_is_refused_before_its_taps_are_listed(self):
        result = parse("999999999/4")
        assert result.error == f"Bars can have at most {MAX_BEATS_PER_BAR} beats."
