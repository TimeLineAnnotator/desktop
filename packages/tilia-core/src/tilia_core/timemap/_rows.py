"""A beat timeline's measure rows, read from WP3's table with what the later steps need."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from tilia_core import tla

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


def rows_of(timeline: tla.Timeline) -> list[RowIn]:
    """The timeline's measure rows in order; none when it has no measure table.

    `Measure.beat_unit` (the unit in force) and any beat pattern are not read:
    the governing unit is computed from the units set on each row's own beats.
    A beat without a time is logged and left out; a measure whose downbeat has
    none is left out whole, so every row's `id` is its first beat.
    """
    if timeline.measures is None:
        return []
    rows = (_row_in(timeline, row) for row in timeline.measures.rows)
    return [row for row in rows if row is not None]


def _row_in(timeline: tla.Timeline, row: tla.Measure) -> RowIn | None:
    mark = _dict(timeline.components.get(row.id), "measure")
    beat_ids: list[str] = []
    beat_times: list[float] = []
    units: list[tuple[str, tla.BeatUnit]] = []
    for beat_id in row.beats:
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
        cadenza=row.cadenza or bool(mark.get("cadenza")),
        restart=row.restart or bool(mark.get("restart")),
        force_display=row.force_display,
        next=None if row.next is None else tuple(row.next),
        source=row.source,
        metadata=row.metadata,
    )


def _dict(component: tla.Component | None, key: str) -> dict[str, Any]:
    value = component.attrs.get(key) if component is not None else None
    return value if isinstance(value, dict) else {}


def _beat_unit(timeline: tla.Timeline, component: tla.Component) -> tla.BeatUnit | None:
    value = component.attrs.get("beat_unit")
    if value is None:
        return None
    try:
        return tla.BeatUnit(
            denominator=value["denominator"],
            units=value["units"],
            assumed=bool(value.get("assumed", False)),
        )
    except (KeyError, TypeError):
        logger.warning(
            "Timeline %s: beat %s has a beat unit that can't be read; ignored.",
            timeline.id,
            component.id,
        )
        return None
