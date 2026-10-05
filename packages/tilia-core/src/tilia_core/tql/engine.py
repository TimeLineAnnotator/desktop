"""Run a TQL query on an index.

SQL selects each unit's candidates (:mod:`.compile`); this module builds the
lanes of every file, walks them with :func:`.sequences.find_runs`, keeps the
matches that meet ``WHERE`` and writes the result table. Relations are in
:mod:`.relations`, the comparisons of conditions in :mod:`.values`, and the
names a query may use in :mod:`.names`. A query of only ``WHERE`` lists
timelines, files or units. ``run`` only reads: it never writes to the index and
never creates a table.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any, Iterator

from tilia_core import derived

from . import compile as tql_compile
from . import names, relations, showsql, sqlfuncs, syntax, values
from .explain import explain
from .inuse import in_use
from .lanes import BAR_KIND
from .readonly import CHECK_EVERY, Limits, Stopped
from .result import Component, Match, Result
from .sequences import find_runs, slots_of
from .showsql import Recorder

MODES = {None: "any", "STARTS_WITH": "start", "ENDS_WITH": "end", "CONSISTS_OF": "full"}


def _sequence_matches(
    scope: relations.Scope,
    pattern: syntax.SeqPattern,
    specs: list[tql_compile.LaneSpec],
    marked: bool,
    limits: Limits,
) -> Iterator[Match]:
    """The matches of a sequence pattern in the lanes ``specs`` of one file."""
    mode = MODES[pattern.order]
    n_steps = len(pattern.seq.steps)
    for node in relations.units_of(pattern.seq):
        scope.fit(node)
    for spec in specs:
        limits.ensure()
        items = scope.lane_items(spec)
        if not items:
            continue
        for i, j, assign, flags in find_runs(
            pattern.seq,
            items,
            mode,
            spec.point,
            scope.fits,
            joins=scope.joiner(pattern.within),
            marks=marked,
            check=limits.ensure,
        ):
            if flags is not None and not any(flags):
                continue  # @ took nothing here: no result
            slot_items = slots_of(items, i, j, assign, n_steps)
            yield Match(
                [[it[0] for it in s] for s in slot_items],
                spec.description,
                None
                if flags is None
                else slots_of(flags, 0, j - i, assign, n_steps),  # type: ignore[arg-type]
                segments=[[(it[1], it[2]) for it in s] for s in slot_items],
                lane_level=spec.level,
                lane_row=spec.row,
            )


def _timeline_row(log: Recorder, m: Match, title: str | None) -> dict[str, Any]:
    """A row of a query of only ``WHERE`` that lists timelines."""
    name, kind, role, author = log.execute(
        "SELECT name, kind, role, author FROM timelines WHERE id = ?",
        (m.timeline_id,),
    )[0]
    return {
        "file": m.file_id,
        "title": title,
        "timeline": name,
        "kind": kind,
        "role": role,
        "author": author,
    }


def _file_row(
    log: Recorder, m: Match, title: str | None, file_fields: list[str]
) -> dict[str, Any]:
    """A row of a query of only ``WHERE`` that lists files: ``file``, ``title``
    and a column for each file field the query names (several values joined by
    ``, ``)."""
    row: dict[str, Any] = {"file": m.file_id, "title": title}
    for name in file_fields:
        if name in row:
            continue
        if name == "id":
            row[name] = m.file_id
            continue
        found = log.execute(
            "SELECT value FROM fields WHERE scope = 'file' AND owner_id = ? "
            "AND name = ? ORDER BY rowid",
            (m.file_id, name),
        )
        row[name] = ", ".join(str(r[0]) for r in found) if found else None
    return row


def _file_title(log: Recorder, file_id: str) -> str | None:
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
    cancel: threading.Event | None = None,
) -> Result:
    """Run ``query`` (a :class:`~tilia_core.tql.syntax.Query` or its text) on
    ``index``, on the connection the index gives the calling thread.

    ``max_matches`` and ``time_limit`` (seconds) are no limit when None; setting
    the ``cancel`` event, from any thread, stops the run too, and interrupts a
    statement that is running. A stopped run does not raise: it returns the
    matches found so far, with their rows, and ``Result.stopped`` says why
    (``"max_matches"``, ``"time_limit"`` or ``"cancelled"``). Nothing is kept
    between calls. Raises ``RuntimeError`` when another thread is running on the
    connection the index gives."""
    if isinstance(query, str):
        query = syntax.parse(query)
    con = index.connection()
    with in_use(con):
        return _run_on(index, con, query, max_matches, time_limit, cancel)


def _run_on(
    index: Any,
    con: sqlite3.Connection,
    query: syntax.Query,
    max_matches: int | None,
    time_limit: float | None,
    cancel: threading.Event | None,
) -> Result:
    """:func:`run` on the connection ``con``, which the caller has marked."""
    pattern = query.pattern
    sqlfuncs.register(con, index)
    log = Recorder(con)
    catalogue = names.read(log)
    names.check(catalogue, query)
    warn = _Warnings()
    extra: list[str] = []
    limits = Limits(time_limit, cancel)
    stopped: str | None = None
    matches: list[Match] = []
    grain = "match"
    con.set_progress_handler(limits, CHECK_EVERY)
    try:
        if pattern is None:
            grain, matches, extra, stopped = _where_only(
                index, log, catalogue, query, warn, max_matches, limits
            )
        else:
            matches, stopped = _pattern_matches(
                index, log, query, pattern, max_matches, warn, limits
            )
    finally:
        con.set_progress_handler(None, 0)
    if pattern is not None:
        warn.words.update(dict.fromkeys(_harmony_warnings(log, query)))
    titles: dict[str, str | None] = {}
    rows = []
    node_names = {r[0]: r[1] for r in log.execute("SELECT id, name FROM timelines")}
    for m in matches:
        fid = m.file_id or _file_of(m)
        if fid not in titles:
            titles[fid] = _file_title(log, fid)
        if grain == "match":
            rows.append(_row(log, m, node_names, titles[fid]))
        elif grain == "timeline":
            rows.append(_timeline_row(log, m, titles[fid]))
        else:
            rows.append(_file_row(log, m, titles[fid], extra))
    return Result(
        grain=grain,
        rows=rows,
        matches=matches,
        explain=explain(query),
        sql=log.text,
        warnings=warn.messages(),
        stopped=stopped,
        generation=index.generation,
        _index=index,
    )


class _Warnings:
    """What parts of the corpus could not answer, by the files they concern."""

    def __init__(self) -> None:
        self.files: dict[str, set[str]] = {}
        self.words: dict[str, None] = {}  # literals that are no chord or key

    def file_lacks(self, field_name: str, file_id: str) -> None:
        self.file_without(f"the file field {field_name!r}", file_id)

    def file_without(self, what: str, file_id: str) -> None:
        """File ``file_id`` lacks ``what`` (a time map, a media length, …)."""
        self.files.setdefault(what, set()).add(file_id)

    def scope_lacks(
        self, scope: relations.Scope, needs: tuple[bool, bool], file_id: str
    ) -> None:
        """What ``scope``'s file lacked of what the query needed of it."""
        for name in sorted(scope.missing):
            self.file_lacks(name, file_id)
        needs_map, needs_length = needs
        if needs_map and scope.time_map is None:
            self.file_without("a time map", file_id)
        if needs_length and (scope.no_length or scope.facts.media_length() is None):
            self.file_without("a media length", file_id)

    def messages(self) -> list[str]:
        out = []
        for what, files in self.files.items():
            n = len(files)
            out.append(
                f"{n} file{'s' if n != 1 else ''} without {what} could not answer"
            )
        return out + list(self.words)


