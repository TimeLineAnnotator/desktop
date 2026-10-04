"""Turn the parts of a TQL pattern into SQL and lanes.

Two jobs: :func:`resolve_lanes` says which lanes of a file an ``IN`` clause
names, and :func:`candidate_statement` writes the SELECT that finds the
components fitting one ``Unit`` of the query: its label, the timing
relations in its brackets (as ``EXISTS``) and its simple comparisons. Python builds the lanes and walks
them, and tests the conditions SQL does not take (:mod:`.relations`).
"""

from __future__ import annotations

import fnmatch
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from tilia_core import derived
from tilia_core.labels import fold, nfc

from . import syntax

ROLE_ALIASES = {"cadence": "cadences", "timemap": "time_map"}
BUILTIN_ROLES = ("form", "cadences", "harmony", "keys", "time_map")
KIND_WORDS = {
    "hierarchy": "hierarchy",
    "hierarchies": "hierarchy",
    "marker": "marker",
    "markers": "marker",
    "range": "range",
    "ranges": "range",
    "beat": "beat",
    "beats": "beat",
    "chord": "chord",
    "chords": "chord",
    "key": "key",
    "keys": "key",
}
BAR_WORDS = ("bar", "bars", "measure", "measures")
DEFAULT_KINDS = ("hierarchy", "range", "marker")
POINT_KINDS = ("marker", "beat")


@dataclass(frozen=True)
class LaneSpec:
    """A lane of one timeline: a hierarchy level, a range row, or all of a
    marker, chord, key or beat timeline's units."""

    timeline_id: str
    timeline: str
    kind: str  # hierarchy | range | marker | chord | key | beat
    level: int | None = None
    row_id: str | None = None
    row: str | None = None

    @property
    def point(self) -> bool:
        return self.kind in POINT_KINDS

    @property
    def description(self) -> str:
        if self.level is not None:
            return f"{self.timeline} · level {self.level}"
        if self.row is not None:
            return f"{self.timeline} · {self.row}"
        if self.kind in ("chord", "key"):
            return f"{self.timeline} · {self.kind}s"
        return self.timeline


# --------------------------------------------------------------------------- #
# Lanes
# --------------------------------------------------------------------------- #
def name_pattern(lane: syntax.Lane) -> str:
    """The ``fnmatch`` pattern for a lane name: a quoted name keeps its case, a
    bare word ignores it. ``*`` is the only wildcard."""
    text = lane.text.strip()
    text = text if lane.quoted else fold(text)
    text = nfc(text).replace("[", "[[]").replace("?", "[?]")
    return text


def _lanes_of(
    con: sqlite3.Connection, tl: tuple[Any, ...], kinds: tuple[str, ...] | None
) -> list[LaneSpec]:
    """The lanes of one timeline row ``(id, kind, name, ...)``, those of the
    given lane ``kinds`` only (None: all)."""
    tid, kind, name = tl[0], tl[1], tl[2]
    out: list[LaneSpec] = []
    if kind == "hierarchy":
        rows = con.execute(
            "SELECT DISTINCT h.level FROM hierarchies h "
            "JOIN components c ON c.id = h.component_id "
            "WHERE c.timeline_id = ? AND h.level IS NOT NULL ORDER BY h.level",
            (tid,),
        ).fetchall()
        out = [LaneSpec(tid, name, "hierarchy", level=r[0]) for r in rows]
    elif kind == "range":
        rows = con.execute(
            "SELECT DISTINCT r.row_id, r.row FROM ranges r "
            "JOIN components c ON c.id = r.component_id "
            "WHERE c.timeline_id = ? ORDER BY r.row_id",
            (tid,),
        ).fetchall()
        out = [LaneSpec(tid, name, "range", row_id=r[0], row=r[1]) for r in rows]
    elif kind == "marker":
        out = [LaneSpec(tid, name, "marker")]
    elif kind == "harmony":
        out = [LaneSpec(tid, name, "chord"), LaneSpec(tid, name, "key")]
    elif kind == "beat":
        out = [LaneSpec(tid, name, "beat")]
    if kinds is not None:
        out = [s for s in out if s.kind in kinds]
    return out


