"""
Parsing for the beat pattern syntax.

A pattern is a whitespace-separated list of items. An item is either a bar
length or a repeated group of items::

    items := item (whitespace item)*
    item  := INT | INT? "[" items "]"

So ``4 4 3`` is three bars, ``10[4] 3 15[4]`` is ten bars of 4, one of 3 and
fifteen of 4, and ``2[4 3[3]]`` expands to ``4 3 3 3 4 3 3 3``. A group with no
count (``[4 3]``) is played once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

# Guards against inputs like "999999[999999[4]]" expanding into a list that
# would exhaust memory. Far above the bar count of any real piece.
MAX_BARS = 100_000
# Groups are parsed recursively, so nesting is capped well below Python's
# recursion limit. Far deeper than any pattern worth writing.
MAX_DEPTH = 32
# Significant digits in a number. Any more and the number is far above
# MAX_BARS, and int() refuses strings past a few thousand digits.
MAX_DIGITS = 9
# Only ASCII digits: str.isdigit() also accepts characters such as "²" that
# int() rejects.
_DIGITS = frozenset("0123456789")


class ParseStatus(Enum):
    COMPLETE = auto()
    # A valid start that more typing could complete, e.g. "10[" or "".
    INCOMPLETE = auto()
    INVALID = auto()


@dataclass(frozen=True)
class ParseResult:
    status: ParseStatus
    bars: list[int] = field(default_factory=list)
    error: str = ""
    position: int | None = None

    @property
    def is_complete(self) -> bool:
        return self.status == ParseStatus.COMPLETE


@dataclass(frozen=True)
class BarRun:
    """Consecutive bars with the same length. `start` is a 0-based bar index."""

    start: int
    count: int
    beats: int


class _Incomplete(Exception):
    def __init__(self, message: str, position: int):
        super().__init__(message)
        self.message = message
        self.position = position


class _Invalid(Exception):
    def __init__(self, message: str, position: int):
        super().__init__(message)
        self.message = message
        self.position = position


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.depth = 0

    def at_end(self) -> bool:
        return self.pos >= len(self.text)

    def peek(self) -> str:
        return self.text[self.pos]

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

    def parse_items(self, open_position: int | None = None) -> list[int]:
        """
        Parses items up to the end of the text, or up to the "]" closing the
        group opened at `open_position`. Leaves that "]" unconsumed.
        """
        in_group = open_position is not None
        bars: list[int] = []
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
            raise _Incomplete("Enter at least one bar length.", 0)

        return bars

    def parse_item(self) -> list[int]:
        start = self.pos
        count = self.parse_int() if self.at_digit() else None
        self.skip_whitespace()

        if not self.at_end() and self.peek() == "[":
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

        if count is None:
            raise _Invalid(f"Unexpected '{self.peek()}'.", self.pos)
        if count < 1:
            raise _Invalid("Bar lengths must be at least 1.", start)
        return [count]


def parse(text: str) -> ParseResult:
    """Parses a beat pattern into the list of bar lengths it expands to."""
    try:
        bars = _Parser(text).parse_items()
    except _Incomplete as e:
        return ParseResult(ParseStatus.INCOMPLETE, error=e.message, position=e.position)
    except _Invalid as e:
        return ParseResult(ParseStatus.INVALID, error=e.message, position=e.position)

    return ParseResult(ParseStatus.COMPLETE, bars)


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
