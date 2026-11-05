"""A beat timeline's measure rows, read from WP3's table with what the later steps need."""

from __future__ import annotations

import bisect
import copy
import logging
import math
from dataclasses import dataclass, field
from typing import Any, TypeGuard

from tilia_core import tla
from tilia_core.timemap.units import parse_units, validate_denominator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RowIn:
    """One measure of the table, with its beats' times and the units set on its beats."""

    id: str  # its downbeat's id
    number: int
    label: str
    beat_ids: tuple[str, ...]
    beat_times: tuple[float, ...]
    units: tuple[tuple[str, tla.BeatUnit], ...]  # (beat id, unit), in beat order
    cadenza: bool
    restart: bool
    force_display: bool
    next: tuple[str, ...] | None
    source: str
    metadata: dict[str, str | list[str]] = field(default_factory=dict)
    closing: float | None = None  # the time of the closing tap that ends it


@dataclass(frozen=True)
class ClosingTap:
    """A tap marked `closing`, and what it is where it stands (FR-011)."""

    id: str
    time: float
    row: str | None  # the row it falls in, by its downbeat; None before the first
    barline: bool  # it ends that row; else it is read as an ordinary beat


def rows_of(timeline: tla.Timeline) -> list[RowIn]:
    """The timeline's measure rows in order; none when it has no measure table.

    `Measure.beat_unit` (the unit in force) and any beat pattern are not read:
    the governing unit is computed from the units set on each row's own beats.
    A beat without a time is logged and left out; a measure whose downbeat has
    none is left out whole, so every row's `id` is its first beat.

    A closing tap is in no row's beats, and gives the row it closes its
    `closing`. WP3's table leaves out every tap marked closing, so one read as
    an ordinary beat (`closing_taps`) is put back here, among its row's beats.

    These are the rows `meters_of` takes. They are read as they stand, and
    `table_problem` isn't applied: for a table it calls broken, such as beats
    at 1.0, 0.5 and 2.0, this still gives rows where `measure_rows` gives none.
    """
    if timeline.measures is None:
        return []
    taps = closing_taps(timeline)
    rows = (
        _row_in(timeline, row, [tap for tap in taps if tap.row == row.id])
        for row in timeline.measures.rows
    )
    return [row for row in rows if row is not None]


def closing_taps(timeline: tla.Timeline) -> list[ClosingTap]:
    """The taps marked `closing` that have a usable time, in time order.

    One is a closing barline when it is the last tap of the timeline, or the
    last before a row with `restart`, with a row before it to close. Any other
    is read as an ordinary beat of the row it falls in, and has a warning
    (`table.closing_warnings`), though before the first row no beat is in a
    measure. Its `measure` mark, if it has one, starts no row: that is so of
    any closing tap's (TimeLineAnnotator/project-management#375).
    """
    marked = sorted(
        (component.attrs["time"], component.id)
        for component in timeline.components.values()
        if component.kind == "beat"
        and component.attrs.get("closing")
        and _is_number(component.attrs.get("time"))
    )
    table = timeline.measures
    if not marked or table is None:
        return []
    rows: list[tla.Measure] = []
    starts: list[float] = []
    for row in table.rows:
        start = _time_of(timeline, row.id)
        if start is not None:
            rows.append(row)
            starts.append(start)
    falls_in = [bisect.bisect_right(starts, time) - 1 for time, _ in marked]
    taps: list[ClosingTap] = []
    for index, ((time, tap_id), j) in enumerate(zip(marked, falls_in, strict=True)):
        row = rows[j] if j >= 0 else None
        barline = (
            row is not None
            and (j + 1 == len(rows) or rows[j + 1].restart)
            and (index + 1 == len(marked) or falls_in[index + 1] != j)
            and all(_before(timeline, beat, time) for beat in row.beats)
        )
        taps.append(
            ClosingTap(
                id=tap_id,
                time=time,
                row=row.id if row is not None else None,
                barline=barline,
            )
        )
    return taps


def _time_of(timeline: tla.Timeline, beat_id: str) -> int | float | None:
    component = timeline.components.get(beat_id)
    time = component.attrs.get("time") if component is not None else None
    return time if _is_number(time) else None


def _before(timeline: tla.Timeline, beat_id: str, time: float) -> bool:
    beat_time = _time_of(timeline, beat_id)
    return beat_time is None or beat_time < time


def _is_number(value: object) -> TypeGuard[int | float]:
    """A finite number, as JSON stores one: not a bool, NaN, an infinity, or a
    whole number too large for a float, which JSON reads as an int."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _beats_with(
    timeline: tla.Timeline, row: tla.Measure, taps: list[ClosingTap]
) -> list[str]:
    """The row's beats, in order, with the taps read as ordinary beats among them."""
    beats = list(row.beats)
    for tap in taps:
        if not tap.barline:
            place = sum(_before(timeline, beat, tap.time) for beat in beats)
            beats.insert(place, tap.id)
    return beats


def _row_in(
    timeline: tla.Timeline, row: tla.Measure, taps: list[ClosingTap]
) -> RowIn | None:
    beat_ids: list[str] = []
    beat_times: list[float] = []
    units: list[tuple[str, tla.BeatUnit]] = []
    for beat_id in _beats_with(timeline, row, taps):
        component = timeline.components.get(beat_id)
        time = component.attrs.get("time") if component is not None else None
        if time is None:
            logger.warning(
                "Timeline %s: beat %s of measure %s has no time; skipped.",
                timeline.id,
                beat_id,
                row.id,
            )
            continue
        beat_ids.append(beat_id)
        beat_times.append(time)
        unit = _beat_unit(timeline, component)
        if unit is not None:
            units.append((beat_id, unit))
    if not beat_ids or beat_ids[0] != row.id:
        logger.warning(
            "Timeline %s: the downbeat of measure %s has no time; the measure is skipped.",
            timeline.id,
            row.id,
        )
        return None
    return RowIn(
        id=row.id,
        number=row.number,
        label=row.label,
        beat_ids=tuple(beat_ids),
        beat_times=tuple(beat_times),
        units=tuple(units),
        cadenza=row.cadenza,
        restart=row.restart,
        force_display=row.force_display,
        next=None if row.next is None else tuple(row.next),
        source=row.source,
        metadata=copy.deepcopy(row.metadata),
        closing=next((tap.time for tap in taps if tap.barline), None),
    )


def _dict(component: tla.Component | None, key: str) -> dict[str, Any]:
    value = component.attrs.get(key) if component is not None else None
    return value if isinstance(value, dict) else {}


def _beat_unit(timeline: tla.Timeline, component: tla.Component) -> tla.BeatUnit | None:
    """The unit set on a beat; None, with a warning, when it can't be read."""
    value = component.attrs.get("beat_unit")
    if value is None:
        return None
    try:
        unit: tla.BeatUnit | None = tla.BeatUnit(
            denominator=value["denominator"],
            units=value["units"],
            assumed=bool(value.get("assumed", False)),
        )
    except (KeyError, TypeError):
        unit = None
    if unit is None or not _readable(unit):
        logger.warning(
            "Timeline %s: beat %s has a beat unit that can't be read (%.60r); ignored.",
            timeline.id,
            component.id,
            value,
        )
        return None
    return unit


def _readable(unit: tla.BeatUnit) -> bool:
    # What desktop#621 refuses to create, and so drops from a file it loads.
    return (
        isinstance(unit.units, str)
        and parse_units(unit.units).is_valid
        and validate_denominator(unit.denominator)
    )