def _lane_units(
    query: syntax.Query,
) -> Iterator[tuple[syntax.Unit, syntax.Lane | None]]:
    """Every unit of a pattern with the lane its literal is read in: the
    pattern's, or the ``IN`` of the relation whose target it is."""
    pattern = query.pattern
    if isinstance(pattern, syntax.SeqPattern):
        yield from _seq_units(pattern.seq, pattern.lane)
    elif isinstance(pattern, syntax.RelPattern):
        yield from _unit_units(pattern.left, pattern.lane)
        yield from _seq_units(
            pattern.relation.target, pattern.relation.lane or pattern.lane
        )


def _seq_units(
    seq: syntax.Seq, lane: syntax.Lane | None
) -> Iterator[tuple[syntax.Unit, syntax.Lane | None]]:
    for step in seq.steps:
        if isinstance(step.item, syntax.Group):
            for option in step.item.options:
                yield from _seq_units(option, lane)
        else:
            yield from _unit_units(step.item, lane)


def _unit_units(
    unit: syntax.Unit, lane: syntax.Lane | None
) -> Iterator[tuple[syntax.Unit, syntax.Lane | None]]:
    yield unit, lane
    for cond in unit.conds:
        if isinstance(cond, syntax.RelCond):
            rel = cond.relation
            yield from _seq_units(rel.target, rel.lane or lane)


