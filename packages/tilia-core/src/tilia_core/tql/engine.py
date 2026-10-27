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

from typing import Any, Callable, Iterator

from tilia_core import derived
from tilia_core.labels import fold

from . import compile as tql_compile
from . import names, relations, showsql, sqlfuncs, syntax, values
from .explain import explain
from .lanes import BAR_KIND
from .result import Component, Match, Result
from .sequences import find_runs, slots_of
from .showsql import Recorder
from .syntax import TQLError

MODES = {None: "any", "STARTS_WITH": "start", "ENDS_WITH": "end", "CONSISTS_OF": "full"}


def _sequence_matches(
    scope: relations.Scope,
    pattern: syntax.SeqPattern,
    specs: list[tql_compile.LaneSpec],
    marked: bool,
) -> Iterator[Match]:
    """The matches of a sequence pattern in the lanes ``specs`` of one file.
    ``THEN … WITHIN`` in bars or beats on a file without a time map has none:
    the file could not answer."""
    if relations.uses_map(pattern.within) and scope.time_map is None:
        return
    mode = MODES[pattern.order]
    n_steps = len(pattern.seq.steps)
    tql_compile.check_labels(specs, relations.units_of(pattern.seq))
    for node in relations.units_of(pattern.seq):
        scope.fit(node)
    for spec in specs:
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
    cancel: Callable[[], bool] | None = None,
) -> Result:
    """Run ``query`` (a :class:`~tilia_core.tql.syntax.Query` or its text) on
    ``index``. ``time_limit`` and ``cancel`` are accepted for a later part."""
    if isinstance(query, str):
        query = syntax.parse(query)
    pattern = query.pattern
    con = index.connection()
    sqlfuncs.register(con, index)
    log = Recorder(con)
    catalogue = names.read(log)
    names.check(catalogue, query)
    warn = _Warnings()
    extra: list[str] = []
    stopped: str | None = None
    if pattern is None:
        grain, matches, extra = _where_only(index, log, catalogue, query, warn)
        if max_matches is not None and len(matches) > max_matches:
            matches, stopped = matches[:max_matches], "max_matches"
    else:
        grain = "match"
        matches, stopped = _pattern_matches(
            index, log, query, pattern, max_matches, warn
        )
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
        sql_blocks=log.blocks,
        warnings=warn.messages(),
        stopped=stopped,
        generation=index.generation,
        columns=_columns(grain, query, extra),
        _index=index,
    )


