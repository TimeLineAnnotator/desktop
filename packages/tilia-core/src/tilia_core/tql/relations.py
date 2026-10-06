"""Relations between units (tql.md §8): ``DURING``, ``CONTAINS``, ``STARTS WITH``
and the rest, in the sentence form (``PAC IN cadences DURING ST IN form``) and
in brackets (``ST[ENDS WITH PAC IN cadences]``).

Two kinds of relation, and the line between them decides what runs where:

* **Timing relations** (``DURING``, ``CONTAINS``, ``SAME START``, ``SAME END``,
  ``SAME``, ``OVERLAPS``, ``BEFORE``, ``AFTER``, ``STARTS BEFORE``,
  ``STARTS AFTER``) between a unit and one unit of another lane are SQL: a join
  in the sentence form, an ``EXISTS`` in brackets, both with the tolerance
  written in. :func:`timing_sql` writes the test, :func:`join_statement` and
  :func:`exists_sql` put it in a statement.
* **Order and hierarchy** (``STARTS WITH``, ``ENDS WITH``, ``CONSISTS OF``,
  ``STARTS``, ``ENDS``, a target of several steps, children, and every relation
  without ``IN``, which looks in the unit's own timeline) is Python, on the
  lanes of a file: :class:`Scope`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from . import compile as tql_compile
from . import syntax
from .compile import LaneSpec, SqlBuilder
from .lanes import project
from .result import Component, Match
from .sequences import Item, find_runs, slots_of

TOLERANCE = 0.1  # s: two times this close are the same time (tql.md §8)
TIMING = (
    "DURING",
    "CONTAINS",
    "SAME_START",
    "SAME_END",
    "SAME",
    "OVERLAPS",
    "BEFORE",
    "AFTER",
    "STARTS_BEFORE",
    "STARTS_AFTER",
)
ORDER_IN_TIME = ("BEFORE", "AFTER", "STARTS_BEFORE", "STARTS_AFTER")
SEQUENCE_MODES = {
    "CONTAINS": "any",
    "STARTS_WITH": "start",
    "ENDS_WITH": "end",
    "CONSISTS_OF": "full",
}
POINT_KINDS = ("marker", "beat")
SLACK = 1e-9  # s: float noise in a limit on a gap


# --------------------------------------------------------------------------- #
# Tolerance and distance
# --------------------------------------------------------------------------- #
def seconds(within: syntax.Within) -> float:
    """``within`` in seconds; bars and beats need the time map (a later part)."""
    if within.unit == "s":
        return within.amount
    if within.unit == "ms":
        return within.amount / 1000
    raise NotImplementedError("WITHIN in bars and beats is not available yet (within)")


@dataclass(frozen=True)
class Metric:
    """Tolerance and distance limit of one relation test. ``tol`` makes times
    equal; ``gap``, when set, limits the distance ``BEFORE``, ``AFTER`` and the
    ``STARTS`` order relations cross."""

    tol: float = TOLERANCE
    gap: float | None = None

    def eq(self, a: float, b: float) -> bool:
        return abs(a - b) <= self.tol

    def le(self, a: float, b: float) -> bool:
        return a <= b + self.tol

    def lt(self, a: float, b: float) -> bool:
        return a < b - self.tol

    def within_gap(self, a: float, b: float) -> bool:
        return self.gap is None or b - a <= self.gap + SLACK

    def inside(self, a: Component, b: Component) -> bool:
        """``a`` lies in ``b``. Points count on the edges; chords and keys belong
        where they begin (half-open), so the next unit's first chord is not this
        unit's last."""
        if a.id == b.id:
            return False
        if a.kind in ("chord", "key"):
            return b.start - self.tol <= a.start < b.end - self.tol
        return b.start - self.tol <= a.start and a.end <= b.end + self.tol


def metric_of(rel: syntax.Relation) -> Metric:
    """The tolerance of ``rel``: 0.1 s, or its ``WITHIN`` (for the order in time,
    the largest gap instead)."""
    if rel.within is None:
        return Metric()
    amount = seconds(rel.within)
    if rel.rel in ORDER_IN_TIME:
        return Metric(TOLERANCE, amount)
    return Metric(amount)


def is_point(comp: Component) -> bool:
    return comp.kind in POINT_KINDS


