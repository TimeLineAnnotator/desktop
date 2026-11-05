"""Bars, beats and passes: a beat timeline's measure table, computed when it's asked for, and never stored.

Nothing here opens a file. From a `tla.Document`:

- **Choosing and building:** `time_map_of` and `find_time_map` choose a
  document's time map, `time_map_for` takes a named beat timeline's, and
  `measure_rows` gives a timeline's `MeasureRow`s, also where it has no time
  map; `table_problem` says why a table gives none.
- **The time map:** a `TimeMap` says where a time lies (`Positions`), how long
  a span lasts in bars, beats and quarter notes, and where a bar is.
- **Beat units and time signatures:** `meters_of`, over `rows_of`'s `RowIn`s,
  gives each measure's `Meter`, which is `units.MeasureMeter` under a shorter
  name. `format_time_signature` writes a time signature and `TimeSignature`
  reads one. The other names of `units` are exported here too.
- **Plans:** `plan_time_signatures` lists, as a `Plan` of `Change`s, the writes
  that give the bars a source names (`BarRef`) their time signatures.
  `apply_plan` makes them in memory, or raises `PlanOutOfDate`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from tilia_core import tla
from tilia_core.timemap._rows import RowIn, rows_of
from tilia_core.timemap.meters import meters_of
from tilia_core.timemap.plan import (
    BarRef,
    Change,
    Plan,
    PlanOutOfDate,
    TimeSignature,
    apply_plan,
    plan_time_signatures,
)
from tilia_core.timemap.table import (
    FrozenMetadata,
    MeasureRow,
    build_rows,
    closing_warnings,
    format_time_signature,
    media_warning,
    table_problem,
)
from tilia_core.timemap.timemap import Positions, TimeMap, build_time_map
from tilia_core.timemap.units import (
    DEFAULT_DENOMINATOR,
    DEFAULT_UNITS,
    MAX_DENOMINATOR,
    MAX_UNIT_LENGTH,
    MeasureMeter,
    UnitsParseResult,
    fit_units,
    format_units,
    is_fit_ambiguous,
    parse_units,
    validate_denominator,
)

__all__ = [
    "DEFAULT_DENOMINATOR",
    "DEFAULT_UNITS",
    "MAX_DENOMINATOR",
    "MAX_UNIT_LENGTH",
    "BarRef",
    "Change",
    "FrozenMetadata",
    "MeasureMeter",
    "MeasureRow",
    "Meter",
    "Plan",
    "PlanOutOfDate",
    "Positions",
    "RowIn",
    "TimeMap",
    "TimeMapFound",
    "TimeSignature",
    "UnitsParseResult",
    "apply_plan",
    "find_time_map",
    "fit_units",
    "format_time_signature",
    "format_units",
    "is_fit_ambiguous",
    "measure_rows",
    "meters_of",
    "parse_units",
    "plan_time_signatures",
    "rows_of",
    "table_problem",
    "time_map_for",
    "time_map_of",
    "validate_denominator",
]

Meter = MeasureMeter

logger = logging.getLogger(__name__)

TIME_MAP_ROLE = "time_map"


@dataclass(frozen=True)
class TimeMapFound:
    """A document's time map as `find_time_map` chose it, or why there is none."""

    time_map: TimeMap | None
    timeline_id: str | None  # the chosen beat timeline, even when it gives no time map
    guessed: bool  # no timeline had the role time_map: the first beat timeline was taken
    reason: str | None  # why the chosen timeline gives no time map
    # Several claim the role; a last beat past the media; a misplaced closing
    # tap, or one past the media or with a beat unit.
    warnings: tuple[str, ...]


