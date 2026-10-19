"""Bars, beats and passes: a beat timeline's measure table, computed when it's asked for, and never stored."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from tilia_core import tla
from tilia_core.timemap.table import MeasureRow, build_rows, media_warning
from tilia_core.timemap.timemap import Positions, TimeMap, build_time_map

__all__ = [
    "MeasureRow",
    "Positions",
    "TimeMap",
    "TimeMapFound",
    "find_time_map",
    "measure_rows",
    "time_map_for",
    "time_map_of",
]

logger = logging.getLogger(__name__)

TIME_MAP_ROLE = "time_map"
TWO_CLAIM = "two timelines claim the role time_map; the first by ordinal is used"


@dataclass(frozen=True)
class TimeMapFound:
    """A document's time map as `find_time_map` chose it, or why there is none."""

    time_map: TimeMap | None
    timeline_id: str | None  # the chosen beat timeline, even when it gives no time map
    guessed: bool  # no timeline had the role time_map: the first beat timeline was taken
    reason: str | None  # why the chosen timeline gives no time map
    warnings: tuple[str, ...]  # several claim the role; a last beat past the media


def find_time_map(
    document: tla.Document, roles: Mapping[str, str | None] | None = None
) -> TimeMapFound:
    """The document's time map: its beat timeline whose role is time_map, else
    its first beat timeline by ordinal, guessed.

    `roles` gives each timeline's role by its id, as the caller resolved them
    (the index: from the file and the corpus's manifest), and a timeline it
    leaves out has none; without it, the roles are the file's. When several
    beat timelines have the role, the first by ordinal wins, with a warning.
    When the chosen timeline gives no time map, no other stands in: the file
    has no bars, and `reason` says why. A document without a beat timeline has
    no time map, and nothing is wrong with it: no reason, no warning.

    Every beat timeline whose last beat is at or after the end of the media
    gets a warning, with its id, the time map's or not: it is logged here, once
    for each call, and not when a table is built.
    """
    beat_timelines = sorted(
        (t for t in document.timelines.values() if t.kind == "beat"),
        key=lambda t: t.ordinal,
    )
    if not beat_timelines:
        return TimeMapFound(
            time_map=None, timeline_id=None, guessed=False, reason=None, warnings=()
        )
    claiming = [t for t in beat_timelines if _role(t, roles) == TIME_MAP_ROLE]
    warnings = [TWO_CLAIM] if len(claiming) > 1 else []
    timeline = (claiming or beat_timelines)[0]
    guessed = not claiming
    time_map, reason = build_time_map(document, timeline, guessed=guessed)
    for beats in beat_timelines:
        warning = media_warning(document, beats)
        if warning is not None:
            logger.warning("%s.", warning)
            warnings.append(warning)
    return TimeMapFound(
        time_map=time_map,
        timeline_id=timeline.id,
        guessed=guessed,
        reason=reason,
        warnings=tuple(warnings),
    )


def _role(timeline: tla.Timeline, roles: Mapping[str, str | None] | None) -> object:
    if roles is None:
        return timeline.metadata.get("role")
    return roles.get(timeline.id)


def time_map_of(
    document: tla.Document, roles: Mapping[str, str | None] | None = None
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

    Also for a folded table, which has no time map. No rows while a beat has no
    usable time or a row's beats don't start at its downbeat (`build_rows`),
    and none for a timeline that isn't a beat timeline.
    """
    timeline = _beat_timeline(document, timeline_id)
    if timeline is None:
        return []
    return build_rows(document, timeline)


def _beat_timeline(document: tla.Document, timeline_id: str) -> tla.Timeline | None:
    timeline = document.timelines.get(timeline_id)
    return timeline if timeline is not None and timeline.kind == "beat" else None