def timing(r: str, a: Component, b: Component, m: Metric) -> bool:
    """Whether timing relation ``r`` holds with ``a`` on the left (the Python
    twin of :func:`timing_sql`)."""
    if a.id == b.id:
        return False
    if r == "DURING":
        return m.inside(a, b)
    if r == "CONTAINS":
        return m.inside(b, a)
    if r == "SAME_START":
        return m.eq(a.start, b.start)
    if r == "SAME_END":
        return m.eq(a.end, b.end)
    if r == "SAME":
        return m.eq(a.start, b.start) and m.eq(a.end, b.end)
    if r == "OVERLAPS":
        if is_point(a) and is_point(b):
            return m.eq(a.start, b.start)
        if is_point(a):
            return m.le(b.start, a.start) and m.le(a.start, b.end)
        if is_point(b):
            return m.le(a.start, b.start) and m.le(b.start, a.end)
        return m.lt(a.start, b.end) and m.lt(b.start, a.end)
    if r == "BEFORE":
        return m.le(a.end, b.start) and m.within_gap(a.end, b.start)
    if r == "AFTER":
        return m.le(b.end, a.start) and m.within_gap(b.end, a.start)
    if r == "STARTS_BEFORE":  # starts only, whether or not the other has ended
        return m.lt(a.start, b.start) and m.within_gap(a.start, b.start)
    if r == "STARTS_AFTER":
        return m.lt(b.start, a.start) and m.within_gap(b.start, a.start)
    raise ValueError(f"{r} is not a timing relation")


# --------------------------------------------------------------------------- #
# SQL
# --------------------------------------------------------------------------- #
def simple_target(seq: syntax.Seq) -> syntax.Unit | None:
    """The one unit ``seq`` is, or None when it is a sequence, a repetition or
    a group."""
    if len(seq.steps) != 1:
        return None
    step = seq.steps[0]
    if step.lo != 1 or step.hi != 1 or not isinstance(step.item, syntax.Unit):
        return None
    return step.item


def joins(rel: syntax.Relation) -> bool:
    """Whether the sentence form of ``rel`` is a join: a timing relation to one
    unit of a lane named by ``IN``."""
    return (
        rel.rel in TIMING
        and rel.lane is not None
        and simple_target(rel.target) is not None
    )


def in_sql(rel: syntax.Relation) -> bool:
    """Whether ``rel``, as a bracket condition, is an ``EXISTS``: it is a join
    whose target SQL tests in full (nothing of it is left to Python)."""
    target = simple_target(rel.target)
    return joins(rel) and target is not None and not tql_compile.needs_python(target)


def _inside_sql(a: str, b: str, t: str) -> str:
    return (
        f"({b}.start - {t} <= {a}.start AND CASE WHEN {a}.kind IN ('chord', 'key') "
        f'THEN {a}.start < {b}."end" - {t} ELSE {a}."end" <= {b}."end" + {t} END)'
    )


def timing_sql(rel: syntax.Relation, a: str, b: str) -> str:
    """The test that timing relation ``rel`` holds between the components
    aliased ``a`` (left) and ``b``, the tolerance written as a literal; the SQL
    twin of :func:`timing`."""
    m = metric_of(rel)
    t = repr(m.tol)
    pa = f"{a}.kind IN ('marker', 'beat')"
    pb = f"{b}.kind IN ('marker', 'beat')"
    a_end, b_end = f'{a}."end"', f'{b}."end"'

    def gap(lo: str, hi: str) -> str:
        return "" if m.gap is None else f" AND {hi} - {lo} <= {m.gap!r} + {SLACK!r}"

    r = rel.rel
    if r == "DURING":
        return _inside_sql(a, b, t)
    if r == "CONTAINS":
        return _inside_sql(b, a, t)
    if r == "SAME_START":
        return f"abs({a}.start - {b}.start) <= {t}"
    if r == "SAME_END":
        return f'abs({a}."end" - {b}."end") <= {t}'
    if r == "SAME":
        return (
            f'(abs({a}.start - {b}.start) <= {t} AND abs({a}."end" - {b}."end") <= {t})'
        )
    if r == "OVERLAPS":
        return (
            f"(CASE WHEN {pa} AND {pb} THEN abs({a}.start - {b}.start) <= {t} "
            f'WHEN {pa} THEN {b}.start <= {a}.start + {t} AND {a}.start <= {b}."end" + {t} '
            f'WHEN {pb} THEN {a}.start <= {b}.start + {t} AND {b}.start <= {a}."end" + {t} '
            f'ELSE {a}.start < {b}."end" - {t} AND {b}.start < {a}."end" - {t} END)'
        )
    if r == "BEFORE":
        return f"({a_end} <= {b}.start + {t}{gap(a_end, f'{b}.start')})"
    if r == "AFTER":
        return f"({b_end} <= {a}.start + {t}{gap(b_end, f'{a}.start')})"
    if r == "STARTS_BEFORE":
        return f"({a}.start < {b}.start - {t}{gap(f'{a}.start', f'{b}.start')})"
    if r == "STARTS_AFTER":
        return f"({b}.start < {a}.start - {t}{gap(f'{b}.start', f'{a}.start')})"
    raise ValueError(f"{r} is not a timing relation")