class _Warnings:
    """What parts of the corpus could not answer, by the files they concern."""

    def __init__(self) -> None:
        self.files: dict[str, set[str]] = {}
        self.words: dict[str, None] = {}  # literals that are no chord or key
        self.other: list[str] = []

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
        out = list(self.other)
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
    neither, in the chords and keys lanes they are looked for in, warn. Only
    a unit with a literal that is no chord or no key can warn, so the lanes
    (resolved once per file and ``IN``) are looked up for those alone."""
    pairs = [
        (unit, lane)
        for unit, lane in _lane_units(query)
        if tql_compile.harmony_problems(unit, ("chord",))
        or tql_compile.harmony_problems(unit, ("key",))
    ]
    if not pairs:
        return []
    custom: dict[str, bool] = {}

    def has_custom(text: str) -> bool:
        if text not in custom:
            found = log.con.execute(
                "SELECT 1 FROM chords WHERE trim(custom_text) = ? LIMIT 1", (text,)
            ).fetchone()
            custom[text] = found is not None
        return custom[text]

    out: list[str] = []
    # lookups, not search statements: kept out of the SQL a result shows
    for (file_id,) in log.con.execute("SELECT id FROM files ORDER BY id"):
        kinds_of: dict[int, tuple[str, ...]] = {}
        for unit, lane in pairs:
            if id(lane) not in kinds_of:
                specs = tql_compile.resolve_lanes(log.con, file_id, lane)
                kinds = {s.kind for s in specs}
                kinds_of[id(lane)] = tuple(k for k in ("chord", "key") if k in kinds)
            if kinds_of[id(lane)]:
                out.extend(
                    tql_compile.harmony_problems(unit, kinds_of[id(lane)], has_custom)
                )
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


def _pattern_matches(
    index: Any,
    log: Recorder,
    query: syntax.Query,
    pattern: syntax.SeqPattern | syntax.RelPattern,
    max_matches: int | None,
    warn: _Warnings,
) -> tuple[list[Match], str | None]:
    """The matches of a sequence or relation pattern in every file, those that
    meet ``WHERE`` only, in file and time order."""
    marked = query.has_target
    single = names.is_single(query)
    needs = names.time_needs(query)
    found: dict[tuple[Any, ...], Match] = {}
    order: list[tuple[Any, ...]] = []
    stopped: str | None = None
    labels = showsql.describe_units(query)
    any_lane = False
    for (file_id,) in log.execute("SELECT id FROM files ORDER BY id"):
        scope = relations.Scope(log, file_id, index.time_map(file_id), labels)
        specs = scope.lanes(pattern.lane)
        if not specs:
            continue
        any_lane = True
        if isinstance(pattern, syntax.RelPattern):
            part = showsql.relation_part(query)
            found_here = relations.matches(scope, pattern, specs, part)
        else:
            found_here = _sequence_matches(scope, pattern, specs, marked)
        for match in found_here:
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
                # the limit is hit by the match it refuses, not by the
                # one that reaches it: a complete result is not cut
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
            log.note(f"{showsql.where_text(query)}: tested in Python on each match.")
        warn.scope_lacks(scope, needs, file_id)
        if stopped:
            break
    if pattern.lane is not None and not any_lane:
        _no_lane(log, pattern.lane, warn.other)

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
) -> tuple[str, list[Match], list[str]]:
    """``WHERE`` alone: timelines when it names timeline fields, files when it
    names only file fields, and units otherwise. Also the file fields it names,
    for the columns of a file row."""
    grain = names.where_grain(cat, query)
    harmony = names.asks_about_harmony(query)
    needs = names.time_needs(query)
    log.note(
        f"{showsql.where_text(query)}: tested in Python on each {'unit' if grain == 'match' else grain}."
    )
    matches: list[Match] = []
    where = showsql.where_text(query)
    files_part = f"{where}: the files" if grain == "file" else None
    for (file_id,) in log.execute("SELECT id FROM files ORDER BY id", part=files_part):
        scope = relations.Scope(log, file_id, index.time_map(file_id))
        timelines = log.execute(
            "SELECT id, name FROM timelines WHERE file_id = ? ORDER BY ordinal",
            (file_id,),
            part=f"{where}: the timelines of {file_id}"
            if grain == "timeline"
            else None,
        )
        if grain == "file":
            ok, caps = scope.where_ok(query.where, values.Subject([], None))
            if ok:
                matches.append(Match([], "", captures=caps, file_id=file_id))
        elif grain == "timeline":
            for tid, name in timelines:
                subject = values.Subject([], tid)
                ok, caps = scope.where_ok(query.where, subject)
                if ok:
                    matches.append(
                        Match([], name, captures=caps, file_id=file_id, timeline_id=tid)
                    )
        else:
            seen: set[str] = set()
            for spec in _lanes_with_labels_and_more(scope, harmony):
                for comp, _, _ in scope.lane_items(spec):
                    if comp.id in seen:
                        continue
                    seen.add(comp.id)
                    subject = values.Subject([[comp]], comp.timeline_id)
                    ok, caps = scope.where_ok(query.where, subject)
                    if ok:
                        match = scope.match(comp, [])
                        match.captures = caps
                        matches.append(match)
        warn.scope_lacks(scope, needs, file_id)
    if grain == "match":
        matches.sort(key=lambda m: (_file_of(m), _extent(m)[0]))
    return grain, matches, names.named_file_fields(cat, query)


ROLE_HINTS = {
    "form": "IN hierarchies",
    "cadences": "IN markers",
    "harmony": "IN chords",
    "keys": "IN key",
    "time_map": "IN beats",
}


def _no_lane(log: Recorder, lane: syntax.Lane, warnings: list[str]) -> None:
    """No file of the corpus has a lane ``lane`` names. A role or kind no
    timeline has is a warning (a role: with the kind to try instead; in a
    corpus with no roles at all, that it has none); a word that is neither, nor
    a timeline or row name, is an error on the name."""
    if not lane.quoted:
        word = fold(lane.text.strip())
        word = tql_compile.ROLE_ALIASES.get(word, word)
        stored = {
            r[0]
            for r in log.execute(
                "SELECT DISTINCT role FROM timelines WHERE role IS NOT NULL"
            )
        }
        if word in tql_compile.BUILTIN_ROLES and not stored:
            # one warning for the whole corpus, not one per role or file
            warnings.append(
                f"this corpus has no roles - try {ROLE_HINTS[word]} or a quoted "
                '"timeline name"'
            )
            return
        if word in tql_compile.BUILTIN_ROLES:
            hint = ROLE_HINTS[word]
            warnings.append(
                f"no timeline has the role {word!r} - try {hint}, a quoted "
                '"timeline name", or give a timeline the role: '
                f'WHERE tl.name ~ /…/ -> SET tl.role = "{word}"'
            )
            return
        if (
            word in stored
            or word in tql_compile.KIND_WORDS
            or word in tql_compile.BAR_WORDS
        ):
            return
    if lane.quoted:
        raise TQLError(
            f'no timeline or row called "{lane.text}" - a quoted name keeps its '
            "case; * is a wildcard",
            lane.pos,
            lane.pos + len(lane.text) + 2,
        )
    raise TQLError(
        f"no timeline, role or kind called {lane.text!r} - roles: "
        f"{', '.join(tql_compile.BUILTIN_ROLES)}; kinds: hierarchies, markers, "
        'ranges, beats, bars, chords, keys; or a quoted "timeline name" (* is a '
        "wildcard)",
        lane.pos,
        lane.pos + len(lane.text),
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


def _position(log: Recorder, comp: Component | None) -> tuple[Any, Any]:
    if comp is None:
        return None, None
    # not logged: one lookup per target and per step would grow the shown
    # SQL by several statements per match
    if comp.kind == BAR_KIND:  # a bar is no component: it starts on its first beat
        rows = log.con.execute(
            "SELECT number FROM measures WHERE file_id = ? AND start = ?",
            (comp.file_id, comp.start),
        ).fetchall()
        return (rows[0][0], 1.0) if rows else (None, None)
    rows = log.con.execute(
        "SELECT bar, beat FROM positions WHERE component_id = ?", (comp.id,)
    ).fetchall()
    return (rows[0][0], rows[0][1]) if rows else (None, None)


RESULT_COLUMNS = ("file", "title", "timeline", "lane", "ids", "label")
RESULT_COLUMNS += ("symbol", "roman", "start", "end", "bar", "beat")
STEP_COLUMNS = ("label", "timeline", "start", "end", "bar", "ids")
TIMELINE_COLUMNS = ("file", "title", "timeline", "kind", "role", "author")


def _columns(grain: str, query: syntax.Query, file_fields: list[str]) -> list[str]:
    """The columns of the result table (tql.md §10), as ``_row``,
    ``_timeline_row`` and ``_file_row`` write them; a query of only ``WHERE``
    that lists units has the one numbered unit each match holds."""
    if grain == "timeline":
        return list(TIMELINE_COLUMNS)
    if grain == "file":
        return ["file", "title", *(f for f in file_fields if f not in ("file", "title"))]
    steps = query.slot_count if query.pattern is not None else 1
    return [
        *RESULT_COLUMNS,
        *(f"${n}.{c}" for n in range(1, steps + 1) for c in STEP_COLUMNS),
    ]


def _chord_names(log: Recorder, comps: list[Component]) -> dict[str, str | None]:
    """The ``symbol`` and ``roman`` columns: a chord result's symbols and Roman
    numerals, joined as its labels are; None for a result without chords. The
    ``label`` of a chord is its symbol, whatever its ``display_mode``: which of
    the two to show is the reader's choice (Felipe, 2026-10-27)."""
    names: list[tuple[str, str]] = []
    for c in comps:
        if c.kind != "chord":
            continue
        # not logged, as for positions: one lookup per chord
        rows = log.con.execute(
            "SELECT symbol, roman FROM chords WHERE component_id = ?", (c.id,)
        ).fetchall()
        if rows:
            names.append((rows[0][0] or "", rows[0][1] or ""))
    if not names:
        return {"symbol": None, "roman": None}
    return {
        "symbol": " → ".join(s for s, _ in names),
        "roman": " → ".join(r for _, r in names),
    }


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
        **_chord_names(log, [c for c, _, _ in targets]),
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
