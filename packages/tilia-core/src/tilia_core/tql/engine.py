"""Run a TQL sequence pattern on an index.

SQL selects each unit's candidates (:mod:`.compile`); this module builds the
lanes of every file, walks them with :func:`.sequences.find_runs` and writes
the result table. ``run`` only reads: it never writes to the index and never
creates a table.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable, Iterator

from tilia_core import derived

from . import compile as tql_compile
from . import sqlfuncs, syntax
from .explain import explain
from .lanes import project
from .result import Component, Match, Result
from .sequences import Item, find_runs, slots_of

MODES = {None: "any", "STARTS_WITH": "start", "ENDS_WITH": "end", "CONSISTS_OF": "full"}


def sql_literal(value: Any) -> str:
    """``value`` written as an SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


class _Log:
    """Executes statements on a connection and remembers them, with their
    parameters written in."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con
        self.statements: list[str] = []

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[Any]:
        parts = sql.split("?")
        text = parts[0] + "".join(
            sql_literal(p) + rest for p, rest in zip(params, parts[1:], strict=True)
        )
        self.statements.append(text.strip().rstrip(";") + ";")
        return self.con.execute(sql, params).fetchall()


def _units(seq: syntax.Seq) -> Iterator[syntax.Unit]:
    """Every ``Unit`` node of ``seq``, groups included."""
    for st in seq.steps:
        if isinstance(st.item, syntax.Group):
            for option in st.item.options:
                yield from _units(option)
        else:
            yield st.item


def _check(query: syntax.Query) -> syntax.SeqPattern:
    p = query.pattern
    if p is None:
        raise NotImplementedError("a query of only WHERE is not available yet (where)")
    if isinstance(p, syntax.RelPattern):
        raise NotImplementedError("relations are not available yet (relations)")
    if p.within is not None:
        raise NotImplementedError("WITHIN is not available yet (within)")
    if query.where:
        raise NotImplementedError("WHERE is not available yet (where)")
    return p


def _load(log: _Log, file_id: str, spec: tql_compile.LaneSpec) -> list[Component]:
    rows = log.execute(
        'SELECT c.id, c.timeline_id, c.kind, c.label, c.start, c."end", h.level, '
        "r.row, r.row_id FROM components c "
        "LEFT JOIN hierarchies h ON h.component_id = c.id "
        "LEFT JOIN ranges r ON r.component_id = c.id "
        "WHERE c.file_id = ? AND c.timeline_id = ? "
        'ORDER BY c.start, c."end", c.id',
        (file_id, spec.timeline_id),
    )
    return [
        Component(r[0], file_id, r[1], r[2], r[3] or "", r[4], r[5], r[6], r[7])
        for r in rows
        if spec.row_id is None or r[8] == spec.row_id
    ]


def _items(spec: tql_compile.LaneSpec, comps: list[Component]) -> list[Item]:
    if spec.kind == "hierarchy":
        assert spec.level is not None
        return project(comps, spec.level)
    kind = spec.kind
    return [(c, c.start, c.end) for c in comps if c.kind == kind]


def _file_title(log: _Log, file_id: str) -> str | None:
    rows = log.execute(
        "SELECT value FROM fields WHERE scope = 'file' AND owner_id = ? "
        "AND name = ?",
        (file_id, derived.field_name("title")),
    )
    return rows[0][0] if rows else None


def run(
    index: Any,
    query: syntax.Query | str,
    *,
    max_matches: int | None = None,
    time_limit: float | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Result:
    """Run ``query`` (a :class:`~tilia_core.tql.syntax.Query` or its text) on
    ``index``. ``time_limit`` and ``cancel`` are accepted for a later part."""
    if isinstance(query, str):
        query = syntax.parse(query)
    pattern = _check(query)
    con = index.connection()
    sqlfuncs.register(con)
    log = _Log(con)
    nodes = list(_units(pattern.seq))
    mode = MODES[pattern.order]
    marked = query.has_target
    n_steps = len(pattern.seq.steps)

    found: dict[tuple[Any, ...], Match] = {}
    order: list[tuple[Any, ...]] = []
    stopped: str | None = None
    for (file_id,) in log.execute("SELECT id FROM files ORDER BY id"):
        specs = tql_compile.resolve_lanes(con, file_id, pattern.lane)
        if not specs:
            continue
        if any(s.kind in ("chord", "key") for s in specs) and not all(
            tql_compile.is_wildcard(u) for u in nodes
        ):
            raise NotImplementedError(
                "labels in chords and keys lanes are for the harmony part"
            )
        fit: dict[int, set[str]] = {}
        for node in nodes:
            sql, params = tql_compile.candidate_statement(node, file_id)
            fit[id(node)] = {r[0] for r in log.execute(sql, params)}

        def fits(
            node: syntax.Unit, comp: Component, fit: dict[int, set[str]] = fit
        ) -> bool:
            return comp.id in fit[id(node)]

        loaded: dict[str, list[Component]] = {}
        for spec in specs:
            comps = loaded.get(spec.timeline_id + (spec.row_id or ""))
            if comps is None:
                comps = loaded[spec.timeline_id + (spec.row_id or "")] = _load(
                    log, file_id, spec
                )
            items = _items(spec, comps)
            if not items:
                continue
            for i, j, assign, flags in find_runs(
                pattern.seq, items, mode, spec.point, fits, marks=marked
            ):
                if flags is not None and not any(flags):
                    continue  # @ took nothing here: no result
                slot_items = slots_of(items, i, j, assign, n_steps)
                match = Match(
                    [[it[0] for it in s] for s in slot_items],
                    spec.description,
                    None
                    if flags is None
                    else slots_of(flags, 0, j - i, assign, n_steps),  # type: ignore[arg-type]
                    segments=[[(it[1], it[2]) for it in s] for s in slot_items],
                    lane_level=spec.level,
                    lane_row=spec.row,
                )
                key = (
                    file_id,
                    spec.timeline_id,
                    tuple(tuple(c.id for c in s) for s in match.slots),
                )
                cur = found.get(key)
                if cur is None:
                    found[key] = match
                    order.append(key)
                    if max_matches is not None and len(order) >= max_matches:
                        stopped = "max_matches"
                        break
                elif (spec.level or 0) > (cur.lane_level or 0):
                    found[key] = match  # the highest reading of the same run
            if stopped:
                break
        if stopped:
            break

    matches = [found[k] for k in order]
    matches.sort(key=lambda m: (_file_of(m), _extent(m)[0]))
    names = {r[0]: r[1] for r in log.execute("SELECT id, name FROM timelines")}
    titles: dict[str, str | None] = {}
    rows = []
    for m in matches:
        fid = _file_of(m)
        if fid not in titles:
            titles[fid] = _file_title(log, fid)
        rows.append(_row(log, m, names, titles[fid]))
    return Result(
        grain="match",
        rows=rows,
        matches=matches,
        explain=explain(query),
        sql="\n\n".join(log.statements),
        warnings=[],
        stopped=stopped,
        generation=index.generation,
    )


# --------------------------------------------------------------------------- #
# The result table (tql.md §10)
# --------------------------------------------------------------------------- #
def _file_of(m: Match) -> str:
    return next(c.file_id for s in m.slots for c in s)


def _targets(m: Match) -> list[tuple[Component, float, float]]:
    out = []
    for n, slot in enumerate(m.slots, 1):
        for k, comp in enumerate(slot):
            if m.is_target(n, k):
                start, end = m.segments[n - 1][k]
                out.append((comp, start, end))
    return out


def _extent(m: Match) -> tuple[float, float]:
    t = _targets(m)
    return min(x[1] for x in t), max(x[2] for x in t)


def _position(log: _Log, comp: Component | None) -> tuple[Any, Any]:
    if comp is None:
        return None, None
    rows = log.execute(
        "SELECT bar, beat FROM positions WHERE component_id = ?", (comp.id,)
    )
    return (rows[0][0], rows[0][1]) if rows else (None, None)


def _lane_column(m: Match) -> str | None:
    if m.lane_level is not None:
        return f"level {m.lane_level}"
    return m.lane_row


def _row(
    log: _Log, m: Match, names: dict[str, str], title: str | None
) -> dict[str, Any]:
    targets = _targets(m)
    first = targets[0][0]
    start, end = _extent(m)
    bar, beat = _position(log, first)
    row: dict[str, Any] = {
        "file": first.file_id,
        "title": title,
        "timeline": names.get(first.timeline_id),
        "lane": _lane_column(m),
        "ids": " ".join(c.id for c, _, _ in targets),
        "label": " → ".join(c.label for c, _, _ in targets),
        "start": start,
        "end": end,
        "bar": bar,
        "beat": beat,
    }
    for n, slot in enumerate(m.slots, 1):
        spans = m.segments[n - 1]
        row[f"${n}.label"] = " → ".join(c.label for c in slot)
        row[f"${n}.timeline"] = m.lane
        row[f"${n}.start"] = min((s for s, _ in spans), default=None)
        row[f"${n}.end"] = max((e for _, e in spans), default=None)
        row[f"${n}.bar"] = _position(log, slot[0] if slot else None)[0]
        row[f"${n}.ids"] = " ".join(c.id for c in slot)
    return row