def exists_sql(rel: syntax.Relation, comp: str, bld: SqlBuilder) -> str:
    """The bracket condition ``rel`` on component ``comp`` as ``EXISTS`` (or
    ``NOT EXISTS``): a unit of the target lane in that timing relation to it."""
    assert rel.lane is not None
    target = simple_target(rel.target)
    assert target is not None
    specs = bld.lanes(rel.lane)
    tql_compile.check_labels(specs, [target])
    if not specs:
        return "1" if rel.negate else "0"
    other = bld.alias("x")
    inner = (
        f"{other}.file_id = {comp}.file_id AND {other}.id <> {comp}.id AND "
        f"{timing_sql(rel, comp, other)} AND "
        f"{tql_compile.lane_test(specs, other, bld)} AND "
        f"{tql_compile.unit_test(target, other, bld)}"
    )
    found = f"EXISTS (SELECT 1 FROM components {other} WHERE {inner})"
    return f"NOT {found}" if rel.negate else found


def join_statement(
    left: syntax.Unit,
    rel: syntax.Relation,
    left_specs: list[LaneSpec],
    right_specs: list[LaneSpec],
    file_id: str,
    resolve: tql_compile.Resolve,
) -> tuple[str, list[Any]]:
    """``(sql, parameters)`` of the sentence form of a timing relation: the
    left unit's candidates joined with the target's, each in its lanes."""
    target = simple_target(rel.target)
    assert target is not None
    bld = SqlBuilder(resolve)
    bld.params.append(file_id)
    where = (
        f"a.file_id = ? AND {tql_compile.lane_test(left_specs, 'a', bld)} AND "
        f"{tql_compile.lane_test(right_specs, 'b', bld)} AND "
        f"{tql_compile.unit_test(left, 'a', bld)} AND "
        f"{tql_compile.unit_test(target, 'b', bld)}"
    )
    sql = (
        "SELECT a.id, a.timeline_id, b.id, b.timeline_id "
        "FROM components a JOIN components b ON "
        f"a.file_id = b.file_id AND a.id <> b.id AND {timing_sql(rel, 'a', 'b')} "
        f'WHERE {where} ORDER BY a.start, a."end", a.id, b.start, b."end", b.id'
    )
    return sql, bld.params


# --------------------------------------------------------------------------- #
# Python: lanes, order and hierarchy
# --------------------------------------------------------------------------- #
class Log(Protocol):
    """What :class:`Scope` runs statements with (the engine's statement log)."""

    con: sqlite3.Connection

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[Any]:
        ...


def units_of(seq: syntax.Seq) -> Iterator[syntax.Unit]:
    """Every ``Unit`` node of ``seq``, groups included."""
    for st in seq.steps:
        if isinstance(st.item, syntax.Group):
            for option in st.item.options:
                yield from units_of(option)
        else:
            yield st.item


def _single(seq: syntax.Seq) -> syntax.Unit:
    step = seq.steps[0]
    if len(seq.steps) != 1 or not isinstance(step.item, syntax.Unit):
        raise NotImplementedError("a sequence is not available on this relation")
    return step.item


