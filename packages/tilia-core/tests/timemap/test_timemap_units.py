import sys
from fractions import Fraction as F

import pytest

from tilia_core.timemap.units import (
    MAX_DENOMINATOR,
    MAX_UNIT_LENGTH,
    MeasureMeter,
    fit_units,
    format_units,
    is_fit_ambiguous,
    parse_units,
    validate_denominator,
)


class TestParseUnits:
    @pytest.mark.parametrize(
        "text, units",
        [
            ("1", [F(1)]),
            ("3", [F(3)]),
            ("2+3", [F(2), F(3)]),
            (" 2 + 2 + 3 ", [F(2), F(2), F(3)]),
            ("1/2", [F(1, 2)]),
            ("1/3+2/3", [F(1, 3), F(2, 3)]),
            ("2/4", [F(1, 2)]),
        ],
    )
    def test_valid(self, text, units):
        result = parse_units(text)
        assert result.is_valid
        assert result.units == units

    @pytest.mark.parametrize(
        "text", ["", " ", "2+", "+2", "2++3", "0", "1/0", "1.5", "-1", "a", "1e2"]
    )
    def test_invalid(self, text):
        result = parse_units(text)
        assert not result.is_valid
        assert result.error
        assert result.units == []

    def test_longest_unit_is_read(self):
        assert parse_units("1" * MAX_UNIT_LENGTH).is_valid

    def test_longer_unit_is_refused_and_cut_short_in_the_message(self):
        result = parse_units("1" * (MAX_UNIT_LENGTH + 1))

        assert not result.is_valid
        assert result.units == []
        assert result.error == (
            f"'{'1' * MAX_UNIT_LENGTH}…' is longer than {MAX_UNIT_LENGTH} characters."
        )

    @pytest.mark.skipif(
        not hasattr(sys, "set_int_max_str_digits"),
        reason="this Python has no limit on the digits int() reads",
    )
    @pytest.mark.parametrize("digit_limit", [0, 4300])
    def test_very_long_unit_is_refused_whatever_the_digit_limit(self, digit_limit):
        # Python 3.10.7 and later refuse to read an integer of more than 4300
        # digits by default; earlier versions read any length, as 0 does.
        before = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(digit_limit)
        try:
            result = parse_units("1" * 5000)
        finally:
            sys.set_int_max_str_digits(before)

        assert not result.is_valid
        assert result.units == []
        assert result.error == (
            f"'{'1' * MAX_UNIT_LENGTH}…' is longer than {MAX_UNIT_LENGTH} characters."
        )

    def test_format(self):
        assert format_units([F(2), F(3)]) == "2+3"
        assert format_units([F(1, 3)]) == "1/3"
        assert format_units(parse_units(" 2/4 + 1 ").units) == "1/2+1"


class TestFitUnits:
    @pytest.mark.parametrize(
        "units, beat_count, values",
        [
            ([F(1)], 4, [F(1)] * 4),
            ([F(2), F(3)], 2, [F(2), F(3)]),
            ([F(2), F(3)], 4, [F(2), F(3), F(2), F(3)]),
            ([F(2), F(3)], 3, [F(2), F(3), F(2)]),
            ([F(3), F(2)], 1, [F(3)]),
            ([F(2), F(2), F(3)], 2, [F(2), F(2)]),
            ([F(1), F(2), F(3)], 2, [F(1), F(2)]),
            ([F(1)], 0, []),
        ],
    )
    def test_fit(self, units, beat_count, values):
        assert fit_units(units, beat_count) == values

    @pytest.mark.parametrize(
        "units, beat_count, ambiguous",
        [
            ([F(1)], 3, False),
            ([F(3)], 1, False),
            ([F(1, 2)], 3, False),
            ([F(2), F(3)], 2, False),
            ([F(2), F(3)], 4, False),
            ([F(2), F(3)], 1, True),
            ([F(2), F(3)], 3, True),
            ([F(2), F(2)], 3, False),
        ],
    )
    def test_ambiguous(self, units, beat_count, ambiguous):
        assert is_fit_ambiguous(units, beat_count) == ambiguous


def make_meter(**fields):
    values = dict(
        denominator=4,
        units=(F(1),),
        beat_values=(F(1), F(1)),
        beat_unit_id=None,
        starts_here=True,
        is_ambiguous=False,
        is_conflicting=False,
        is_assumed=True,
    )
    return MeasureMeter(**(values | fields))


class TestMeasureMeter:
    def test_built_from_lists_it_holds_tuples(self):
        from_lists = make_meter(units=[F(1)], beat_values=[F(1), F(1)])

        assert from_lists.units == (F(1),)
        assert from_lists.beat_values == (F(1), F(1))
        assert hash(from_lists) == hash(make_meter())
        assert from_lists == make_meter()

    def test_quarter_length_reads_no_text(self):
        with pytest.raises(TypeError):
            make_meter().quarter_length("1/2")


@pytest.mark.parametrize(
    "value, valid",
    [
        (1, True),
        (8, True),
        (MAX_DENOMINATOR, True),
        (0, False),
        (MAX_DENOMINATOR + 1, False),
        (True, False),
        (4.0, False),
    ],
)
def test_validate_denominator(value, valid):
    assert validate_denominator(value) == valid
