"""Turn the parts of a TQL pattern into SQL and lanes.

Two jobs: :func:`resolve_lanes` says which lanes of a file an ``IN`` clause
names, and :func:`candidate_statement` writes the SELECT that finds the
components fitting one ``Unit`` of the query: its label, the timing
relations in its brackets (as ``EXISTS``) and its simple comparisons, positions
and lengths in bars and beats included (read from ``positions`` and through the
time map's SQL functions). Python builds the lanes and walks them, and tests the
conditions SQL does not take (:mod:`.relations`).
"""

from __future__ import annotations

import fnmatch
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from tilia_core import derived
from tilia_core.labels import fold, nfc

from . import sqlfuncs, syntax
from .lanes import BAR_KIND

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
DEFAULT_KINDS = ("hierarchy", "range", "marker")  # a query without IN: no bars
POINT_KINDS = ("marker", "beat")


@dataclass(frozen=True)
class LaneSpec:
    """A lane of one timeline: a hierarchy level, a range row, or all of a
    marker, chord, key or beat timeline's units."""

    timeline_id: str
    timeline: str
    kind: str  # hierarchy | range | marker | chord | key | beat | bar
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
        if self.kind == BAR_KIND:
            return f"{self.timeline} · bars"
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
            return _bar_lanes(con, file_id)
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


def on_bars(lane: syntax.Lane | None) -> bool:
    """Whether ``lane`` is the bars lane (``bars``, ``bar``, ``measures``,
    ``measure``), whose units no table of components holds."""
    return lane is not None and not lane.quoted and fold(lane.text.strip()) in BAR_WORDS


def _bar_lanes(con: sqlite3.Connection, file_id: str) -> list[LaneSpec]:
    """The bars lane of a file: one lane, on the timeline its time map reads,
    when the file has measures."""
    row = con.execute(
        "SELECT t.id, t.name FROM files f JOIN timelines t ON t.id = f.time_map "
        "WHERE f.id = ? AND EXISTS (SELECT 1 FROM measures m WHERE m.file_id = f.id)",
        (file_id,),
    ).fetchone()
    return [] if row is None else [LaneSpec(row[0], row[1], BAR_KIND)]


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
    chords or keys of ``specs`` by a label condition (``[label = V7]``) rather
    than as a step: that is not available yet."""
    if any(s.kind in ("chord", "key") for s in specs) and any(
        has_label_step(u) for u in units
    ):
        raise NotImplementedError(
            "a label condition on chords and keys is not available yet "
            "(write the chord as a step: V7 IN harmony)"
        )


def has_label_step(unit: syntax.Unit) -> bool:
    """Whether a bracket of ``unit`` matches a label as a step, other than ``*``."""
    return any(
        is_label_step(c) and c.value.kind != "any"  # type: ignore[union-attr]
        for c in unit.conds
    )


# --------------------------------------------------------------------------- #
# Candidate statements
# --------------------------------------------------------------------------- #
Resolve = Callable[[syntax.Lane], "list[LaneSpec]"]


class SqlBuilder:
    """The parameters of one statement, in the order their ``?`` appear, and
    the numbering that keeps the aliases of nested statements apart."""

    def __init__(self, resolve: Resolve | None = None, has_map: bool = True) -> None:
        self.params: list[Any] = []
        self.resolve = resolve
        self.has_map = has_map  # whether the file has a time map
        self._n = 0

    def alias(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def lanes(self, lane: syntax.Lane) -> list[LaneSpec]:
        if self.resolve is None:
            raise NotImplementedError("a relation needs the lanes of its file")
        return self.resolve(lane)


def is_label_step(cond: syntax.Cond) -> bool:
    """Whether ``cond`` is ``[label = verse]``: a label matched as a step."""
    return (
        isinstance(cond, syntax.Compare)
        and not cond.field.scope
        and cond.field.name == "label"
        and cond.op in ("=", "!=")
        and cond.value.kind in ("word", "string")
    )


def _category_test(lit: syntax.Literal, alias: str, params: list[Any]) -> str:
    head = fold(lit.text)
    if lit.sub:
        params.append(f"{head}.{fold(lit.sub)}")
        return f"{alias}.category = ?"
    params.extend((head, len(head) + 1, head + "."))
    return f"({alias}.category = ? OR substr({alias}.category, 1, ?) = ?)"


def _alt_sql(alt: syntax.Alt, comp: str, n: int, params: list[Any]) -> str:
    """One ``a/b/…`` on the component ``comp``. A chord is read as a chord and a
    key as a key (:func:`_harmony_sql`); any other component has its label
    tested (:func:`_label_sql`)."""
    lits = alt.lits
    if len(lits) == 1 and lits[0].kind == "any":
        return "(1)"
    harmony = _harmony_sql(alt, comp, params)
    label = _label_sql(alt, comp, n, params)
    return (
        f"(({comp}.kind IN ('chord', 'key') AND {harmony}) OR "
        f"({comp}.kind NOT IN ('chord', 'key') AND {label}))"
    )


REGEX_COLUMNS = ("roman", "symbol", "key", "custom_text")


def _harmony_sql(alt: syntax.Alt, comp: str, params: list[Any]) -> str:
    """The test that ``alt`` fits the chord or key ``comp`` (tql.md §5): a
    regular expression alone searches a chord's Roman numeral, symbol, key and
    custom text, or a key's name; any other literal is read as a chord or a key
    (``V/V`` and ``C/E`` as written, with their slash). A chord literal that is
    no chord, written in quotes, still matches a chord's own custom text."""
    lits = alt.lits
    if len(lits) == 1 and lits[0].kind == "regex":
        pattern = lits[0].text
        found = " OR ".join(f"x.{col} REGEXP ?" for col in REGEX_COLUMNS)
        params.extend([pattern] * len(REGEX_COLUMNS))
        chord = f"EXISTS (SELECT 1 FROM chords x WHERE x.component_id = {comp}.id AND ({found}))"
        params.append(pattern)
        key = f"EXISTS (SELECT 1 FROM keys x WHERE x.component_id = {comp}.id AND x.key REGEXP ?)"
        return (
            f"(({comp}.kind = 'chord' AND {chord}) OR ({comp}.kind = 'key' AND {key}))"
        )
    exact = len(lits) == 1 and lits[0].kind == "exact"
    text = nfc(lits[0].text if exact else alt.raw)
    chord = (
        "EXISTS (SELECT 1 FROM chords x LEFT JOIN keys y ON y.component_id = "
        f"x.key_id WHERE x.component_id = {comp}.id AND tql_chord(?, x.step, "
        "x.accidental, x.quality, x.inversion, x.applied_to, y.step, "
        "y.accidental, y.mode))"
    )
    params.append(text)
    if exact and isinstance(sqlfuncs.chord_spec(text), str):
        chord = (
            f"({chord} OR EXISTS (SELECT 1 FROM chords x WHERE "
            f"x.component_id = {comp}.id AND trim(x.custom_text) = ?))"
        )
        params.append(text.strip())
    params.append(text)
    key = (
        f"EXISTS (SELECT 1 FROM keys x WHERE x.component_id = {comp}.id AND "
        "tql_key(?, x.step, x.accidental, x.mode))"
    )
    return f"(({comp}.kind = 'chord' AND {chord}) OR ({comp}.kind = 'key' AND {key}))"


