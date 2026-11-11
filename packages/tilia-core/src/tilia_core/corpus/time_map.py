"""What the index asks of a file's time map: the seam with WP9.

WP9 (the measure table, TimeLineAnnotator/project-management#13) gives a file's
time map; until it lands, no file has one, and tests pass a fake
(contracts/time-map.md). The index stores what a time map gives: a row of
``measures`` per bar, and a row of ``positions`` per unit whose start lies on
the map.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .documents import Document


@dataclass(frozen=True)
class Measure:
    """One bar, in playing order: a row of ``measures``.

    ``count`` is its place in playing order, from 1; ``number`` and ``label``
    its printed number and name ("16a"); ``start`` and ``end`` its downbeat and
    the next one; ``beats`` how many beats it has; ``pass_`` which pass through
    a repeat it belongs to (1 without repeats); ``time_signature`` how a
    musician reads it ("6/8"); ``cadenza`` whether it is a cadenza bar; and
    ``movement`` which movement or song it is in, from 1. ``beat_unit`` and
    ``assumed`` are WP9's further columns, which the tables don't hold yet."""

    count: int
    number: int
    label: str
    start: float
    end: float
    beats: int
    pass_: int
    beat_unit: int
    time_signature: str | None
    assumed: bool
    cadenza: bool
    movement: int


@dataclass(frozen=True)
class Positions:
    """Where a unit falls on the map: a row of ``positions`` (data-model.md).
    ``cadenza`` and ``movement`` are those of the bar it starts in."""

    bar: int
    end_bar: int
    beat: float
    pass_: int
    bar_count: int
    bar_label: str
    bar_beat_count: int
    downbeat: bool
    cadenza: bool
    movement: int


class TimeMap(Protocol):
    """A file's time map, as the index and the engine use it.

    ``timeline_id`` is the id in the file of the timeline it was built from;
    ``guessed`` is True when that is the first beat timeline, because no
    timeline has the role ``time_map``. ``measures`` is WP13's view of the bars,
    ``(start, end, number, label)``; ``measure_rows`` gives one
    :class:`Measure` per bar in playing order; ``positions`` where a unit
    falls, None when its start is off the map. ``position``, ``length`` and
    ``unit_seconds`` are what queries ask (WP13's contracts/time-map.md)."""

    timeline_id: str
    guessed: bool

    def measures(self) -> list[tuple[float, float, int, str]]: ...

    def measure_rows(self) -> list[Measure]: ...

    def positions(self, start: float, end: float) -> Positions | None: ...

    def position(self, t: float, unit: str = "bar") -> float | None: ...

    def length(self, start: float, end: float, unit: str = "bar") -> float | None: ...

    def unit_seconds(self, t: float, unit: str) -> float | None: ...


@dataclass(frozen=True)
class TimeMapFound:
    """A file's time map, or why it has none, as WP9's ``find_time_map`` says
    (its FR-082: whoever reads a file reports these with it).

    ``reason`` says why the chosen beat timeline gives no time map: None when
    there is one, and for a file without a beat timeline, which has nothing
    wrong. ``warnings`` are WP9's about the file's beat timelines, with or
    without a time map. The index stores them in ``files.time_map_reason`` and
    ``file_warnings``."""

    time_map: TimeMap | None
    reason: str | None = None
    warnings: tuple[str, ...] = ()


TimeMapOf = Callable[
    [Document, Mapping[str, "str | None"]], "TimeMap | TimeMapFound | None"
]
"""The function that gives a file's time map: ``(document, roles) -> TimeMap |
TimeMapFound | None``, with each timeline's role, by its id in the file, as the
index resolved it. A :class:`TimeMapFound` also says why there is no time map,
and what WP9 warns about; a bare time map or None says neither."""


def found(given: TimeMap | TimeMapFound | None) -> TimeMapFound:
    """What a :data:`TimeMapOf` gave, as a :class:`TimeMapFound`."""
    if isinstance(given, TimeMapFound):
        return given
    return TimeMapFound(time_map=given)