def resolve_lanes(
    con: sqlite3.Connection, file_id: str, lane: syntax.Lane | None
) -> list[LaneSpec]:
    """The lanes of file ``file_id`` that ``IN lane`` names (tql.md §4); with
    no ``IN``, every hierarchy level, range row and marker timeline."""
    timelines = con.execute(
        "SELECT id, kind, name, name_folded, role FROM timelines "
        "WHERE file_id = ? ORDER BY ordinal",
        (file_id,),
    ).fetchall()
    if lane is None:
        return [s for tl in timelines for s in _lanes_of(con, tl, DEFAULT_KINDS)]

    word = fold(lane.text.strip())
    if not lane.quoted:
        word = ROLE_ALIASES.get(word, word)
        if word in BAR_WORDS:
            raise NotImplementedError("the bars lane is not available yet")
        stored = {tl[4] for tl in timelines if tl[4]}
        if word in BUILTIN_ROLES or word in stored:
            return _role_lanes(con, file_id, timelines, word)
        if word in KIND_WORDS:
            kind = KIND_WORDS[word]
            return [s for tl in timelines for s in _lanes_of(con, tl, (kind,))]

    pattern = name_pattern(lane)
    out: list[LaneSpec] = []
    for tl in timelines:
        name = tl[3] if not lane.quoted else nfc(tl[2])
        if fnmatch.fnmatchcase(name, pattern):
            out.extend(_lanes_of(con, tl, None))
        elif tl[1] == "range":
            for spec in _lanes_of(con, tl, None):
                row = fold(spec.row or "") if not lane.quoted else nfc(spec.row or "")
                if fnmatch.fnmatchcase(row, pattern):
                    out.append(spec)
    return out


def _role_lanes(
    con: sqlite3.Connection,
    file_id: str,
    timelines: list[tuple[Any, ...]],
    role: str,
) -> list[LaneSpec]:
    """The lanes of the timelines with ``role``. A built-in role on its own kind
    of timeline takes only the lane it is about (the chords of a harmony
    timeline, not its keys); any other role takes the whole timeline."""
    time_map = con.execute(
        "SELECT time_map FROM files WHERE id = ?", (file_id,)
    ).fetchone()
    time_map_id = time_map[0] if time_map else None
    out: list[LaneSpec] = []
    for tl in timelines:
        tid, kind, stored = tl[0], tl[1], tl[4]
        if role == "harmony" and kind == "harmony" and stored in ("harmony", "keys"):
            out.extend(_lanes_of(con, tl, ("chord",)))
        elif role == "keys" and kind == "harmony" and stored in ("harmony", "keys"):
            out.extend(_lanes_of(con, tl, ("key",)))
        elif role == "time_map" and kind == "beat" and tid == time_map_id:
            out.extend(_lanes_of(con, tl, None))
        elif stored == role:
            out.extend(_lanes_of(con, tl, None))
    return out


def timeline_lanes(con: sqlite3.Connection, timeline_id: str) -> list[LaneSpec]:
    """Every lane of one timeline."""
    tl = con.execute(
        "SELECT id, kind, name FROM timelines WHERE id = ?", (timeline_id,)
    ).fetchone()
    return [] if tl is None else _lanes_of(con, tl, None)


def check_labels(specs: Iterable[LaneSpec], units: Iterable[syntax.Unit]) -> None:
    """Raise NotImplementedError when ``units`` would be matched against the
    chords or keys of ``specs`` by anything but ``*``: that is for the harmony
    part."""
    if any(s.kind in ("chord", "key") for s in specs) and not all(
        is_wildcard(u) for u in units
    ):
        raise NotImplementedError(
            "labels in chords and keys lanes are for the harmony part"
        )


# --------------------------------------------------------------------------- #
# Candidate statements
# --------------------------------------------------------------------------- #
Resolve = Callable[[syntax.Lane], "list[LaneSpec]"]


