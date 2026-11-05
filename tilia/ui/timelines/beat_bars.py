"""
The rows of a beat timeline's bars table: runs of consecutive bars that are
alike, each with its bar numbers, time signature and taps. Free of Qt, so
the CLI lists the bars as the bars dialog shows them.
"""

from __future__ import annotations

from dataclasses import dataclass

import tilia.ui.strings
from tilia.timelines.beat.pattern import (
    PlannedBar,
    format_taps,
    format_time_signature,
)


@dataclass(frozen=True)
class BarRow:
    """Consecutive bars that are alike. `start` is a 0-based bar index."""

    start: int
    bar: PlannedBar
    numbers: tuple[int, ...]
    is_tapped: bool

    @property
    def count(self) -> int:
        return len(self.numbers)


def get_rows(
    bars: list[PlannedBar],
    tapped: int,
    numbers: list[int],
    breaks: frozenset[int] = frozenset(),
) -> list[BarRow]:
    """
    Groups consecutive bars that are alike and numbered one after another.
    A bar whose index is in `breaks` starts a row of its own.
    """
    rows: list[BarRow] = []
    for index, (bar, number) in enumerate(zip(bars, numbers, strict=True)):
        is_tapped = index < tapped
        if rows and index not in breaks:
            last = rows[-1]
            if (
                last.bar == bar
                and last.is_tapped == is_tapped
                and last.numbers[-1] + 1 == number
            ):
                rows[-1] = BarRow(last.start, bar, last.numbers + (number,), is_tapped)
                continue
        rows.append(BarRow(index, bar, (number,), is_tapped))
    return rows


def format_bar_numbers(numbers: tuple[int, ...] | list[int]) -> str:
    """Writes consecutive bar numbers as a range: "1–4", or "5" alone."""
    if len(numbers) == 1:
        return str(numbers[0])
    return f"{numbers[0]}–{numbers[-1]}"


def format_time_signature_cell(bar: PlannedBar) -> str:
    text = format_time_signature(bar)
    if bar.assumed:
        return tilia.ui.strings.BEAT_PATTERN_ASSUMED_TIME_SIGNATURE.format(text)
    return text


def format_row(row: BarRow) -> tuple[str, str, str]:
    """A row's bars, time signature and taps, as the table shows them."""
    return (
        format_bar_numbers(row.numbers),
        format_time_signature_cell(row.bar),
        format_taps(row.bar),
    )
