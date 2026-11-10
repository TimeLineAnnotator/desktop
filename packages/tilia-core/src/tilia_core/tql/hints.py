"""Why an empty result is empty, where the engine can know (tql.md §10, R4).

Three messages, beside the rows, never instead of them: a sequence whose
neighbours mostly don't touch, a harmony field asked of units that are no
chords or keys, and a label that occurs nowhere in the lanes searched. Each
reads the lanes again, so the engine asks only when a search found nothing and
was not stopped; the statements are lookups, kept out of the SQL a result
shows.
"""

from __future__ import annotations

import itertools
import logging
import sqlite3
from typing import Any, Callable, Iterable

from . import compile as tql_compile
from . import names, regexes, relations, syntax, values
from .lanes import GAP_EPS, SLACK
from .readonly import Stopped
from .showsql import Recorder

LOG = logging.getLogger(__name__)

HARMONY_KINDS = ("chord", "key")


def empty(
    con: sqlite3.Connection,
    index: Any,
    query: syntax.Query,
    units: Iterable[tuple[syntax.Unit, syntax.Lane | None]],
    check: Callable[[], None],
    measures: values.Measures | None = None,
) -> list[str]:
    """The messages for a query that matched nothing. ``units`` are the units
    of the query with the lane each is read in; ``check`` raises to stop, and
    the messages found by then are given. ``measures`` reads the bars, when the
    run has read them already."""
    pattern = query.pattern
    if pattern is None:
        return []
    units = list(units)
    log = Recorder(con)  # its blocks are dropped: these are no search statements
    scopes: list[relations.Scope] = []
    out: list[str] = []
    if measures is None:
        measures = values.Measures(log)  # the bars of every file, read once
    try:
        for (file_id,) in con.execute(
            "SELECT id FROM files WHERE state = 'readable' ORDER BY path, id"
        ):
            check()
            scopes.append(
                relations.Scope(
                    log, file_id, index.time_map(file_id), {}, check, measures
                )
            )
        gaps = _gaps(scopes, pattern)
        if gaps:
            out.append(gaps)
        out.extend(_harmony_fields(scopes, query, units))
        out.extend(_nowhere(scopes, units))
    except sqlite3.OperationalError as err:
        if "interrupt" not in str(err):
            raise
        LOG.debug("the hints of an empty result stopped early")
    except (Stopped, regexes.RegexTimeout):
        LOG.debug("the hints of an empty result stopped early")
    return out


def _is_run(pattern: syntax.SeqPattern) -> bool:
    """Whether the pattern asks for neighbours: two steps or more, a step that
    repeats, or an order relation of a unit's children."""
    steps = pattern.seq.steps
    return len(steps) > 1 or pattern.order is not None or any(s.hi != 1 for s in steps)


def _gaps(
    scopes: list[relations.Scope], pattern: syntax.SeqPattern | syntax.RelPattern
) -> str | None:
    """``N of M neighbouring pairs are further apart than 0.1 s``, when more
    than half of the neighbours in the lanes searched are."""
    if not isinstance(pattern, syntax.SeqPattern) or pattern.within is not None:
        return None
    if not _is_run(pattern):
        return None
    pairs = apart = 0
    for scope in scopes:
        for spec in scope.lanes(pattern.lane):
            items = scope.lane_items(spec)
            for (_, _, end), (_, start, _) in itertools.pairwise(items):
                pairs += 1
                if start - end > GAP_EPS + SLACK:
                    apart += 1
    if not pairs or apart * 2 <= pairs:
        return None
    return (
        f"{apart} of {pairs} neighbouring pairs are further apart than "
        f"{GAP_EPS:g} s; try THEN … WITHIN"
    )


def _asked_fields(
    query: syntax.Query, units: list[tuple[syntax.Unit, syntax.Lane | None]]
) -> list[tuple[str, syntax.Lane | None]]:
    """The harmony fields the query asks, each with the lane of the units it is
    asked of: brackets in their unit's lane, ``WHERE`` in the pattern's (or, for
    ``$n`` past the first unit of a relation, the relation's)."""
    out: list[tuple[str, syntax.Lane | None]] = []
    for unit, lane in units:
        for cond in syntax.leaf_conds(unit.conds):
            if isinstance(cond, syntax.Compare) and cond.field.scope is None:
                out.append((cond.field.name, lane))
    pattern = query.pattern
    for cond in syntax.leaf_conds(query.where):
        if not isinstance(cond, syntax.Compare) or cond.field.scope is not None:
            continue
        lane = pattern.lane if pattern is not None else None
        n = cond.field.index
        if isinstance(pattern, syntax.RelPattern) and n is not None and n > 1:
            lane = pattern.relation.lane or pattern.lane
        out.append((cond.field.name, lane))
    return [(f, lane) for f, lane in out if f in names.HARMONY_FIELDS]


def _lanes_searched(lane: syntax.Lane | None) -> str:
    if lane is None:
        return "the lanes searched (the default ones)"
    shown = f'"{lane.text}"' if lane.quoted else lane.text
    return f"the lanes searched (IN {shown})"


def _harmony_fields(
    scopes: list[relations.Scope],
    query: syntax.Query,
    units: list[tuple[syntax.Unit, syntax.Lane | None]],
) -> list[str]:
    """A harmony field (``key``, ``tonic``, ``roman``, …) asked of lanes that
    hold no chords or keys in any file."""
    out: dict[str, None] = {}
    for name, lane in _asked_fields(query, units):
        kinds = {spec.kind for scope in scopes for spec in scope.lanes(lane)}
        if not kinds or kinds & set(HARMONY_KINDS):
            continue
        out[
            f"{name} is a field of chords and keys, and {_lanes_searched(lane)} "
            "hold none - try IN harmony"
        ] = None
    return list(out)


def _literals(unit: syntax.Unit) -> Iterable[syntax.Literal]:
    if unit.term is None:
        return
    for alt in unit.term.alts:
        for lit in alt.lits:
            if not lit.negate and lit.kind != "any":
                yield lit


def _nowhere(
    scopes: list[relations.Scope],
    units: list[tuple[syntax.Unit, syntax.Lane | None]],
) -> list[str]:
    """A label of the query that no unit of the lanes it is read in has, in
    any file. A lane no file has warns elsewhere, so it says nothing here."""
    out: dict[str, None] = {}
    probes: list[syntax.Unit] = []  # kept alive: a scope caches by id(unit)
    for unit, lane in units:
        for lit in _literals(unit):
            probe = syntax.Unit(syntax.Term([syntax.Alt([lit])]))
            probes.append(probe)
            lanes_found = found = said = False
            for scope in scopes:
                specs = scope.lanes(lane)
                lanes_found = lanes_found or bool(specs)
                kinds = tuple(k for k in HARMONY_KINDS if k in {s.kind for s in specs})
                if kinds and tql_compile.harmony_problems(probe, kinds):
                    said = True  # no chord or key: the engine's warning says so
                    break
                specs = scope.lanes_holding(specs, [probe])
                if any(scope.fits(probe, c) for c in scope.lane_components(specs)):
                    found = True
                    break
            if lanes_found and not found and not said:
                text = lit.raw or lit.text
                out[f"{text} occurs nowhere in {_lanes_searched(lane)}"] = None
    return list(out)
