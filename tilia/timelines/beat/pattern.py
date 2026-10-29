"""
Parsing for the beat pattern syntax.

A pattern is a whitespace-separated list of items. An item is a bar or a
repeated group of items::

    items     := item (whitespace item)*
    item      := bar | INT? "[" items "]"
    bar       := INT | numerator "/" INT taps?
    numerator := part ("+" part)*
    part      := INT ("/" INT)?
    taps      := "(" value (whitespace value)* ")"
    value     := INT ("/" INT)?

A bar is a time signature, such as ``4/4``, ``6/8`` or ``2+3/8``, or just a
number of beats, such as ``4``, whose time signature TiLiA assumes (four
quarter notes). A time signature is tapped once per unit of its denominator
(``6/8`` is six taps of an eighth note), or once per part of an added
numerator (``2+3/8`` is two taps, of a quarter and of a dotted quarter).
``taps`` says what each tap is worth instead, in units of the denominator:
``6/8(3 3)`` is 6/8 tapped in two, ``4/4(3/2 3/2 1)`` is 4/4 tapped as
3+3+2 eighths. The taps must add up to the numerator. A numerator can hold a
fraction, written before the denominator, for bars like ``11/2/4(3/2 3/2 1
3/2)``.

So ``4/4 4/4 3/4`` is three bars, ``10[4/4] 3/4 15[4/4]`` is ten bars of 4/4,
one of 3/4 and fifteen of 4/4, and ``2[4/4 3[3/4]]`` expands to ``4/4 3/4 3/4
3/4 4/4 3/4 3/4 3/4``. A group with no count (``[4/4 3/4]``) is played once.
Spaces are allowed around ``/`` and ``+``, and before ``(``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from fractions import Fraction

from tilia.timelines.beat.units import (
    MAX_DENOMINATOR,
    fit_units,
    format_units,
    parse_units,
)

# Guards against inputs like "999999[999999[4]]" expanding into a list that
# would exhaust memory. Far above the bar count of any real piece.
MAX_BARS = 100_000
# Far above the beats tapped in any real bar. Each tap's value is kept, so a
# bar's beats are capped like its bars.
MAX_BEATS_PER_BAR = 1_000
# Groups are parsed recursively, so nesting is capped well below Python's
# recursion limit. Far deeper than any pattern worth writing.
MAX_DEPTH = 32
# Significant digits in a number. Any more and the number is far above
# MAX_BARS, and int() refuses strings past a few thousand digits.
MAX_DIGITS = 9
# The time signature TiLiA assumes for a bar given only its number of beats:
# that many quarter notes.
ASSUMED_DENOMINATOR = 4
# Only ASCII digits: str.isdigit() also accepts characters such as "²" that
# int() rejects.
_DIGITS = frozenset("0123456789")


class ParseStatus(Enum):
    COMPLETE = auto()
    # A valid start that more typing could complete, e.g. "10[" or "".
    INCOMPLETE = auto()
    INVALID = auto()


@dataclass(frozen=True)
class PlannedBar:
    """
    A bar of a beat pattern: how many beats are tapped in it, and the beat
    unit that gives each its value (see `tilia.timelines.beat.units`).
    `units` repeats over the taps, and is as short as that allows.
    `assumed` is True for a bar given only its number of beats.
    """

    beat_count: int
    denominator: int
    units: tuple[Fraction, ...]
    assumed: bool = False

    @classmethod
    def from_values(
        cls, values: list[Fraction], denominator: int, assumed: bool = False
    ) -> PlannedBar:
        return cls(len(values), denominator, _shortest_period(values), assumed)

    @property
    def values(self) -> list[Fraction]:
        """What each tap is worth, in units of the denominator."""
        return fit_units(list(self.units), self.beat_count)

    @property
    def numerator(self) -> Fraction:
        if len(self.units) == 1:
            return self.units[0] * self.beat_count
        return sum(self.values, Fraction(0))

    @property
    def units_text(self) -> str:
        """The units as a beat unit stores them, e.g. "3/2+3/2+1"."""
        return format_units(self.units)


@dataclass(frozen=True)
class ParseResult:
    status: ParseStatus
    planned_bars: list[PlannedBar] = field(default_factory=list)
    error: str = ""
    position: int | None = None

    @property
    def is_complete(self) -> bool:
        return self.status == ParseStatus.COMPLETE

    @property
    def bars(self) -> list[int]:
        """The number of beats in each bar."""
        return [bar.beat_count for bar in self.planned_bars]


@dataclass(frozen=True)
class BarRun:
    """Consecutive bars with the same length. `start` is a 0-based bar index."""

    start: int
    count: int
    beats: int


def _shortest_period(values: list[Fraction]) -> tuple[Fraction, ...]:
    """The shortest start of `values` that repeats into all of them."""
    for length in range(1, len(values) + 1):
        if len(values) % length == 0 and values == values[:length] * (
            len(values) // length
        ):
            return tuple(values[:length])
    return tuple(values)


class _Incomplete(Exception):
    def __init__(self, message: str, position: int) -> None:
        super().__init__(message)
        self.message = message
        self.position = position


class _Invalid(Exception):
    def __init__(self, message: str, position: int) -> None:
        super().__init__(message)
        self.message = message
        self.position = position


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.depth = 0

    def at_end(self) -> bool:
        return self.pos >= len(self.text)

    def peek(self) -> str:
        return self.text[self.pos]

    def at(self, character: str) -> bool:
        return not self.at_end() and self.peek() == character

    def at_digit(self) -> bool:
        return not self.at_end() and self.peek() in _DIGITS

    def skip_whitespace(self) -> None:
        while not self.at_end() and self.peek().isspace():
            self.pos += 1

    def parse_int(self) -> int:
        start = self.pos
        while self.at_digit():
            self.pos += 1
        digits = self.text[start : self.pos].lstrip("0")
        if len(digits) > MAX_DIGITS:
            raise _Invalid(f"Numbers can have at most {MAX_DIGITS} digits.", start)
        return int(digits or "0")

    def expect_int(self, missing: str) -> int:
        """Parses a number after skipping whitespace, which must be there."""
        self.skip_whitespace()
        if self.at_end():
            raise _Incomplete(missing, self.pos)
        if not self.at_digit():
            raise _Invalid(f"Unexpected '{self.peek()}'.", self.pos)
        return self.parse_int()

    def parse_items(self, open_position: int | None = None) -> list[PlannedBar]:
        """
        Parses items up to the end of the text, or up to the "]" closing the
        group opened at `open_position`. Leaves that "]" unconsumed.
        """
        in_group = open_position is not None
        bars: list[PlannedBar] = []
        while True:
            self.skip_whitespace()
            if self.at_end():
                if in_group:
                    raise _Incomplete("Unclosed '['.", open_position)
                break
            if self.peek() == "]":
                if in_group:
                    break
                raise _Invalid("Unmatched ']'.", self.pos)
            item_start = self.pos
            bars.extend(self.parse_item())
            if len(bars) > MAX_BARS:
                raise _Invalid(
                    f"Pattern expands to more than {MAX_BARS} bars.", item_start
                )

        if not bars:
            if in_group:
                raise _Invalid("Empty group '[]'.", open_position)
            raise _Incomplete("Enter at least one bar.", 0)

        return bars

    def parse_item(self) -> list[PlannedBar]:
        start = self.pos
        count = self.parse_int() if self.at_digit() else None
        self.skip_whitespace()

        if self.at("["):
            return self.parse_group(start, count)

        if count is None:
            raise _Invalid(f"Unexpected '{self.peek()}'.", self.pos)
        if self.at("/") or self.at("+"):
            return [self.parse_time_signature(start, count)]
        if count < 1:
            raise _Invalid("Bars must have at least 1 beat.", start)
        if count > MAX_BEATS_PER_BAR:
            raise _Invalid(f"Bars can have at most {MAX_BEATS_PER_BAR} beats.", start)
        return [PlannedBar(count, ASSUMED_DENOMINATOR, (Fraction(1),), assumed=True)]

    def parse_group(self, start: int, count: int | None) -> list[PlannedBar]:
        open_position = self.pos
        if self.depth >= MAX_DEPTH:
            raise _Invalid(
                f"Groups can be nested at most {MAX_DEPTH} deep.", open_position
            )
        self.pos += 1
        self.depth += 1
        group = self.parse_items(open_position)
        self.depth -= 1
        self.pos += 1  # the closing "]"
        repeats = 1 if count is None else count
        if repeats < 1:
            raise _Invalid("Repeat count must be at least 1.", start)
        if len(group) * repeats > MAX_BARS:
            raise _Invalid(f"Pattern expands to more than {MAX_BARS} bars.", start)
        return group * repeats

    def parse_time_signature(self, start: int, first: int) -> PlannedBar:
        """
        Parses a time signature whose numerator starts with `first`, already
        read, up to its denominator and taps.
        """
        parts = [Fraction(first)]
        while True:
            if self.at("+"):
                self.pos += 1
                parts.append(Fraction(self.expect_int("Enter a number after '+'.")))
                self.skip_whitespace()
                continue
            if self.at_end():
                raise _Incomplete("Enter '/' and a denominator.", self.pos)
            if not self.at("/"):
                raise _Invalid(f"Unexpected '{self.peek()}'.", self.pos)
            self.pos += 1
            number = self.expect_int("Enter a denominator after '/'.")
            # A second "/" makes the number a part's denominator: the last
            # number after a "/" is the time signature's.
            after_number = self.pos
            self.skip_whitespace()
            if self.at("/"):
                if number == 0:
                    raise _Invalid("Division by 0.", after_number)
                parts[-1] /= number
                continue
            self.pos = after_number
            denominator = number
            break

        if any(part <= 0 for part in parts):
            raise _Invalid("Numerators must be greater than 0.", start)
        if not 1 <= denominator <= MAX_DENOMINATOR:
            raise _Invalid(f"Denominators go from 1 to {MAX_DENOMINATOR}.", start)

        taps_start = self.pos
        self.skip_whitespace()
        if self.at("("):
            values = self.parse_taps()
            numerator = sum(parts, Fraction(0))
            if sum(values, Fraction(0)) != numerator:
                raise _Invalid(
                    f"The taps add up to {format_units([sum(values)])}, not "
                    f"{format_units([numerator])}.",
                    taps_start,
                )
        else:
            self.pos = taps_start
            if len(parts) > 1:
                values = parts
            elif parts[0].denominator != 1:
                raise _Invalid("Give the taps of a fractional numerator.", start)
            elif parts[0] > MAX_BEATS_PER_BAR:
                # Checked before the taps are listed, as they may be many.
                raise _Invalid(
                    f"Bars can have at most {MAX_BEATS_PER_BAR} beats.", start
                )
            else:
                values = [Fraction(1)] * int(parts[0])

        if len(values) > MAX_BEATS_PER_BAR:
            raise _Invalid(f"Bars can have at most {MAX_BEATS_PER_BAR} beats.", start)
        return PlannedBar.from_values(values, denominator)

    def parse_taps(self) -> list[Fraction]:
        open_position = self.pos
        self.pos += 1
        close = self.text.find(")", self.pos)
        if close == -1:
            if "(" in self.text[self.pos :] or "[" in self.text[self.pos :]:
                raise _Invalid("Unclosed '('.", open_position)
            raise _Incomplete("Unclosed '('.", open_position)
        inside = self.text[self.pos : close]
        if not inside.strip():
            raise _Invalid("Empty taps '()'.", open_position)
        result = parse_units("+".join(inside.replace("+", " ").split()))
        if not result.is_valid:
            raise _Invalid(result.error, self.pos)
        self.pos = close + 1
        return result.units


def parse(text: str) -> ParseResult:
    """Parses a beat pattern into the bars it expands to."""
    try:
        bars = _Parser(text).parse_items()
    except _Incomplete as e:
        return ParseResult(ParseStatus.INCOMPLETE, error=e.message, position=e.position)
    except _Invalid as e:
        return ParseResult(ParseStatus.INVALID, error=e.message, position=e.position)

    return ParseResult(ParseStatus.COMPLETE, bars)


def parse_time_signature(text: str) -> tuple[PlannedBar | None, str]:
    """Reads one bar of the pattern syntax, such as "6/8" or "6/8(3 3)"."""
    result = parse(text)
    if not result.is_complete:
        return None, result.error
    if len(result.planned_bars) != 1:
        return None, "Enter one time signature, such as 3/4."
    return result.planned_bars[0], ""


def parse_time_signature_over_taps(
    text: str, beat_count: int
) -> tuple[PlannedBar | None, str]:
    """
    Reads the time signature of a bar that already has `beat_count` taps.
    The bar keeps its taps unless the text gives others, in brackets: each
    tap is then worth the same, the numerator divided by the taps, or, for
    an added numerator with as many parts as taps, a part each. 6/8 over two
    taps is 3 and 3; 3/4 over four is 3/4 each.
    """
    bar, error = parse_time_signature(text)
    if bar is None:
        return None, error
    if bar.assumed or bar.beat_count == beat_count or "(" in text:
        return bar, ""

    value = bar.numerator / beat_count
    if value.denominator > MAX_DENOMINATOR:
        return None, (
            f"{format_units([bar.numerator])}/{bar.denominator} can't be shared "
            f"between {beat_count} taps."
        )
    return PlannedBar.from_values([value] * beat_count, bar.denominator), ""


def parse_time_signature_of_tapped_bar(
    text: str, beat_count: int
) -> tuple[PlannedBar | None, str]:
    """
    Reads the time signature of a bar that has `beat_count` taps, as
    `parse_time_signature_over_taps` does, refusing taps in brackets that
    aren't as many.
    """
    bar, error = parse_time_signature_over_taps(text, beat_count)
    if bar is not None and bar.beat_count != beat_count:
        return None, f"It gives {bar.beat_count} taps, but the bar has {beat_count}."
    return bar, error


def group_runs(bars: list[int]) -> list[BarRun]:
    """Groups consecutive bars of equal length, e.g. for previewing a pattern."""
    runs: list[BarRun] = []
    for index, beats in enumerate(bars):
        if runs and runs[-1].beats == beats:
            last = runs[-1]
            runs[-1] = BarRun(last.start, last.count + 1, beats)
        else:
            runs.append(BarRun(index, 1, beats))
    return runs


def format_bars(bars: list[int]) -> str:
    """
    Writes bar lengths as a pattern, collapsing runs of equal bars:
    ``[4, 4, 4, 3]`` becomes ``3[4] 3``. Nested groups are not recovered.
    """
    return " ".join(
        f"{run.count}[{run.beats}]" if run.count > 1 else str(run.beats)
        for run in group_runs(bars)
    )


def format_planned_bar(bar: PlannedBar) -> str:
    """
    Writes a bar as the pattern syntax would: its number of beats if it is
    assumed, else its time signature, with its taps where they aren't the
    time signature's own.
    """
    if bar.assumed:
        return str(bar.beat_count)
    values = bar.values
    if all(value == 1 for value in values):
        return f"{len(values)}/{bar.denominator}"
    if len(set(values)) > 1 and all(value.denominator == 1 for value in values):
        return f"{format_units(values)}/{bar.denominator}"
    taps = " ".join(str(value) for value in values)
    return f"{format_units([bar.numerator])}/{bar.denominator}({taps})"


def format_time_signature(bar: PlannedBar) -> str:
    """A bar's time signature alone, such as "6/8" or "11/2/4"."""
    return f"{format_units([bar.numerator])}/{bar.denominator}"


def format_taps(bar: PlannedBar) -> str:
    """What each tap of a bar is worth, such as "3/2 3/2 1"."""
    return " ".join(str(value) for value in bar.values)


def format_planned_bars(bars: list[PlannedBar]) -> str:
    """
    Writes bars as a pattern, collapsing runs of equal bars: three bars of
    4/4 and one of 3/4 become ``3[4/4] 3/4``. Nested groups are not
    recovered.
    """
    items = []
    index = 0
    while index < len(bars):
        end = index
        while end + 1 < len(bars) and bars[end + 1] == bars[index]:
            end += 1
        text = format_planned_bar(bars[index])
        count = end - index + 1
        items.append(f"{count}[{text}]" if count > 1 else text)
        index = end + 1
    return " ".join(items)
