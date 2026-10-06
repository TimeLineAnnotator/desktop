"""What :func:`tilia_core.tql.run` returns: components, matches and the result."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Component:
    """A unit of a timeline, as the index stores it."""

    id: str
    file_id: str
    timeline_id: str
    kind: str
    label: str
    start: float
    end: float
    level: int | None = None
    row: str | None = None


@dataclass
class Match:
    """One match of a sequence: the units each step took, in order.

    ``slots`` has one list per ``$n``; an optional step may hold none.
    ``marks`` says, per slot and unit, whether a step marked ``@`` took it
    (None without ``@``). ``segments`` holds the time each unit fills in the
    lane the match was found in; ``lane_level`` and ``lane_row`` say which
    level or range row that lane is. ``slot_lanes``, when the steps lie in
    different lanes (a relation), names each step's lane; ``lane`` is then the
    first one's."""

    slots: list[list[Component]]
    lane: str
    marks: list[list[bool]] | None = None
    captures: tuple[str, ...] = ()
    segments: list[list[tuple[float, float]]] = field(default_factory=list)
    lane_level: int | None = None
    lane_row: str | None = None
    slot_lanes: list[str] = field(default_factory=list)

    def is_target(self, n: int, k: int) -> bool:
        """Whether unit ``k`` (from 0) of step ``n`` (``$n``, from 1) is the
        result: marked with ``@``, or any unit when the query has no ``@``."""
        if self.marks is None:
            return True
        return self.marks[n - 1][k]

    @property
    def key(self) -> str:
        """A key that names the match and is the same on every run: the file,
        then per step the units' ``timeline/component`` ids."""
        first = next((c for s in self.slots for c in s), None)
        file_id = first.file_id if first is not None else ""
        steps = (",".join(f"{c.timeline_id}/{c.id}" for c in s) for s in self.slots)
        return f"{file_id}|" + ";".join(steps)


@dataclass
class Result:
    """The matches of a query, as rows of the result table (tql.md §10)."""

    grain: str
    rows: list[dict[str, Any]]
    matches: list[Match]
    explain: str
    sql: str
    warnings: list[str]
    stopped: str | None
    generation: int
