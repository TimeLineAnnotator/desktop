"""What :func:`tilia_core.tql.run` returns: components, matches and the result."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from . import stats
from .showsql import SqlBlock, render


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
    first one's. ``captures`` are the groups a ``~`` in ``WHERE`` captured.

    A query of only ``WHERE`` that lists timelines or files has no units: its
    matches have empty ``slots`` and name their ``file_id`` (and, for a
    timeline, its ``timeline_id``) instead."""

    slots: list[list[Component]]
    lane: str
    marks: list[list[bool]] | None = None
    captures: tuple[str, ...] = ()
    segments: list[list[tuple[float, float]]] = field(default_factory=list)
    lane_level: int | None = None
    lane_row: str | None = None
    slot_lanes: list[str] = field(default_factory=list)
    file_id: str | None = None
    timeline_id: str | None = None

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
        if first is None:
            if self.timeline_id is not None:
                return f"{self.file_id}|tl:{self.timeline_id}"
            return f"{self.file_id}|file"
        file_id = first.file_id
        steps = (",".join(f"{c.timeline_id}/{c.id}" for c in s) for s in self.slots)
        return f"{file_id}|" + ";".join(steps)


@dataclass
class Result:
    """The matches of a query, as rows of the result table (tql.md §10).

    ``sql_blocks`` are the statements the run executed, in order: each
    :class:`~tilia_core.tql.showsql.SqlBlock` holds a comment naming the part
    of the query it answers, and the statement with its values written in, or
    None where Python takes over. ``sql`` shows them as text. Each statement
    runs on its own through :func:`tilia_core.tql.sql`, which registers TiLiA's
    SQL functions (:mod:`tilia_core.tql.sqlfuncs`); a plain SQLite client lacks
    them."""

    grain: str
    rows: list[dict[str, Any]]
    matches: list[Match]
    explain: str
    sql_blocks: list[SqlBlock]
    warnings: list[str]
    stopped: str | None
    generation: int
    _index: Any = field(default=None, repr=False, compare=False)

    @property
    def sql(self) -> str:
        """The blocks of ``sql_blocks`` as text: each a ``--`` comment line,
        then its statement unless Python takes over there, with a blank line
        between two blocks. The string is for reading only: a value may hold
        a blank line too, so to take it apart split ``sql_blocks`` rather than
        this text. The shown SQL may change, and nothing in it is promised
        yet."""
        return render(self.sql_blocks)

    def to_csv(self, path: str | Path) -> None:
        """Write the table of ``rows`` as CSV: a header of the columns, then a
        line per row; UTF-8 in NFC, LF line endings, no byte-order mark. Times
        are in seconds with three decimals, None is an empty field."""
        columns: list[str] = []
        for row in self.rows:
            columns.extend(c for c in row if c not in columns)
        timed = [bool(_TIME_COLUMN.match(c)) for c in columns]
        stats.write_csv(
            path,
            columns,
            (
                [
                    _seconds(v) if t else v
                    for v, t in zip((row.get(c) for c in columns), timed, strict=True)
                ]
                for row in self.rows
            ),
        )

    def stats(
        self,
        name: str,
        by: str | Sequence[str] | None = None,
        *,
        fold_subtypes: bool = False,
    ) -> stats.Table:
        """A statistics table of the targets: ``counts`` (``by`` one key or two),
        ``durations`` and ``positions`` (one key), or ``transitions`` (none).
        ``by`` is ``label`` unless given; see :mod:`tilia_core.tql.stats`.
        ``fold_subtypes`` makes the ``category`` key the part before the first
        dot. Raises ``ValueError`` for an unknown ``name`` or key."""
        return stats.compute(self, name, by, fold_subtypes=fold_subtypes)


_TIME_COLUMN = re.compile(r"(\$\d+\.)?(start|end)$")


def _seconds(value: Any) -> Any:
    return f"{value:.3f}" if isinstance(value, (int, float)) else value