class Scope:
    """One file as the relations read it: its timelines' components, the lanes
    built from them, the hierarchy's parents, and the components each unit of
    the query fits. Everything is loaded when first asked for."""

    def __init__(self, log: Log, file_id: str) -> None:
        self.log = log
        self.file_id = file_id
        self._timelines: dict[str, list[Component]] = {}
        self._by_id: dict[str, Component] = {}
        self._row_id: dict[str, str | None] = {}
        self._parent_id: dict[str, str | None] = {}
        self._children: dict[str, list[Component]] = {}
        self._loaded_all = False
        self._lanes: dict[tuple[str, bool], list[LaneSpec]] = {}
        self._own: dict[str, list[LaneSpec]] = {}
        self._items: dict[LaneSpec, list[Item]] = {}
        self._fit: dict[int, frozenset[str]] = {}
        self._keep: list[Any] = []  # units made here, kept so their ids stay theirs

    # -- components ---------------------------------------------------------- #
    def timeline(self, timeline_id: str) -> list[Component]:
        """Every component of one timeline, in time order."""
        comps = self._timelines.get(timeline_id)
        if comps is not None:
            return comps
        rows = self.log.execute(
            'SELECT c.id, c.timeline_id, c.kind, c.label, c.start, c."end", h.level, '
            "r.row, r.row_id, h.parent_id FROM components c "
            "LEFT JOIN hierarchies h ON h.component_id = c.id "
            "LEFT JOIN ranges r ON r.component_id = c.id "
            "WHERE c.file_id = ? AND c.timeline_id = ? "
            'ORDER BY c.start, c."end", c.id',
            (self.file_id, timeline_id),
        )
        comps = []
        for r in rows:
            comp = Component(
                r[0], self.file_id, r[1], r[2], r[3] or "", r[4], r[5], r[6], r[7]
            )
            comps.append(comp)
            self._by_id[comp.id] = comp
            self._row_id[comp.id] = r[8]
            self._parent_id[comp.id] = r[9]
            if r[9] is not None:
                self._children.setdefault(r[9], []).append(comp)
        self._timelines[timeline_id] = comps
        return comps

    def component(self, comp_id: str, timeline_id: str) -> Component:
        self.timeline(timeline_id)
        return self._by_id[comp_id]

    def _load_all(self) -> None:
        if not self._loaded_all:
            rows = self.log.execute(
                "SELECT DISTINCT timeline_id FROM components WHERE file_id = ? "
                "ORDER BY timeline_id",
                (self.file_id,),
            )
            for (tid,) in rows:
                self.timeline(tid)
            self._loaded_all = True

    def parent(self, comp: Component) -> Component | None:
        pid = self._parent_id.get(comp.id)
        return None if pid is None else self._by_id.get(pid)

    def children(self, comp: Component) -> list[Component]:
        return self._children.get(comp.id, [])

    def is_descendant(self, comp: Component, outer: Component) -> bool:
        p = self.parent(comp)
        while p is not None and p.id != outer.id:
            p = self.parent(p)
        return p is not None

    # -- lanes --------------------------------------------------------------- #
    def lanes(self, lane: syntax.Lane | None) -> list[LaneSpec]:
        """The lanes ``IN lane`` names in this file (none: the default ones)."""
        key = ("", False) if lane is None else (lane.text, lane.quoted)
        got = self._lanes.get(key)
        if got is None:
            got = self._lanes[key] = tql_compile.resolve_lanes(
                self.log.con, self.file_id, lane
            )
        return got

    def own_lanes(self, timeline_id: str) -> list[LaneSpec]:
        got = self._own.get(timeline_id)
        if got is None:
            got = self._own[timeline_id] = tql_compile.timeline_lanes(
                self.log.con, timeline_id
            )
        return got

    def lane_items(self, spec: LaneSpec) -> list[Item]:
        """The ``(component, start, end)`` items of one lane, in time order."""
        got = self._items.get(spec)
        if got is None:
            comps = [
                c
                for c in self.timeline(spec.timeline_id)
                if spec.row_id is None or self._row_id[c.id] == spec.row_id
            ]
            if spec.kind == "hierarchy":
                assert spec.level is not None
                got = project(comps, spec.level)
            else:
                got = [(c, c.start, c.end) for c in comps if c.kind == spec.kind]
            self._items[spec] = got
        return got

    def lane_components(self, specs: list[LaneSpec]) -> list[Component]:
        """The components in any of the lanes, each once, lane by lane."""
        seen: set[str] = set()
        out: list[Component] = []
        for spec in specs:
            for comp, _, _ in self.lane_items(spec):
                if comp.id not in seen:
                    seen.add(comp.id)
                    out.append(comp)
        return out

    def home_lane(self, comp: Component) -> LaneSpec | None:
        """The lane a component lives in: its level, its row, its kind."""
        for spec in self.own_lanes(comp.timeline_id):
            if comp.kind == "hierarchy" and spec.level == comp.level:
                return spec
            if comp.kind == "range" and spec.row == comp.row:
                return spec
            if comp.kind not in ("hierarchy", "range") and spec.kind == comp.kind:
                return spec
        return None

    # -- which components fit a unit ----------------------------------------- #
    def keep(self, unit: syntax.Unit) -> syntax.Unit:
        self._keep.append(unit)
        return unit

    def fit(self, unit: syntax.Unit) -> frozenset[str]:
        """The ids of the components of the file that fit ``unit``: SQL picks by
        label and timing relations, then Python tests the other conditions."""
        got = self._fit.get(id(unit))
        if got is not None:
            return got
        sql, params = tql_compile.candidate_statement(unit, self.file_id, self.lanes)
        ids = [r[0] for r in self.log.execute(sql, params)]
        _, in_python = tql_compile.split_conds(unit)
        if in_python:
            self._load_all()
            ids = [
                i
                for i in ids
                if all(self.cond_ok(c, self._by_id[i]) for c in in_python)
            ]
        got = self._fit[id(unit)] = frozenset(ids)
        return got

    def fits(self, unit: syntax.Unit, comp: Component) -> bool:
        return comp.id in self.fit(unit)

    def cond_ok(self, cond: syntax.Cond, comp: Component) -> bool:
        """Whether ``comp`` meets a bracket condition SQL does not test: its
        children, or a relation to a sequence, an order relation, a relation
        without ``IN``."""
        if isinstance(cond, syntax.Children):
            if comp.kind != "hierarchy":
                return cond.negate
            items: list[Item] = [(c, c.start, c.end) for c in self.children(comp)]
            found = bool(items) and bool(
                find_runs(cond.seq, items, "any", False, self.fits)
            )
            return found != cond.negate
        if isinstance(cond, syntax.RelCond):
            got = bool(self.rel_targets(comp, cond.relation, first_only=True))
            return got != cond.relation.negate
        raise NotImplementedError(
            "conditions on fields are not available yet (conditions)"
        )

    # -- relations ------------------------------------------------------------ #
    def target_lanes(self, a: Component, rel: syntax.Relation) -> list[LaneSpec]:
        """Where the target of ``rel`` is looked for with ``a`` on the left: the
        lanes ``IN`` names; with no ``IN``, ``a``'s own timeline, and below ``a``
        for the relations that look inside it."""
        if rel.lane is not None:
            specs = self.lanes(rel.lane)
            tql_compile.check_labels(specs, units_of(rel.target))
            return specs
        own = self.own_lanes(a.timeline_id)
        if rel.rel in SEQUENCE_MODES and a.kind == "hierarchy":
            return [
                s
                for s in own
                if s.level is not None and a.level is not None and s.level < a.level
            ]
        return list(own)

    def inside_items(
        self, items: list[Item], outer: Component, metric: Metric, own: bool
    ) -> list[Item]:
        """The items of a lane that lie in ``outer``: its descendants when the
        lane is of its own hierarchy, otherwise those within it in time."""
        out = []
        for it in items:
            u = it[0]
            if u.id == outer.id:
                continue
            if own and u.timeline_id == outer.timeline_id and u.kind == "hierarchy":
                if self.is_descendant(u, outer):
                    out.append(it)
            elif metric.inside(u, outer):
                out.append(it)
        return out

    def candidates(self, unit: syntax.Unit, specs: list[LaneSpec]) -> list[Component]:
        seen: set[str] = set()
        out = []
        for spec in specs:
            for comp, _, _ in self.lane_items(spec):
                if comp.id not in seen:
                    seen.add(comp.id)
                    if self.fits(unit, comp):
                        out.append(comp)
        return out

    def rel_targets(
        self, a: Component, rel: syntax.Relation, first_only: bool = False
    ) -> list[list[list[Item]]]:
        """The ways ``rel`` holds with ``a`` on the left: each a list of slots
        (one per step of the target), each slot a list of items."""
        r = rel.rel
        metric = metric_of(rel)
        own = rel.lane is None
        specs = self.target_lanes(a, rel)
        out: list[list[list[Item]]] = []
        if r in SEQUENCE_MODES:
            n_steps = len(rel.target.steps)
            seen: set[tuple[tuple[str, ...], ...]] = set()
            for spec in specs:
                inner = self.inside_items(self.lane_items(spec), a, metric, own)
                if not inner:
                    continue
                for i, j, assign, _ in find_runs(
                    rel.target, inner, SEQUENCE_MODES[r], spec.point, self.fits
                ):
                    slots = slots_of(inner, i, j, assign, n_steps)
                    key = tuple(tuple(it[0].id for it in s) for s in slots)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(slots)
                    if first_only:
                        return out
            return out
        target = _single(rel.target)
        if r == "DURING" and own and a.kind == "hierarchy":
            # without IN, DURING is CONTAINS read backwards: the unit lies in a
            # unit above it, so its ancestors, not what else covers the time
            p = self.parent(a)
            while p is not None:
                if self.fits(target, p):
                    out.append([[(p, p.start, p.end)]])
                    if first_only:
                        return out
                p = self.parent(p)
            return out
        if r in ("STARTS", "ENDS"):
            home = self.home_lane(a)
            if home is None:
                return out
            items = self.lane_items(home)
            for b in self.candidates(target, specs):
                if b.id == a.id:
                    continue
                inner = self.inside_items(
                    items, b, metric, home.timeline_id == b.timeline_id
                )
                if not inner:
                    continue
                edge = inner[0] if r == "STARTS" else inner[-1]
                if edge[0].id == a.id:
                    out.append([[(b, b.start, b.end)]])
                    if first_only:
                        return out
            return out
        for b in self.candidates(target, specs):
            if timing(r, a, b, metric):
                out.append([[(b, b.start, b.end)]])
                if first_only:
                    return out
        return out

    # -- matches ------------------------------------------------------------- #
    def match(self, left: Component, slots: list[list[Item]]) -> Match:
        """A match of a sentence-form relation: the left unit, which is the
        result, then the target's steps."""
        items: list[list[Item]] = [[(left, left.start, left.end)], *slots]
        homes = [self.home_lane(s[0][0]) if s else None for s in items]
        home = homes[0]
        return Match(
            [[it[0] for it in s] for s in items],
            home.description if home else "",
            [
                [True] * len(s) if k == 0 else [False] * len(s)
                for k, s in enumerate(items)
            ],
            segments=[[(it[1], it[2]) for it in s] for s in items],
            lane_level=home.level if home else None,
            lane_row=home.row if home else None,
            slot_lanes=[h.description if h else "" for h in homes],
        )


