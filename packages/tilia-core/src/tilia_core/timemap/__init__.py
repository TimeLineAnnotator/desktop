"""Bars, beats and passes: a beat timeline's measure table, computed when it's asked for, and never stored."""

from __future__ import annotations

from tilia_core import tla
from tilia_core.timemap.table import MeasureRow
from tilia_core.timemap.timemap import Positions, TimeMap, build_time_map

__all__ = ["MeasureRow", "Positions", "TimeMap", "time_map_for"]


def time_map_for(document: tla.Document, timeline_id: str) -> TimeMap | None:
    """The time map of the beat timeline `timeline_id`; None when it has none."""
    timeline = document.timelines.get(timeline_id)
    if timeline is None or timeline.kind != "beat":
        return None
    time_map, _ = build_time_map(document, timeline)
    return time_map
