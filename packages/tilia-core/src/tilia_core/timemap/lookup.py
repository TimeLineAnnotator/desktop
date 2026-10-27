"""Bars back to times: the times of a bar and a fraction of it, one per time
through the bar, as TiLiA's import by measure asks for them.

A port of TiLiA's `BeatTimeline.get_time_by_measure`, which looks among every
pass's beats at once, with one time for each row the bar names instead
(TimeLineAnnotator/project-management#315):

- the fraction counts the row's own beats, and between two beats the time is
  interpolated; a fraction that, at 3 decimals, is a beat's (0.333 of three
  beats) is that beat, as TiLiA rounds;
- the fraction 1 is the next downbeat when the next bar is numbered one more,
  and no time otherwise; as a segment's end, it is the row's end;
- past the last beat, the last row lasts as long as the row before it
  (TiLiA's projection), not until FR-011's closing barline;
- as a segment's end, the fraction 0 also gives where each time through the
  bar numbered just below ends (#321);
- a cadenza belongs to the bar before it
  (TimeLineAnnotator/project-management#339): that bar leads into the row
  after the cadenza, or after the last of a run of them, and ends where the
  cadenza does. So the fraction 1 looks at the bar after the cadenza, and an
  end that leads into a cadenza counts as an end at bar N only when the
  cadenza leads into a bar N;
- a bar no row names gives no time.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

from tilia_core.timemap.table import MeasureRow, find_rows

logger = logging.getLogger(__name__)

DECIMALS = 3  # TiLiA rounds a bar number plus its fraction to this many


def times_of(
    rows: Sequence[MeasureRow],
    times: Sequence[float],
    first: Sequence[int],
    number: int | None = None,
    fraction: float = 0.0,
    *,
    label: str | None = None,
    pass_: int | None = None,
    movement: int | None = None,
    segment_end: bool = False,
) -> list[float]:
    """The times of `fraction` through the rows a bar names, in time order.

    `rows` are a time map's rows in the timeline's order, `times` its beats,
    and `first[j]` the index in `times` of row j's downbeat. The rows are
    named as `find_rows` names them. A fraction outside 0 to 1 gives no time,
    with a warning.
    """
    if not 0.0 <= fraction <= 1.0:  # NaN too
        logger.warning(
            "A fraction of a bar runs from 0 to 1, not %r; no time.", fraction
        )
        return []
    named = find_rows(rows, number, label=label, pass_=pass_, movement=movement)
    found = [
        time
        for row in named
        if (time := _time_in(rows, times, first, row, fraction, segment_end))
        is not None
    ]
    if segment_end:
        found += _ends_before(rows, named, fraction, pass_=pass_, movement=movement)
    return _distinct(found)


def _time_in(
    rows: Sequence[MeasureRow],
    times: Sequence[float],
    first: Sequence[int],
    row: MeasureRow,
    fraction: float,
    segment_end: bool,
) -> float | None:
    j = row.count - 1  # a time map keeps every row of its table
    beat = _beat_at(row, fraction)
    if beat == row.beats:  # the fraction 1
        k = _leads_into(rows, j)
        if segment_end:
            return _end(rows, k - 1)
        following = rows[k] if k < len(rows) else None
        if following is not None and following.number == row.number + 1:
            return following.start
        return None
    if beat is not None:
        return times[first[j] + beat]
    position = fraction * row.beats
    k = int(position)  # below row.beats: a fraction this close to 1 is at 1
    start = times[first[j] + k]
    end = times[first[j] + k + 1] if k + 1 < row.beats else _end(rows, j)
    if end is None:
        return None
    return start + (position - k) * (end - start)


def _beat_at(row: MeasureRow, fraction: float) -> int | None:
    """The beat (0-based) that `fraction` is at, rounded as TiLiA rounds;
    `row.beats` for the fraction 1, None between beats."""
    target = round(row.number + fraction, DECIMALS)
    if target == row.number + 1:
        return row.beats
    for k in range(row.beats):
        if target == round(row.number + k / row.beats, DECIMALS):
            return k
    return None


def _end(rows: Sequence[MeasureRow], j: int) -> float | None:
    """Where row j ends: the next downbeat, or past the last beat, as long
    after its downbeat as the row before it lasted. None for a table of one
    row, which has nothing to measure it by."""
    if j + 1 < len(rows):
        return rows[j].end
    if j == 0:
        return None
    row = rows[j]
    return row.start + (row.start - rows[j - 1].start)


def _leads_into(rows: Sequence[MeasureRow], j: int) -> int:
    """The index of the row that row j leads into, `len(rows)` when none
    follows: the next row, past the cadenzas after it, which belong to it
    (#339). A cadenza named by its label leads into the next row, and one
    that starts a movement belongs to that movement, not to the row before."""
    k = j + 1
    if not rows[j].cadenza:
        while k < len(rows) and rows[k].cadenza and not rows[k].restart:
            k += 1
    return k


def _ends_before(
    rows: Sequence[MeasureRow],
    named: Sequence[MeasureRow],
    fraction: float,
    *,
    pass_: int | None,
    movement: int | None,
) -> list[float]:
    """As a segment's end, the fraction 0 of bar N: where each time through
    the bar numbered just below N ends, in the pass and movement asked for.

    An end that leads into a bar N the query doesn't name is left out, so a
    label or a pass gives only the ends that lead into the bars it names;
    without them, every bar N is named. A bar that cadenzas follow ends after
    them, and counts only when they lead into a bar N (#339).
    """
    named_counts = {row.count for row in named}
    ends: list[float] = []
    for number in sorted({row.number for row in named if _beat_at(row, fraction) == 0}):
        below = [
            row.number
            for row in rows
            if row.number < number
            and not row.cadenza
            and (movement is None or row.movement == movement)
        ]
        if not below:
            continue
        bars = {row.count for row in find_rows(rows, number)}
        for before in find_rows(rows, max(below), pass_=pass_, movement=movement):
            j = before.count - 1
            k = _leads_into(rows, j)
            into = rows[k].count if k < len(rows) else None
            if into in bars and into not in named_counts:
                continue  # a bar N the query doesn't name
            if k > j + 1 and into not in bars:
                continue  # its cadenzas lead elsewhere, or end the piece
            end = _end(rows, k - 1)
            if end is not None:
                ends.append(end)
    return ends


def _distinct(times: list[float]) -> list[float]:
    """In time order, without times as close as TiLiA's lookup counts the same."""
    out: list[float] = []
    for time in sorted(times):
        if not out or not math.isclose(time, out[-1]):
            out.append(time)
    return out
