"""
Beat units: what one tapped beat is worth in notation.

A beat unit is a denominator plus a units pattern, the number of
denominator units each tapped beat in a measure is worth. Units are written
as a "+"-separated list of whole numbers or fractions: "1", "3", "2+3",
"1/2", "1/3". The time signature of a measure is calculated from its beat
unit and number of tapped beats, and is never stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

DEFAULT_DENOMINATOR = 4
DEFAULT_UNITS = "1"
# Far above any denominator used in notation. Enforced wherever a beat unit
# is set, so the dialog and inspector, which can't show more, never meet one.
MAX_DENOMINATOR = 128

_UNIT_CHARACTERS = set("0123456789/")


def validate_denominator(value: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 1 <= value <= MAX_DENOMINATOR
    )


@dataclass(frozen=True)
class UnitsParseResult:
    units: list[Fraction]
    error: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.error


def parse_units(text: str) -> UnitsParseResult:
    """Parses units text such as "2+3" or "1/3" into fractions."""
    if not text.strip():
        return UnitsParseResult([], "Enter at least one unit.")

    units = []
    for item in text.split("+"):
        item = item.strip()
        if not item:
            return UnitsParseResult([], "Missing unit around '+'.")
        not_a_fraction = UnitsParseResult(
            [], f"'{item}' is not a whole number or fraction such as 1/2."
        )
        # Fraction() also accepts decimals, signs and exponents; units are
        # written the way they are in notation.
        if not set(item) <= _UNIT_CHARACTERS:
            return not_a_fraction
        try:
            unit = Fraction(item)
        except (ValueError, ZeroDivisionError):
            return not_a_fraction
        if unit <= 0:
            return UnitsParseResult([], "Units must be greater than 0.")
        units.append(unit)

    return UnitsParseResult(units)


def format_units(units: list[Fraction]) -> str:
    """Writes units in canonical form, e.g. [2, 3] as "2+3"."""
    return "+".join(str(unit) for unit in units)


def fit_units(units: list[Fraction], beat_count: int) -> list[Fraction]:
    """
    The value of each of `beat_count` tapped beats in a measure. The pattern
    is read from its start in every measure, pickups included: a shorter
    measure takes its first entries and a longer one repeats it. A pickup
    that holds the end of the pattern needs a beat unit of its own.
    """
    return [units[i % len(units)] for i in range(beat_count)]


def is_fit_ambiguous(units: list[Fraction], beat_count: int) -> bool:
    """
    Whether the measure doesn't hold a whole number of patterns: the pattern
    is not uniform and the beat count is not a multiple of its length. One
    tap under 2+3 is read as 2, but could be a pickup worth 3.
    """
    return len(set(units)) > 1 and beat_count % len(units) != 0


@dataclass(frozen=True)
class MeasureMeter:
    """
    The meter a measure ends up with. `beat_unit_id` is the beat unit that
    governs the measure, or None where the default applies. `is_assumed` is
    True when its values weren't set by the user (see BeatUnit.assumed).
    """

    denominator: int
    units: list[Fraction]
    beat_values: list[Fraction]
    beat_unit_id: int | None
    starts_here: bool
    is_ambiguous: bool
    is_conflicting: bool
    is_assumed: bool

    @property
    def numerator(self) -> Fraction:
        return sum(self.beat_values, Fraction(0))

    @property
    def time_signature(self) -> tuple[Fraction, int]:
        return self.numerator, self.denominator

    def quarter_length(self, beat_value: Fraction) -> Fraction:
        return beat_value * 4 / self.denominator
