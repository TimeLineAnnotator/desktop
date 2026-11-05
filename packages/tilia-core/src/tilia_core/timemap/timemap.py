"""The time map: where a time lies in bars and beats, from a beat timeline's measure table.

The map runs from the first beat to the closing barline, which it excludes.
Every lookup is a bisection over arrays built once: the beat slots (the beats,
then the closing barline, with a closing barline too after each movement a
closing tap ends), each slot's measure, each measure's first slot and the
downbeats, with the map; each slot's quarter stamp, the first time one is asked
for. A time after a movement's closing tap, and before the next movement's first
downbeat, is in a pause: no measure holds it, and it has no quarter stamp, unless
it snaps onto that tap or that downbeat, as a position does.
"""

from __future__ import annotations

import bisect
import itertools
import logging
import math
from dataclasses import dataclass, field
from fractions import Fraction

from tilia_core import tla
from tilia_core.timemap import lookup
from tilia_core.timemap._rows import rows_of
from tilia_core.timemap.qstamps import (
    TimeStampTable,
    beat_lengths,
    beats_between,
    build_time_stamp_table,
    quarter_stamp_by_time,
    time_by_quarter_stamp,
)
from tilia_core.timemap.table import (
    EPS,
    MeasureRow,
    _media_length,
    build_rows_from,
    find_rows,
    is_folded,
    missing_time,
    table_problem,
)

logger = logging.getLogger(__name__)

TOLERANCE = 0.1  # in the file's unit: a time this close to a beat is on it

FOLDED = (
    "the table lists the measures played next (`next`), "
    "which positions don't handle yet"
)

UNITS = ("bar", "beat")  # what distances and lengths are measured in


@dataclass(frozen=True)
class Positions:
    """Where a unit lies on a time map: its start's measure, and where it ends."""

    bar: int
    end_bar: int | None  # the end point excluded; a point's bar; None off the map
    beat: float  # 1-based and fractional
    pass_: int | None  # None in a cadenza
    bar_count: int
    bar_label: str
    bar_beat_count: int
    downbeat: bool
    cadenza: bool
    movement: int


