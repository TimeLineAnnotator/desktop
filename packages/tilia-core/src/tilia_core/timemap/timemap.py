"""The time map: where a time lies in bars and beats, from a beat timeline's measure table.

The map runs from the first beat to the closing barline, which it excludes.
Every lookup is a bisection over arrays built once: the beat slots (the beats,
then the closing barline), each beat's measure, each measure's first beat, and
the downbeats.
"""

from __future__ import annotations

import bisect
import itertools
import math
from dataclasses import dataclass, field

from tilia_core import tla
from tilia_core.timemap._rows import rows_of
from tilia_core.timemap.table import MeasureRow, build_rows_from

TOLERANCE = 0.1  # in the file's unit: a time this close to a beat is on it
EPS = 1e-6  # added to the tolerance, so float noise never decides whether a time is on a beat

FOLDED = (
    "the table lists the measures played next (`next`), "
    "which positions don't handle yet"
)


@dataclass(frozen=True)
class Positions:
    """Where a unit lies on a time map: its start's measure, and where it ends."""

    bar: int
    end_bar: int | None  # the end point excluded; a point's bar; None past the map
    beat: float  # 1-based and fractional
    pass_: int | None  # None in a cadenza
    bar_count: int
    bar_label: str
    bar_beat_count: int
    downbeat: bool
    cadenza: bool
    movement: int


@dataclass(frozen=True)
class TimeMap:
    """A beat timeline seen as a map from times to positions.

    Built by `build_time_map`. It doesn't follow later changes to the document:
    a caller builds it again after one.
    """

    timeline_id: str
    guessed: bool  # taken as the first beat timeline, as none had the role time_map
    start: float  # the first beat
    end: float  # the closing barline, excluded
    tolerance: float
    _rows: tuple[MeasureRow, ...] = field(repr=False)
    _slots: tuple[float, ...] = field(repr=False)  # the beats, then the closing barline
    _measure_of: tuple[int, ...] = field(repr=False)  # each beat's measure
    _first: tuple[int, ...] = field(repr=False)  # each measure's first beat
    _downbeats: tuple[float, ...] = field(repr=False)

    def measure_rows(self) -> list[MeasureRow]:
        """The measure table, in the timeline's order."""
        return list(self._rows)

    def measures(self) -> list[tuple[float, float, int, str]]:
        """Each measure's (start, end, number, label), in the timeline's order."""
        return [(row.start, row.end, row.number, row.label) for row in self._rows]

    def positions(self, start: float, end: float) -> Positions | None:
        """Where a unit from `start` to `end` lies; a point has `end == start`.

        An end that, once both are snapped, isn't after the start ends in the
        start's bar, as a point's does. None when the start is off the map.
        """
        snapped_start = self._snapped(start)
        located = self._locate(snapped_start)
        if located is None:
            return None
        slot, fraction = located
        measure = self._measure_of[slot]
        row = self._rows[measure]
        snapped_end = self._snapped(end)
        if snapped_end is not None and snapped_end <= snapped_start:
            end_bar: int | None = row.number
        else:
            end_bar = self._end_bar(snapped_end)
        return Positions(
            bar=row.number,
            end_bar=end_bar,
            beat=slot - self._first[measure] + 1 + fraction,
            pass_=row.pass_,
            bar_count=row.count,
            bar_label=row.label,
            bar_beat_count=row.beats,
            downbeat=self._is_downbeat(start),
            cadenza=row.cadenza,
            movement=row.movement,
        )

    def _snapped(self, t: float | None) -> float | None:
        """`t` moved onto the nearer beat slot, or the closing barline, when it
        lies within the tolerance of one. None for a missing time."""
        if t is None or not math.isfinite(t):
            return None
        slots = self._slots
        tolerance = self.tolerance + EPS
        k = bisect.bisect_left(slots, t)  # slots[k - 1] < t <= slots[k]
        best, best_distance = float(t), math.inf
        if k < len(slots) and slots[k] - t <= tolerance:
            best, best_distance = slots[k], slots[k] - t
        if k and t - slots[k - 1] <= tolerance and t - slots[k - 1] < best_distance:
            best = slots[k - 1]
        return best

    def _locate(self, snapped: float | None) -> tuple[int, float] | None:
        """(beat slot, fraction through it) of a snapped time; None off the map."""
        slots = self._slots
        if snapped is None or snapped < slots[0] or snapped >= slots[-1]:
            return None
        i = bisect.bisect_right(slots, snapped) - 1
        return i, (snapped - slots[i]) / (slots[i + 1] - slots[i])

    def _end_bar(self, snapped_end: float | None) -> int | None:
        # Only for an end after the start, so after the first downbeat. The end
        # point is excluded: an end on a downbeat belongs to the bar before.
        if snapped_end is None or snapped_end > self.end:
            return None
        return self._rows[bisect.bisect_left(self._downbeats, snapped_end) - 1].number

    def _is_downbeat(self, t: float) -> bool:
        downbeats = self._downbeats
        k = bisect.bisect_left(downbeats, t)
        nearest = min(
            abs(downbeats[x] - t) for x in (k - 1, k) if 0 <= x < len(downbeats)
        )
        return nearest <= self.tolerance + EPS


def build_time_map(
    document: tla.Document, timeline: tla.Timeline, *, guessed: bool = False
) -> tuple[TimeMap | None, str | None]:
    """The beat timeline's time map, or None with the reason it has none."""
    table = timeline.measures
    if table is None or (not table.rows and timeline.components):
        return None, "no measure table"
    rows_in = rows_of(timeline)
    if len(rows_in) < len(table.rows):
        return None, "a downbeat without a time"
    times = [t for row in rows_in for t in row.beat_times]
    if len(times) < 2:
        return None, "fewer than two beats"
    for a, b in itertools.pairwise(times):
        if abs(b - a) < EPS:
            return None, f"two beats at the same time ({a})"
        if b < a:
            return None, f"beats out of time order (at {b})"
    rows = build_rows_from(document, timeline, rows_in)
    if rows[0].folded:
        return None, FOLDED
    slots = (*times, rows[-1].end)
    time_map = TimeMap(
        timeline_id=timeline.id,
        guessed=guessed,
        start=slots[0],
        end=slots[-1],
        tolerance=TOLERANCE,
        _rows=tuple(rows),
        _slots=slots,
        _measure_of=tuple(j for j, row in enumerate(rows) for _ in range(row.beats)),
        _first=tuple(itertools.accumulate((row.beats for row in rows[:-1]), initial=0)),
        _downbeats=tuple(row.start for row in rows),
    )
    return time_map, None
