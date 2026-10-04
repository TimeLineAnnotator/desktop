"""Turn the parts of a TQL sequence pattern into SQL and lanes.

Two jobs: :func:`resolve_lanes` says which lanes of a file an ``IN`` clause
names, and :func:`candidate_statement` writes the SELECT that finds the
components fitting one ``Unit`` of the query. Python builds the lanes and walks
them; SQL only picks each unit's candidates.
"""

from __future__ import annotations

import fnmatch
import sqlite3
from dataclasses import dataclass
from typing import Any

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
def _name_pattern(lane: syntax.Lane) -> str:
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

    pattern = _name_pattern(lane)
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


# --------------------------------------------------------------------------- #
# Candidate statements
# --------------------------------------------------------------------------- #
def is_wildcard(unit: syntax.Unit) -> bool:
    """Whether ``unit`` is a plain ``*``, the one literal that fits a chord or
    a key until the harmony part lands."""
    term = unit.term
    return (
        term is not None
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


def _alt_sql(alt: syntax.Alt, n: int, params: list[Any]) -> str:
    """One ``a/b/…``: every literal on the one component. Words need their own
    category row each; the other literals test the label."""
    tests: list[str] = []
    words = [lit for lit in alt.lits if lit.kind == "word"]
    aliases = [f"k{n}_{i}" for i in range(len(words))]
    word_tests: list[str] = []
    for lit, alias in zip(words, aliases, strict=True):
        word_tests.append(_category_test(lit, alias, params))
    if words:
        joins = " AND ".join(f"{a}.component_id = c.id" for a in aliases)
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
            tests.append("COALESCE(trim(c.label), '') = ?")
            params.append(nfc(lit.text))
        elif lit.kind == "regex":
            tests.append("(c.label IS NOT NULL AND c.label REGEXP ?)")
            params.append(lit.text)
        elif lit.kind == "any":
            tests.append("1")
    return "(" + " AND ".join(tests) + ")"


def candidate_statement(unit: syntax.Unit, file_id: str) -> tuple[str, list[Any]]:
    """``(sql, parameters)`` selecting the ids of the components of ``file_id``
    that fit ``unit`` (tql.md §5), bound with ``?``."""
    if unit.conds:
        raise NotImplementedError(
            "bracket conditions are not available yet (conditions)"
        )
    term = unit.term
    if term is None:
        raise NotImplementedError(
            "a unit without a label is not available yet (conditions)"
        )
    params: list[Any] = [file_id]
    alts = [_alt_sql(alt, n, params) for n, alt in enumerate(term.alts)]
    test = " OR ".join(alts)
    if term.negate:
        test = f"NOT ({test})"
    sql = f"SELECT c.id FROM components c WHERE c.file_id = ? AND ({test})"
    return sql, params