def _harmony_warnings(log: Recorder, query: syntax.Query) -> list[str]:
    """What the literals of ``query`` that are read as chords or keys and are
    neither, in the chords and keys lanes they are looked for in, warn."""
    pairs = list(_lane_units(query))
    out: list[str] = []
    for (file_id,) in log.execute("SELECT id FROM files ORDER BY id"):
        for unit, lane in pairs:
            kinds = {s.kind for s in tql_compile.resolve_lanes(log.con, file_id, lane)}
            for kind in ("chord", "key"):
                if kind in kinds:
                    out.extend(tql_compile.harmony_problems(unit, kind))
    return out


def _lanes_with_labels_and_more(
    scope: relations.Scope, harmony: bool
) -> list[tql_compile.LaneSpec]:
    """The default lanes of a file, and, for a question about harmony, the
    chords and keys of its timelines."""
    specs = list(scope.lanes(None))
    if harmony:
        rows = scope.log.execute(
            "SELECT id FROM timelines WHERE file_id = ? ORDER BY ordinal",
            (scope.file_id,),
        )
        for (tid,) in rows:
            specs.extend(s for s in scope.own_lanes(tid) if s.kind in ("chord", "key"))
    return specs


def _lanes_of_seq(seq: syntax.Seq) -> Iterator[syntax.Lane]:
    for unit in relations.units_of(seq):
        for cond in unit.conds:
            yield from _lanes_of_cond(cond)


def _lanes_of_cond(cond: syntax.Cond) -> Iterator[syntax.Lane]:
    if isinstance(cond, syntax.RelCond):
        yield from _lanes_of_relation(cond.relation)
    elif isinstance(cond, syntax.Children):
        yield from _lanes_of_seq(cond.seq)


def _lanes_of_relation(rel: syntax.Relation) -> Iterator[syntax.Lane]:
    if rel.lane is not None:
        yield rel.lane
    yield from _lanes_of_seq(rel.target)


def _named_lanes(query: syntax.Query) -> Iterator[syntax.Lane]:
    """Every ``IN`` lane of ``query``, in the pattern and in ``WHERE``."""
    pattern = query.pattern
    if pattern is not None and pattern.lane is not None:
        yield pattern.lane
    if isinstance(pattern, syntax.SeqPattern):
        yield from _lanes_of_seq(pattern.seq)
    elif isinstance(pattern, syntax.RelPattern):
        for cond in pattern.left.conds:
            yield from _lanes_of_cond(cond)
        yield from _lanes_of_relation(pattern.relation)
    for cond in query.where:
        yield from _lanes_of_cond(cond)


