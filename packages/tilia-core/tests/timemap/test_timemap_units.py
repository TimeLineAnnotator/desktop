from fractions import Fraction as F

import pytest

from tilia_core.timemap.units import (
    MAX_DENOMINATOR,
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
