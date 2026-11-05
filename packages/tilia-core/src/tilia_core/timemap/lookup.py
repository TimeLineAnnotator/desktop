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
- past the last beat, a row ends where the time map ends it: a row that a
  closing tap closes, the last of the piece or of a movement, at the tap, for
  its fractions, the fraction 1 too, and as a segment's end
  (TimeLineAnnotator/project-management#332); the last row without one at
  FR-011's closing barline, whose time the fraction 1 gives only as a segment's
  end, but never before its last beat, where a time map can't put a barline:
  `max(last beat, min(last beat + its length, media's end))`, so times never
  run backwards (TimeLineAnnotator/project-management#493);
- as a segment's end, the fraction 0 also gives where each time through the
  bar numbered just below ends (#321);
- a cadenza belongs to the bar before it
  (TimeLineAnnotator/project-management#339): that bar leads into the row
  after the cadenza, or after the last of a run of them, and ends where the
  cadenza does. So the fraction 1 looks at the bar after the cadenza, and an
  end that leads into a cadenza is taken after it and counts as any other
  end does: a cadenza moves an end, and never removes one;
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
    media_length: float | None = None,
) -> list[float]:
    """The times of `fraction` through the rows a bar names, in time order.

    `rows` are a time map's rows in the timeline's order, `times` its beat
    slots, and `first[j]` the index in `times` of row j's downbeat, with row
    j's beats after it. The rows are named as `find_rows` names them. A
    fraction outside 0 to 1 gives no time, with a warning. `media_length` is
    what stops the last row, when the document has one that does.
    """
    if not 0.0 <= fraction <= 1.0:  # NaN too
        logger.warning(
            "A fraction of a bar runs from 0 to 1, not %r; no time.", fraction
        )
        return []
    named = find_rows(rows, number, label=label, pass_=pass_, movement=movement)
    last_end = _last_end(rows, times, first, media_length)
    found = [
        time
        for row in named
        if (time := _time_in(rows, times, first, row, fraction, segment_end, last_end))
        is not None
    ]
    if segment_end:
        found += _ends_before(
            rows, named, fraction, last_end, pass_=pass_, movement=movement
        )
    return _distinct(found)


def _last_end(
    rows: Sequence[MeasureRow],
    times: Sequence[float],
    first: Sequence[int],
    media_length: float | None,
) -> float:
    """Where the last row ends for a time: at its closing tap, wherever the media
    ends, or else at `max(last beat, min(last beat + its length, media's end))`.
    The row's own end is that length alone when the media ends at or before the
    last beat, since a time map can't put a barline there (FR-082)."""
    last = rows[-1]
    if last.closed or media_length is None:
        return last.end
    last_beat = times[first[-1] + last.beats - 1]
    return max(last_beat, min(last.end, media_length))


def _end(rows: Sequence[MeasureRow], j: int, last_end: float) -> float:
    """Where row j ends for a time."""
    return last_end if j == len(rows) - 1 else rows[j].end


def _time_in(
    rows: Sequence[MeasureRow],
    times: Sequence[float],
    first: Sequence[int],
    row: MeasureRow,
    fraction: float,
    segment_end: bool,
    last_end: float,
) -> float | None:
    j = row.count - 1  # a time map keeps every row of its table
    beat = _beat_at(row, fraction)
    if beat == row.beats:  # the fraction 1
        k = _leads_into(rows, j)
        if segment_end or rows[k - 1].closed:
            return _end(rows, k - 1, last_end)
        following = rows[k] if k < len(rows) else None
        if following is not None and following.number == row.number + 1:
            return following.start
        return None
    if beat is not None:
        return times[first[j] + beat]
    position = fraction * row.beats
    k = int(position)  # below row.beats: a fraction this close to 1 is at 1
    start = times[first[j] + k]
    end = times[first[j] + k + 1] if k + 1 < row.beats else _end(rows, j, last_end)
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
    last_end: float,
    *,
    pass_: int | None,
    movement: int | None,
) -> list[float]:
    """As a segment's end, the fraction 0 of bar N: where each time through
    the bar numbered just below N ends, in the pass and movement asked for.

    An end that leads into a bar N the query doesn't name is left out, so a
    label or a pass gives only the ends that lead into the bars it names;
    without them, every bar N is named. A bar that cadenzas follow ends after
    them, and the bar after them is the one it leads into (#339).
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
        others = {row.count for row in find_rows(rows, number)} - named_counts
        for before in find_rows(rows, max(below), pass_=pass_, movement=movement):
            k = _leads_into(rows, before.count - 1)
            if k < len(rows) and rows[k].count in others:
                continue  # a bar N the query doesn't name
            ends.append(_end(rows, k - 1, last_end))
    return ends


def _distinct(times: list[float]) -> list[float]:
    """In time order, without times as close as TiLiA's lookup counts the same."""
    out: list[float] = []
    for time in sorted(times):
        if not out or not math.isclose(time, out[-1]):
            out.append(time)
    return out
