"""Quarter stamps: each beat's position in quarter notes, and the conversion
between times and quarter stamps.

Moved from desktop#621's BeatTimeline (`beat_quarter_lengths`,
`_build_quarter_stamps`, `_build_time_stamp_table`,
`get_quarter_stamp_by_time` and `get_time_by_quarter_stamp`), with the same
rules, over a beat timeline's beat times and its measures' meters instead of
the app's components. Stamps are exact inside, and floats where they meet times.
`beats_between`, which says which beats' lengths a span's quarter notes count,
is the core's own.
"""

from __future__ import annotations

import itertools
from bisect import bisect, bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from tilia_core.timemap.units import MeasureMeter


@dataclass(frozen=True)
class TimeStampTable:
    """
    Per beat: its time, its quarter stamp and how many seconds a quarter note
    lasts from it to the next beat, for converting between the two. Seconds
    are the file's unit, which is quarter notes in a quarters file.
    """

    times: tuple[float, ...]
    stamps: tuple[float, ...]
    seconds_per_quarter: tuple[float, ...]


def beat_lengths(meter: MeasureMeter) -> list[Fraction]:
    """How long each beat of a measure is, in quarter notes."""
    return [meter.quarter_length(value) for value in meter.beat_values]


def quarter_stamps(lengths: Sequence[Fraction]) -> list[Fraction]:
    """
    Each beat's position in quarter notes, from 0 at the first beat (pickup
    included): the sum of the lengths of the beats before it, as Verovio's and
    the Measure Map's "qstamp".
    """
    stamps = [Fraction(0)] + list(itertools.accumulate(lengths[:-1]))
    return stamps[: len(lengths)]


def build_time_stamp_table(
    times: Sequence[float], lengths: Sequence[Fraction]
) -> TimeStampTable | None:
    """The table for beats at `times`, `lengths` quarter notes long; None with
    fewer than two beats."""
    if len(times) < 2:
        return None
    seconds_per_quarter = [
        (times[index + 1] - times[index]) / float(lengths[index])
        for index in range(len(times) - 1)
    ]
    # The last beat has no next beat to measure against, so the tempo of
    # the gap before it carries on past it. Its own length doesn't enter:
    # that gap lasted the previous beat's length, not the last one's.
    # (beats_between follows this rule too.)
    seconds_per_quarter.append(seconds_per_quarter[-1])
    return TimeStampTable(
        times=tuple(times),
        stamps=tuple(float(stamp) for stamp in quarter_stamps(lengths)),
        seconds_per_quarter=tuple(seconds_per_quarter),
    )


def quarter_stamp_by_time(table: TimeStampTable | None, time: float) -> float | None:
    """
    The quarter stamp at `time`, interpolated between beats and
    extrapolated beyond them. None with fewer than two beats.
    """
    if table is None:
        return None
    index = max(0, min(bisect(table.times, time) - 1, len(table.times) - 1))
    return (
        table.stamps[index]
        + (time - table.times[index]) / table.seconds_per_quarter[index]
    )


def beats_between(times: Sequence[float], start: float, end: float) -> range:
    """
    The beats whose lengths the quarter notes between `start` and `end` count,
    in either order, by index: each beat whose gap the span covers. Before the
    first beat the first gap's tempo applies, and after the last beat the last
    gap's, as `quarter_stamp_by_time` extrapolates. An end exactly on a beat
    takes nothing from it, and a point takes its own gap. Empty with fewer than
    two beats.
    """
    if len(times) < 2:
        return range(0)
    start, end = sorted((start, end))
    last = len(times) - 2  # the last beat's own length never enters
    first = min(max(bisect(times, start) - 1, 0), last)
    stop = min(max(bisect_left(times, end) - 1, first), last)
    return range(first, stop + 1)


def time_by_quarter_stamp(table: TimeStampTable | None, stamp: float) -> float | None:
    """
    The time of quarter stamp `stamp`, interpolated between beats and
    extrapolated beyond them. None with fewer than two beats.
    """
    if table is None:
        return None
    index = max(0, min(bisect(table.stamps, stamp) - 1, len(table.stamps) - 1))
    return (
        table.times[index]
        + (stamp - table.stamps[index]) * table.seconds_per_quarter[index]
    )