class SqlBuilder:
    """The parameters of one statement, in the order their ``?`` appear, and
    the numbering that keeps the aliases of nested statements apart."""

    def __init__(self, resolve: Resolve | None = None) -> None:
        self.params: list[Any] = []
        self.resolve = resolve
        self._n = 0

    def alias(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def lanes(self, lane: syntax.Lane) -> list[LaneSpec]:
        if self.resolve is None:
            raise NotImplementedError("a relation needs the lanes of its file")
        return self.resolve(lane)


def is_label_step(cond: syntax.Cond) -> bool:
    """Whether ``cond`` is ``[label = verse]``: a label matched as a step, which
    chords and keys do not take until the harmony part."""
    return (
        isinstance(cond, syntax.Compare)
        and not cond.field.scope
        and cond.field.name == "label"
        and cond.op in ("=", "!=")
        and cond.value.kind in ("word", "string")
    )


def is_wildcard(unit: syntax.Unit) -> bool:
    """Whether ``unit`` is a plain ``*``, the one literal that fits a chord or
    a key until the harmony part lands."""
    term = unit.term
    return (
        term is not None
        and not any(is_label_step(c) for c in unit.conds)
        and not term.negate
        and len(term.alts) == 1
        and len(term.alts[0].lits) == 1
        and term.alts[0].lits[0].kind == "any"
    )


def _category_test(lit: syntax.Literal, alias: str, params: list[Any]) -> str:
    head = fold(lit.text)
    if lit.sub:
        params.append(f"{head}.{fold(lit.sub)}")
        return f"{alias}.category = ?"
    params.extend((head, len(head) + 1, head + "."))
    return f"({alias}.category = ? OR substr({alias}.category, 1, ?) = ?)"


def _alt_sql(alt: syntax.Alt, comp: str, n: int, params: list[Any]) -> str:
    """One ``a/b/…``: every literal on the one component ``comp``. Words need
    their own category row each; the other literals test the label."""
    tests: list[str] = []
    words = [lit for lit in alt.lits if lit.kind == "word"]
    aliases = [f"k{comp}{n}_{i}" for i in range(len(words))]
    word_tests: list[str] = []
    for lit, alias in zip(words, aliases, strict=True):
        word_tests.append(_category_test(lit, alias, params))
    if words:
        joins = " AND ".join(f"{a}.component_id = {comp}.id" for a in aliases)
        distinct = "".join(
            f" AND {a}.rowid <> {b}.rowid"
            for i, a in enumerate(aliases)
            for b in aliases[i + 1 :]
        )
        tables = ", ".join(f"categories {a}" for a in aliases)
        tests.append(
            f"EXISTS (SELECT 1 FROM {tables} WHERE {joins}{distinct} AND "
            + " AND ".join(word_tests)
            + ")"
        )
    for lit in alt.lits:
        if lit.kind == "exact":
            tests.append(f"COALESCE(trim({comp}.label), '') = ?")
            params.append(nfc(lit.text))
        elif lit.kind == "regex":
            tests.append(f"({comp}.label IS NOT NULL AND {comp}.label REGEXP ?)")
            params.append(lit.text)
        elif lit.kind == "any":
            tests.append("1")
    return "(" + " AND ".join(tests) + ")"


POSITION_FIELDS = (
    "bar",
    "end_bar",
    "beat",
    "pass",
    "bar.count",
    "bar.label",
    "bar.beat_count",
)
ORDER_OPS = {"=": "=", "!=": "<>", "<": "<", ">": ">", "<=": "<=", ">=": ">="}
STORED_NUMBERS = {
    "start": "{c}.start",
    "time": "{c}.start",
    "end": '{c}."end"',
    "duration": '({c}."end" - {c}.start)',
    "level": "(SELECT h.level FROM hierarchies h WHERE h.component_id = {c}.id)",
    "depth": "(SELECT h.depth FROM hierarchies h WHERE h.component_id = {c}.id)",
    "inversion": "(SELECT x.inversion FROM chords x WHERE x.component_id = {c}.id)",
    "applied_to": "(SELECT x.applied_to FROM chords x WHERE x.component_id = {c}.id)",
}


def later(cond: syntax.Cond) -> None:
    """Raise NotImplementedError for a condition that needs the time map or the
    piece's length: positions, percentages, lengths in bars or beats, distances."""
    if isinstance(cond, syntax.Downbeat):
        raise NotImplementedError("downbeat is not available yet (positions)")
    if not isinstance(cond, syntax.Compare):
        return
    value = cond.value
    sides = [cond.field] + ([value.value] if value.kind == "ref" else [])
    for side in sides:
        if not side.scope and side.name in POSITION_FIELDS:
            raise NotImplementedError(
                f"{side.name} is a position: positions are not available yet "
                "(positions)"
            )
    if value.unit:
        raise NotImplementedError(
            "percentages and lengths in bars or beats are not available yet "
            "(positions)"
        )
    if value.offset is not None:
        raise NotImplementedError(
            "a distance added to a time is not available yet (positions)"
        )


def compare_in_sql(cond: syntax.Compare) -> bool:
    """Whether SQL tests ``cond`` on one unit: a stored number against a number
    or a range, or a colour against a colour, or either one's ``*``."""
    f, v = cond.field, cond.value
    if f.scope or f.index is not None or v.unit or v.offset is not None:
        return False
    if f.name in STORED_NUMBERS:
        if v.kind == "number":
            return cond.op in ORDER_OPS
        return v.kind in ("range", "any")
    if f.name == "color":
        return v.kind == "any" or (
            v.kind in ("number", "word", "string") and cond.op in ("=", "!=")
        )
    return False


def compare_sql(cond: syntax.Compare, comp: str, bld: SqlBuilder) -> str:
    """The condition ``cond`` (see :func:`compare_in_sql`) on component ``comp``.
    A unit without the value never satisfies a comparison, ``NOT`` included, as in
    Python: the test is 0 then, not NULL."""
    f, v = cond.field, cond.value
    if f.name == "color":
        col = f"tql_color({comp}.color)"
    else:
        col = STORED_NUMBERS[f.name].format(c=comp)
    if v.kind == "any":
        empty = (
            f"({col} IS NULL OR {col} = '')" if f.name == "color" else f"{col} IS NULL"
        )
        test = empty if cond.op == "!=" else f"NOT {empty}"
    elif v.kind == "range":
        lo, hi = v.value
        bld.params.extend((lo - 1e-9, hi + 1e-9))
        between = "NOT BETWEEN" if cond.op == "!=" else "BETWEEN"
        test = f"{col} {between} ? AND ?"
    elif f.name == "color":
        raw = v.raw if v.kind == "number" else v.value
        bld.params.append(derived.color(str(raw)))
        test = f"{col} {ORDER_OPS[cond.op]} ?"
    else:
        bld.params.append(float(v.value))
        test = f"{col} {ORDER_OPS[cond.op]} ?"
    test = f"COALESCE(({test}), 0)"
    return f"NOT {test}" if cond.negate else test


def split_conds(
    unit: syntax.Unit,
) -> tuple[list[syntax.RelCond | syntax.Compare], list[syntax.Cond]]:
    """The bracket conditions of ``unit`` that SQL tests (stored numbers and
    colours, and timing relations to another lane, whose target SQL tests in
    full) and those Python tests."""
    from . import relations  # relations imports this module

    in_sql: list[syntax.RelCond | syntax.Compare] = []
    in_python: list[syntax.Cond] = []
    for cond in unit.conds:
        later(cond)
        if isinstance(cond, syntax.Compare) and compare_in_sql(cond):
            in_sql.append(cond)
        elif isinstance(cond, syntax.RelCond) and relations.in_sql(cond.relation):
            in_sql.append(cond)
        else:
            in_python.append(cond)
    return in_sql, in_python


def needs_python(unit: syntax.Unit) -> bool:
    """Whether some bracket condition of ``unit`` is left to Python."""
    return bool(split_conds(unit)[1])


def lane_test(specs: list[LaneSpec], comp: str, bld: SqlBuilder) -> str:
    """The test that component ``comp`` lies in one of the lanes ``specs``."""
    groups: dict[tuple[str, str], list[LaneSpec]] = {}
    for s in specs:
        groups.setdefault((s.timeline_id, s.kind), []).append(s)
    tests: list[str] = []
    for (tid, kind), group in groups.items():
        bld.params.extend((tid, kind))
        test = f"{comp}.timeline_id = ? AND {comp}.kind = ?"
        if kind == "hierarchy":
            marks = ", ".join("?" for _ in group)
            bld.params.extend(s.level for s in group)
            test += (
                " AND EXISTS (SELECT 1 FROM hierarchies h WHERE "
                f"h.component_id = {comp}.id AND h.level IN ({marks}))"
            )
        elif kind == "range":
            marks = ", ".join("?" for _ in group)
            bld.params.extend(s.row_id for s in group)
            test += (
                " AND EXISTS (SELECT 1 FROM ranges r WHERE "
                f"r.component_id = {comp}.id AND r.row_id IN ({marks}))"
            )
        tests.append(f"({test})")
    return "(" + " OR ".join(tests) + ")" if tests else "0"


def unit_test(unit: syntax.Unit, comp: str, bld: SqlBuilder) -> str:
    """The test that component ``comp`` fits ``unit``: its label, and the timing
    relations among its brackets as ``EXISTS``."""
    from . import relations  # relations imports this module

    in_sql, _ = split_conds(unit)
    term = unit.term
    if term is None:
        test = "1"
    else:
        alts = [_alt_sql(alt, comp, n, bld.params) for n, alt in enumerate(term.alts)]
        test = " OR ".join(alts)
        if term.negate:
            test = f"NOT ({test})"
    if not in_sql:
        return test
    parts = [f"({test})"] + [
        compare_sql(c, comp, bld)
        if isinstance(c, syntax.Compare)
        else relations.exists_sql(c.relation, comp, bld)
        for c in in_sql
    ]
    return " AND ".join(parts)


def candidate_statement(
    unit: syntax.Unit, file_id: str, resolve: Resolve | None = None
) -> tuple[str, list[Any]]:
    """``(sql, parameters)`` selecting the ids of the components of ``file_id``
    that fit ``unit`` (tql.md §5), bound with ``?``: its label and the timing
    relations in its brackets, and the stored numbers and colours it compares.
    ``resolve`` names the lanes of an ``IN`` clause."""
    if unit.term is None and not unit.conds:
        raise NotImplementedError(
            "a unit without a label is not available yet (conditions)"
        )
    bld = SqlBuilder(resolve)
    bld.params.append(file_id)
    test = unit_test(unit, "c", bld)
    sql = f"SELECT c.id FROM components c WHERE c.file_id = ? AND ({test})"
    return sql, bld.params