def find_time_map(
    document: tla.Document, roles: Mapping[str, str | list[str] | None] | None = None
) -> TimeMapFound:
    """The document's time map: its beat timeline whose role is time_map, else
    its first beat timeline by ordinal, guessed.

    `roles` gives each timeline's role by its id, as the caller resolved them
    (the index: from the file and the corpus's manifest), and a timeline it
    leaves out has none; without it, the roles are the file's. A role that is a
    list claims time_map when it holds it. When several beat timelines have the
    role, the first by ordinal wins, with a warning that names them. When the
    chosen timeline gives no time map, no other stands in: the file has no
    bars, and `reason` says why. A document without a beat timeline has no
    time map, and nothing is wrong with it: no reason, no warning.

    Every beat timeline whose last beat is at or after the end of the media
    gets a warning too, with its id, the time map's or not; so does each of its
    taps marked closing that is read as an ordinary beat, lies past the media
    or has a beat unit. The warnings are logged here, once for each call, and
    not when a table is built.
    """
    beat_timelines = sorted(
        (t for t in document.timelines.values() if t.kind == "beat"),
        key=_by_ordinal,
    )
    if not beat_timelines:
        return TimeMapFound(
            time_map=None, timeline_id=None, guessed=False, reason=None, warnings=()
        )
    claiming = [t for t in beat_timelines if _claims_the_role(t, roles)]
    warnings = [_several_claim(claiming)] if len(claiming) > 1 else []
    timeline = (claiming or beat_timelines)[0]
    guessed = not claiming
    time_map, reason = build_time_map(document, timeline, guessed=guessed)
    for beats in beat_timelines:
        warning = media_warning(document, beats)
        if warning is not None:
            warnings.append(warning)
        warnings.extend(closing_warnings(document, beats))
    for warning in warnings:
        logger.warning("%s.", warning)
    return TimeMapFound(
        time_map=time_map,
        timeline_id=timeline.id,
        guessed=guessed,
        reason=reason,
        warnings=tuple(warnings),
    )


def _several_claim(claiming: list[tla.Timeline]) -> str:
    ids = [timeline.id for timeline in claiming]
    return (
        f"timelines {', '.join(ids[:-1])} and {ids[-1]} claim the role time_map; "
        f"{ids[0]}, the first by ordinal, is used"
    )


def _by_ordinal(timeline: tla.Timeline) -> tuple[int, float]:
    # An ordinal that isn't a whole number, which the reader doesn't refuse
    # yet, comes after the others, in the document's order.
    ordinal: object = timeline.ordinal
    if isinstance(ordinal, int) and not isinstance(ordinal, bool):
        return 0, ordinal
    if isinstance(ordinal, float) and ordinal.is_integer():
        return 0, ordinal
    return 1, 0


def _claims_the_role(
    timeline: tla.Timeline, roles: Mapping[str, str | list[str] | None] | None
) -> bool:
    role = timeline.metadata.get("role") if roles is None else roles.get(timeline.id)
    if isinstance(role, (list, tuple)):
        return TIME_MAP_ROLE in role
    return role == TIME_MAP_ROLE


def time_map_of(
    document: tla.Document, roles: Mapping[str, str | list[str] | None] | None = None
) -> TimeMap | None:
    """The document's time map, chosen as `find_time_map` chooses it; None when it has none."""
    return find_time_map(document, roles).time_map


def time_map_for(document: tla.Document, timeline_id: str) -> TimeMap | None:
    """The time map of the beat timeline `timeline_id`; None when it has none."""
    timeline = _beat_timeline(document, timeline_id)
    if timeline is None:
        return None
    time_map, _ = build_time_map(document, timeline)
    return time_map


def measure_rows(document: tla.Document, timeline_id: str) -> list[MeasureRow]:
    """The measure table of the beat timeline `timeline_id`, in its order.

    Also for a folded table, which has no time map. No rows while the table
    has a problem (`table_problem`: a beat without a usable time, a row
    whose beats don't start at its downbeat, or two beats at the same time or
    out of time order), and none for a timeline that isn't a beat timeline.
    """
    timeline = _beat_timeline(document, timeline_id)
    if timeline is None:
        return []
    return build_rows(document, timeline)


def _beat_timeline(document: tla.Document, timeline_id: str) -> tla.Timeline | None:
    timeline = document.timelines.get(timeline_id)
    return timeline if timeline is not None and timeline.kind == "beat" else None