def _lanes_in_play(
    scope: relations.Scope, query: syntax.Query, specs: list[tql_compile.LaneSpec]
) -> list[tql_compile.LaneSpec]:
    """Every lane of the file the query can read a unit in: ``specs``, the
    other lanes of their timelines, and the lanes the query names. A statement
    that tests a unit reads chords, keys and labels only where they can be."""
    out = list(specs)
    for tid in dict.fromkeys(spec.timeline_id for spec in specs):
        out.extend(scope.own_lanes(tid))
    for lane in _named_lanes(query):
        out.extend(scope.lanes(lane))
    if query.pattern is not None and query.pattern.lane is None:
        out.extend(_lanes_with_labels_and_more(scope, True))  # no IN: harmony too
    return list(dict.fromkeys(out))


def _pattern_matches(
    index: Any,
    log: Recorder,
    query: syntax.Query,
    pattern: syntax.SeqPattern | syntax.RelPattern,
    max_matches: int | None,
    warn: _Warnings,
    limits: Limits,
) -> tuple[list[Match], str | None]:
    """The matches of a sequence or relation pattern in every file, those that
    meet ``WHERE`` only, in file and time order, and why the search stopped
    early, if it did."""
    marked = query.has_target
    single = names.is_single(query)
    needs = names.time_needs(query)
    found: dict[tuple[Any, ...], Match] = {}
    order: list[tuple[Any, ...]] = []
    stopped: str | None = None
    labels = showsql.describe_units(query)
    try:
        limits.ensure()
        for (file_id,) in log.execute("SELECT id FROM files ORDER BY id"):
            limits.ensure()
            scope = relations.Scope(
                log, file_id, index.time_map(file_id), labels, limits.ensure
            )
            specs = scope.lanes(pattern.lane)
            if not specs:
                continue
            scope.play = _lanes_in_play(scope, query, specs)
            if isinstance(pattern, syntax.RelPattern):
                part = showsql.relation_part(query)
                found_here = relations.matches(scope, pattern, specs, part)
            else:
                found_here = _sequence_matches(scope, pattern, specs, marked, limits)
            for match in found_here:
                limits.ensure()
                if query.where:
                    first = next(c for slot in match.slots for c in slot)
                    subject = values.Subject(match.slots, first.timeline_id, single)
                    ok, caps = scope.where_ok(query.where, subject)
                    if not ok:
                        continue
                    match.captures = caps
                key = (file_id, tuple(tuple(c.id for c in s) for s in match.slots))
                cur = found.get(key)
                if cur is None:
                    if max_matches is not None and len(order) >= max_matches:
                        stopped = "max_matches"
                        break
                    found[key] = match
                    order.append(key)
                elif (match.lane_level or 0) > (cur.lane_level or 0):
                    found[key] = match  # the highest reading of the same run
            if not _is_join(pattern):
                log.note(showsql.python_stage(query))
            if query.where:
                log.note(
                    f"{showsql.where_text(query)}: tested in Python on each match."
                )
            warn.scope_lacks(scope, needs, file_id)
            if stopped:
                break
    except (Stopped, sqlite3.OperationalError) as err:
        stopped = limits.reason_of(err)

    matches = [found[k] for k in order]
    matches.sort(key=lambda m: (_file_of(m), _extent(m)[0]))
    return matches, stopped


def _is_join(pattern: syntax.SeqPattern | syntax.RelPattern) -> bool:
    """Whether SQL alone matches ``pattern``: a sentence-form timing relation,
    one join."""
    return (
        isinstance(pattern, syntax.RelPattern)
        and not pattern.relation.negate
        and relations.joins(pattern.relation)
        and not tql_compile.on_bars(pattern.lane)
    )