def harmony_problems(unit: syntax.Unit, kind: str) -> list[str]:
    """The warnings for the literals of ``unit`` that are read as chords
    (``kind`` ``chord``) or as keys (``key``) and are none."""
    out: list[str] = []
    for alt in unit.term.alts if unit.term is not None else ():
        lits = alt.lits
        if len(lits) == 1 and lits[0].kind in ("any", "regex"):
            continue
        if any(lit.kind == "regex" for lit in lits):
            out.append("a regular expression in a harmony lane must stand alone")
            continue
        text = nfc(
            lits[0].text if len(lits) == 1 and lits[0].kind == "exact" else alt.raw
        )
        spec = sqlfuncs.chord_spec(text) if kind == "chord" else sqlfuncs.key_spec(text)
        if isinstance(spec, str):
            out.append(f"{text!r} is not a {kind}: {spec}")
    return out


def _label_sql(alt: syntax.Alt, comp: str, n: int, params: list[Any]) -> str:
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
POSITION_COLUMNS = {
    "bar": "bar",
    "end_bar": "end_bar",
    "beat": "beat",
    "pass": "pass",
    "bar.count": "bar_count",
    "bar.beat_count": "bar_beat_count",
}  # the numeric position fields and the column of ``positions`` each reads
LENGTH_UNITS = ("bar", "beat")
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
    **{
        name: f"(SELECT p.{column} FROM positions p WHERE p.component_id = {{c}}.id)"
        for name, column in POSITION_COLUMNS.items()
    },
}


def compare_in_sql(cond: syntax.Compare) -> bool:
    """Whether SQL tests ``cond`` on one unit: a stored number (a position
    included) against a number or a range, a ``duration`` in bars or beats, or a
    colour against a colour, or either one's ``*``."""
    f, v = cond.field, cond.value
    if f.scope or f.index is not None or v.offset is not None:
        return False
    if v.unit:
        return (
            f.name == "duration"
            and v.unit in LENGTH_UNITS
            and v.kind in ("number", "range")
            and (v.kind == "range" or cond.op in ORDER_OPS)
        )
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
    elif v.unit:
        col = f"tql_length({comp}.file_id, {comp}.start, {comp}.\"end\", '{v.unit}')"
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
    if cond_unknowable(cond):  # no value is no match, ``NOT`` included
        return f"COALESCE(({'NOT ' if cond.negate else ''}({test})), 0)"
    test = f"COALESCE(({test}), 0)"
    return f"NOT {test}" if cond.negate else test


def cond_unknowable(cond: syntax.Compare) -> bool:
    """Whether a unit can lack what ``cond`` compares because of the file (a
    position or a length in bars or beats needs the time map): the condition
    then holds of no unit, ``NOT`` included, rather than of every one."""
    f, v = cond.field, cond.value
    if v.kind == "any":
        return False
    return bool(v.unit) or (not f.scope and f.name in POSITION_FIELDS)


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
        if len(alts) > 1:
            # callers AND this with the file and lane tests
            test = f"({test})"
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
    unit: syntax.Unit,
    file_id: str,
    resolve: Resolve | None = None,
    has_map: bool = True,
) -> tuple[str, list[Any]]:
    """``(sql, parameters)`` selecting the ids of the components of ``file_id``
    that fit ``unit`` (tql.md §5), bound with ``?``: its label and the timing
    relations in its brackets, and the stored numbers and colours it compares.
    ``resolve`` names the lanes of an ``IN`` clause; ``has_map`` says whether the
    file has a time map, without which a relation limited in bars or beats holds
    of nothing."""
    if unit.term is None and not unit.conds:
        raise NotImplementedError(
            "a unit without a label is not available yet (conditions)"
        )
    bld = SqlBuilder(resolve, has_map)
    bld.params.append(file_id)
    test = unit_test(unit, "c", bld)
    sql = f"SELECT c.id FROM components c WHERE c.file_id = ? AND ({test})"
    return sql, bld.params