def matches(
    scope: Scope, pattern: syntax.RelPattern, specs: list[LaneSpec]
) -> Iterator[Match]:
    """The matches of a sentence-form relation in one file, ``specs`` being the
    lanes of its left unit: the left unit, then the target's steps. A negated
    relation gives the left unit alone."""
    rel, left = pattern.relation, pattern.left
    tql_compile.check_labels(specs, [left])
    if rel.negate:
        # `A NOT REL B` is `A[NOT REL B]`
        test = scope.keep(
            syntax.Unit(left.term, [*left.conds, syntax.RelCond(rel)], left.pos)
        )
        for comp in scope.lane_components(specs):
            if scope.fits(test, comp):
                yield scope.match(comp, [])
        return
    if joins(rel):
        assert rel.lane is not None
        target = _single(rel.target)
        right = scope.lanes(rel.lane)
        tql_compile.check_labels(right, [target])
        if not right:
            return
        sql, params = join_statement(
            left, rel, specs, right, scope.file_id, scope.lanes
        )
        check_left = tql_compile.needs_python(left)
        check_right = tql_compile.needs_python(target)
        for a_id, a_tl, b_id, b_tl in scope.log.execute(sql, params):
            a, b = scope.component(a_id, a_tl), scope.component(b_id, b_tl)
            if check_left and not scope.fits(left, a):
                continue
            if check_right and not scope.fits(target, b):
                continue
            yield scope.match(a, [[(b, b.start, b.end)]])
        return
    for comp in scope.lane_components(specs):
        if scope.fits(left, comp):
            for slots in scope.rel_targets(comp, rel):
                yield scope.match(comp, slots)