@dataclass(frozen=True, eq=False)
class TimeMap:
    """A beat timeline seen as a map from times to positions.

    Built by `build_time_map`. It doesn't follow later changes to the document:
    a caller builds it again after one.
    """

    timeline_id: str
    guessed: bool  # taken as the first beat timeline, as none had the role time_map
    _rows: tuple[MeasureRow, ...] = field(repr=False)
    _times: tuple[float, ...] = field(repr=False)  # the beats
    _media_length: float | None = field(repr=False)  # what stops a time past them
    # Computed from the rows and the beats, so nothing can make them disagree:
    # the beat slots (the beats, then the closing barline, with one after each
    # measure a closing tap closes), each slot's measure (a closing barline's
    # is the measure it ends), each measure's first slot, how many beats come
    # before it, and the downbeats. Each slot's quarter stamp is computed from
    # them too, when first asked for (`_stamps`).
    _slots: tuple[float, ...] = field(init=False, repr=False)
    _measure_of: tuple[int, ...] = field(init=False, repr=False)
    _first: tuple[int, ...] = field(init=False, repr=False)
    _beats_before: tuple[int, ...] = field(init=False, repr=False)
    _downbeats: tuple[float, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        rows = self._rows
        if sum(row.beats for row in rows) != len(self._times):
            raise ValueError("the rows' beats and the beat times don't match")
        slots: list[float] = []
        measure_of: list[int] = []
        first: list[int] = []
        beats = iter(self._times)
        for j, row in enumerate(rows):
            first.append(len(slots))
            slots.extend(itertools.islice(beats, row.beats))
            if row.closed or j == len(rows) - 1:
                slots.append(row.end)
            measure_of.extend(itertools.repeat(j, len(slots) - first[j]))
        computed = {
            "_slots": tuple(slots),
            "_measure_of": tuple(measure_of),
            "_first": tuple(first),
            "_beats_before": tuple(
                itertools.accumulate((row.beats for row in rows[:-1]), initial=0)
            ),
            "_downbeats": tuple(row.start for row in rows),
        }
        for name, value in computed.items():
            object.__setattr__(self, name, value)

    @property
    def _stamps(self) -> TimeStampTable | None:
        """Each tap's quarter stamp, built the first time one is asked for:
        the index, which reads every file's positions, never asks, and a long
        piece's exact stamps take a while.

        Kept in the instance's __dict__, without a lock, so that maps don't
        wait for each other (functools.cached_property holds one lock for every
        instance on Python 3.10 and 3.11). Two threads asking a new map at once
        may both build its table; the tables are the same, and either is kept.
        """
        try:
            return self.__dict__["_stamp_table"]
        except KeyError:
            pass
        lengths: list[Fraction] = []
        for row in self._rows:
            lengths += beat_lengths(row.meter)
            if row.closed:
                lengths.append(Fraction(0))
        table = build_time_stamp_table(self._taps, lengths)
        object.__setattr__(self, "_stamp_table", table)
        return table

    @property
    def _taps(self) -> tuple[float, ...]:
        """The beats and the closing taps: the slots, but for a closing barline
        worked out from the beats, which no quarter stamp is measured against."""
        return self._slots if self._rows[-1].closed else self._slots[:-1]

    @property
    def start(self) -> float:
        """The first beat."""
        return self._slots[0]

    @property
    def end(self) -> float:
        """The closing barline, which the map excludes."""
        return self._slots[-1]

    @property
    def tolerance(self) -> float:
        """How close to a beat a time is on it, in the file's unit."""
        return TOLERANCE

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
            # on a downbeat once moved onto its nearest beat: always beat 1
            downbeat=fraction == 0 and slot == self._first[measure],
            cadenza=row.cadenza,
            movement=row.movement,
        )

    # Distances and lengths in bars and beats: the prototype's position,
    # length, beat_seconds and bar_seconds.

    def position(self, t: float, unit: str) -> float | None:
        """Where `t` lies along the map in bars or beats (`unit` "bar" or
        "beat"), from 0 at the first beat, in the timeline's order.

        A bar counts 1 whatever its metre, and inside a bar the fraction counts
        beats. A closing barline is the end of its movement's last bar, and a
        pause counts for nothing. None elsewhere off the map, and in a pause.
        """
        if not _is_unit(unit):
            return None
        return self._position(self._snapped(t), unit, closing=True)

    def length(self, start: float, end: float, unit: str) -> float | None:
        """How long a span lasts in bars or beats (`unit` "bar" or "beat"): the
        distance between its two positions, rounded to a millionth, so that 8
        bars compares equal to 8. None when either end is off the map or in a
        pause; an end on a closing barline is on it, a start isn't."""
        if not _is_unit(unit):
            return None
        a = self._position(self._snapped(start), unit, closing=False)
        b = self._position(self._snapped(end), unit, closing=True)
        if a is None or b is None:
            return None
        return round(b - a, 6)

    def unit_seconds(self, t: float, unit: str) -> float | None:
        """How long the beat or the bar holding `t` lasts (`unit` "beat" or
        "bar"), in the file's unit despite the name. None off the map, and in a
        pause."""
        if not _is_unit(unit):
            return None
        located = self._locate(self._snapped(t))
        if located is None:
            return None
        slot = located[0]
        if unit == "beat":
            return self._slots[slot + 1] - self._slots[slot]
        row = self._rows[self._measure_of[slot]]
        return row.end - row.start

    def _position(
        self, snapped: float | None, unit: str, *, closing: bool
    ) -> float | None:
        # The prototype's measure_pos or beat_pos; with `closing`, its position.
        located = self._locate(snapped)
        if located is None:
            return self._barline_position(snapped, unit) if closing else None
        slot, fraction = located
        measure = self._measure_of[slot]
        if unit == "beat":
            return self._beats_before[measure] + slot - self._first[measure] + fraction
        beats = self._rows[measure].beats
        return measure + (slot - self._first[measure] + fraction) / beats

    def _barline_position(self, snapped: float | None, unit: str) -> float | None:
        """The end of the measure a closing barline ends, if `snapped` is on one."""
        if snapped is None or snapped < self.start or snapped > self.end:
            return None
        slot = bisect.bisect_right(self._slots, snapped) - 1
        if snapped != self._slots[slot] or not self._is_barline(slot):
            return None
        measure = self._measure_of[slot]
        if unit == "bar":
            return float(measure + 1)
        return float(self._beats_before[measure] + self._rows[measure].beats)

    def _is_barline(self, slot: int) -> bool:
        measure = self._measure_of[slot]
        return slot - self._first[measure] == self._rows[measure].beats

    def _in_pause(self, t: float) -> bool:
        """Whether `t` is after a closing barline and before the next downbeat."""
        slot = bisect.bisect_right(self._slots, t) - 1
        return (
            0 <= slot < len(self._slots) - 1
            and t > self._slots[slot]
            and self._is_barline(slot)
        )

    def _edges_a_pause(self, slot: int) -> bool:
        """Whether a slot is a movement's closing barline, or the first downbeat
        after one. The piece's last barline has no pause after it."""
        if slot < len(self._slots) - 1 and self._is_barline(slot):
            return True
        return slot > 0 and self._is_barline(slot - 1)

    def _stamp_time(self, t: float) -> float | None:
        """The time at which `t`'s quarter stamp is read: `t` itself, but around a
        pause, where it snaps as a position does, so that a section has quarter
        notes wherever it has bars. None for a time truly in the pause."""
        snapped = self._snapped(t)
        slot = bisect.bisect_right(self._slots, snapped) - 1
        if slot >= 0 and snapped == self._slots[slot] and self._edges_a_pause(slot):
            return snapped
        return None if self._in_pause(t) else t

    # Quarter notes: desktop#621's quarter stamps. Unlike positions, they aren't
    # snapped, but around a pause, and they go on beyond the beats.

    def qstamp(self, t: float) -> float | None:
        """`t`'s position in quarter notes, from 0 at the first beat:
        interpolated between beats, and extrapolated beyond them with the tempo
        of the nearest gap. At a beat, its exact stamp as a float. A closing tap
        lasts no quarter note, and the pause after a movement's holds none: the
        next downbeat has the tap's stamp, and a time that snaps onto either has
        it too. None for a missing time, or one truly in a pause."""
        if t is None or not math.isfinite(t):
            return None
        at = self._stamp_time(t)
        return None if at is None else quarter_stamp_by_time(self._stamps, at)

    def time_at_qstamp(self, q: float) -> float | None:
        """The time at the quarter stamp `q`, read as `qstamp` reads them. A
        movement's closing tap and the next movement's first downbeat have the
        same stamp, which is read as a start: it gives the downbeat."""
        if q is None or not math.isfinite(q):
            return None
        return time_by_quarter_stamp(self._stamps, q)

    def quarters(self, start: float, end: float) -> float | None:
        """How long a span lasts in quarter notes: the difference of its
        qstamps, rounded to a millionth as lengths in bars and beats are.
        `assumed_between` says whether an assumed meter went into it."""
        a, b = self.qstamp(start), self.qstamp(end)
        if a is None or b is None:
            return None
        return round(b - a, 6)

    def assumed_between(self, start: float, end: float) -> bool:
        """Whether an assumed meter went into `quarters(start, end)`, so that a
        length in quarter notes can say "assumed meter": whether a measure that
        holds a beat whose length it counts is assumed (`beats_between`). Around
        a pause, a time is read where `qstamp` reads it. False for a missing
        time, or one truly in a pause, as `quarters` gives None."""
        if any(t is None or not math.isfinite(t) for t in (start, end)):
            return False
        ends = self._stamp_time(start), self._stamp_time(end)
        if None in ends:
            return False
        low, high = sorted(ends)
        beats = beats_between(self._taps, low, high)
        if (
            beats
            and self._is_barline(beats[0])
            and low == self._slots[beats[0]]
            and (len(beats) > 1 or high <= self._taps[-1])
        ):
            # From a closing barline on, its bar gives no quarter note. But past
            # a last movement of one beat, quarter notes go by the gap before
            # the pause, which is that bar's, and no other gap is left.
            beats = beats[1:]
        if not beats:
            return False
        first, last = self._measure_of[beats[0]], self._measure_of[beats[-1]]
        return any(row.assumed for row in self._rows[first : last + 1])

    def find(
        self,
        number: int | None = None,
        *,
        label: str | None = None,
        pass_: int | None = None,
        movement: int | None = None,
    ) -> list[MeasureRow]:
        """The measures a bar names, in the timeline's order: by number (every
        pass, cadenzas left out), by label (cadenzas included), or both;
        narrowed to one pass, and to one movement, else every movement."""
        return find_rows(
            self._rows, number, label=label, pass_=pass_, movement=movement
        )

    def times_of(
        self,
        number: int | None = None,
        fraction: float = 0.0,
        *,
        label: str | None = None,
        pass_: int | None = None,
        movement: int | None = None,
        segment_end: bool = False,
    ) -> list[float]:
        """The times of `fraction` (0 to 1, counted in beats) through each
        measure the bar names, in time order: one per pass, as an import by
        measure asks for them (`lookup.times_of`). `segment_end` is for the
        end of a span."""
        return lookup.times_of(
            self._rows,
            self._slots,
            self._first,
            number,
            fraction,
            label=label,
            pass_=pass_,
            movement=movement,
            segment_end=segment_end,
            media_length=self._media_length,
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
        """(beat slot, fraction through it) of a snapped time; None off the map,
        on a closing barline and in the pause after one."""
        slots = self._slots
        if snapped is None or snapped < slots[0] or snapped >= slots[-1]:
            return None
        i = bisect.bisect_right(slots, snapped) - 1
        if self._is_barline(i):
            return None
        return i, (snapped - slots[i]) / (slots[i + 1] - slots[i])

    def _end_bar(self, snapped_end: float | None) -> int | None:
        # The end point is excluded: an end on a downbeat belongs to the bar
        # before, and an end on or before the first downbeat to none. An end on
        # a closing barline belongs to the bar it ends, and one in the pause
        # after it to none.
        if snapped_end is None or snapped_end <= self.start or snapped_end > self.end:
            return None
        k = bisect.bisect_left(self._downbeats, snapped_end)
        row = self._rows[k - 1]
        on_a_downbeat = k < len(self._downbeats) and self._downbeats[k] == snapped_end
        return row.number if on_a_downbeat or snapped_end <= row.end else None


def _is_unit(unit: str) -> bool:
    if unit in UNITS:
        return True
    # Not something a file can give: a caller's mistake, logged, not raised.
    logger.error("A time map measures in 'bar' or 'beat', not %r.", unit)
    return False


def build_time_map(
    document: tla.Document, timeline: tla.Timeline, *, guessed: bool = False
) -> tuple[TimeMap | None, str | None]:
    """The beat timeline's time map, or None with the reason it has none."""
    table = timeline.measures
    if table is None or (not table.rows and timeline.components):
        # A beat without a time is named first. WP3's table leaves it out of
        # every row, so a downbeat without one may be why there are none. No
        # table at all happens only in memory, since the reader gives every
        # beat timeline one: with a table rebuilt there, that beat would still
        # give no time map, so it is the one thing to fix either way.
        return None, missing_time(timeline) or "no measure table"
    reason = table_problem(timeline)
    if reason is not None:
        return None, reason
    rows_in = rows_of(timeline)
    times = [t for row in rows_in for t in row.beat_times]
    if len(times) < 2:
        return None, "fewer than two beats"
    if is_folded(rows_in):
        return None, FOLDED
    rows = build_rows_from(document, timeline, rows_in)
    time_map = TimeMap(
        timeline_id=timeline.id,
        guessed=guessed,
        _rows=tuple(rows),
        _times=tuple(times),
        _media_length=_media_length(document),
    )
    return time_map, None