def _where_only(
    index: Any,
    log: Recorder,
    cat: names.Catalogue,
    query: syntax.Query,
    warn: _Warnings,
    max_matches: int | None,
    limits: Limits,
) -> tuple[str, list[Match], list[str], str | None]:
    """``WHERE`` alone: timelines when it names timeline fields, files when it
    names only file fields, and units otherwise. Also the file fields it names,
    for the columns of a file row, and why the search stopped early, if it did."""
    grain = names.where_grain(cat, query)
    harmony = names.asks_about_harmony(query)
    needs = names.time_needs(query)
    log.note(
        f"{showsql.where_text(query)}: tested in Python on each {'unit' if grain == 'match' else grain}."
    )
    matches: list[Match] = []
    stopped: str | None = None
    where = showsql.where_text(query)
    files_part = f"{where}: the files" if grain == "file" else None

    def add(match: Match) -> bool:
        """Keep ``match``; False when the limit is reached instead."""
        nonlocal stopped
        if max_matches is not None and len(matches) >= max_matches:
            stopped = "max_matches"
            return False
        matches.append(match)
        return True

    try:
        limits.ensure()
        for (file_id,) in log.execute(
            "SELECT id FROM files ORDER BY id", part=files_part
        ):
            limits.ensure()
            scope = relations.Scope(
                log, file_id, index.time_map(file_id), check=limits.ensure
            )
            timelines = log.execute(
                "SELECT id, name FROM timelines WHERE file_id = ? ORDER BY ordinal",
                (file_id,),
                part=f"{where}: the timelines of {file_id}"
                if grain == "timeline"
                else None,
            )
            if grain == "file":
                ok, caps = scope.where_ok(query.where, values.Subject([], None))
                if ok and not add(Match([], "", captures=caps, file_id=file_id)):
                    break
            elif grain == "timeline":
                for tid, name in timelines:
                    limits.ensure()
                    subject = values.Subject([], tid)
                    ok, caps = scope.where_ok(query.where, subject)
                    if ok and not add(
                        Match([], name, captures=caps, file_id=file_id, timeline_id=tid)
                    ):
                        break
            else:
                specs = _lanes_with_labels_and_more(scope, harmony)
                scope.play = _lanes_in_play(scope, query, specs)
                seen: set[str] = set()
                for spec in specs:
                    limits.ensure()
                    for comp, _, _ in scope.lane_items(spec):
                        if comp.id in seen:
                            continue
                        seen.add(comp.id)
                        limits.ensure()
                        subject = values.Subject([[comp]], comp.timeline_id)
                        ok, caps = scope.where_ok(query.where, subject)
                        if ok:
                            match = scope.match(comp, [])
                            match.captures = caps
                            if not add(match):
                                break
                    if stopped:
                        break
            warn.scope_lacks(scope, needs, file_id)
            if stopped:
                break
    except (Stopped, sqlite3.OperationalError) as err:
        stopped = limits.reason_of(err)
    if grain == "match":
        matches.sort(key=lambda m: (_file_of(m), _extent(m)[0]))
    return grain, matches, names.named_file_fields(cat, query), stopped


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


def _position(log: Recorder, comp: Component | None) -> tuple[Any, Any]:
    if comp is None:
        return None, None
    if comp.kind == BAR_KIND:  # a bar is no component: it starts on its first beat
        rows = log.execute(
            "SELECT number FROM measures WHERE file_id = ? AND start = ?",
            (comp.file_id, comp.start),
        )
        return (rows[0][0], 1.0) if rows else (None, None)
    rows = log.execute(
        "SELECT bar, beat FROM positions WHERE component_id = ?", (comp.id,)
    )
    return (rows[0][0], rows[0][1]) if rows else (None, None)


def _lane_column(m: Match) -> str | None:
    if m.lane_level is not None:
        return f"level {m.lane_level}"
    return m.lane_row


def _row(
    log: Recorder, m: Match, names: dict[str, str], title: str | None
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
        row[f"${n}.timeline"] = m.slot_lanes[n - 1] if m.slot_lanes else m.lane
        row[f"${n}.start"] = min((s for s, _ in spans), default=None)
        row[f"${n}.end"] = max((e for _, e in spans), default=None)
        row[f"${n}.bar"] = _position(log, slot[0] if slot else None)[0]
        row[f"${n}.ids"] = " ".join(c.id for c in slot)
    return row
