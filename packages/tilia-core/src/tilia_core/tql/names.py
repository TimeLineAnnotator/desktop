"""The names a corpus has, and the check of a query against them.

:func:`read` makes the catalogue: every field name per scope, every role,
timeline name and range row in the index, each read with ``SELECT DISTINCT``.
:func:`check` refuses a field or a lane the corpus does not have, at its
position in the query, and a bare name in ``WHERE`` that two scopes share.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from tilia_core.labels import fold, nfc

from . import compile as tql_compile
from . import syntax
from .syntax import TQLError

UNIT_FIELDS = frozenset(
    {
        "label",
        "color",
        "comments",
        "tags",
        "start",
        "end",
        "time",
        "duration",
        "level",
        "depth",
        "parent",
        "row",
        "bar",
        "end_bar",
        "beat",
        "pass",
        "bar.count",
        "bar.label",
        "bar.beat_count",
        "root",
        "quality",
        "inversion",
        "applied_to",
        "roman",
        "symbol",
        "key",
        "tonic",
        "mode",
    }
)
TIMELINE_FIELDS = frozenset({"name", "kind", "role", "author", "id", "ordinal"})
FILE_BASE_FIELDS = frozenset({"id", "title"})
HARMONY_FIELDS = frozenset(
    {"root", "quality", "inversion", "applied_to", "roman", "symbol"}
    | {"key", "tonic", "mode"}
)
NUMERIC_FIELDS = frozenset(
    {"start", "end", "time", "duration", "level", "depth", "inversion", "applied_to"}
    | (set(tql_compile.POSITION_FIELDS) - {"bar.label"})
)
RENAMED_FIELDS = {"analyst": "author"}  # what TQL calls what other tools did
KIND_NAMES = "markers, ranges, hierarchies, beats, chords"


class Log(Protocol):
    """What :func:`read` runs statements with."""

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[Any]:
        ...


@dataclass(frozen=True)
class Catalogue:
    """What the corpus has: field names per scope (``file``, ``component``, …),
    stored roles, timeline names and range rows (each with its folded form)."""

    fields: dict[str, frozenset[str]]
    roles: frozenset[str]
    timelines: tuple[tuple[str, str], ...]
    rows: tuple[tuple[str, str], ...]

    @property
    def file_fields(self) -> frozenset[str]:
        """The names a ``file.`` prefix may carry."""
        return FILE_BASE_FIELDS | self.fields.get("file", frozenset())


def read(log: Log) -> Catalogue:
    """The catalogue of the index ``log`` runs statements on."""
    fields: dict[str, set[str]] = {}
    for scope, name in log.execute("SELECT DISTINCT scope, name FROM fields"):
        fields.setdefault(scope, set()).add(name)
    roles = log.execute(
        "SELECT DISTINCT role FROM timelines WHERE role IS NOT NULL ORDER BY role"
    )
    timelines = log.execute(
        "SELECT DISTINCT name, name_folded FROM timelines ORDER BY name"
    )
    rows = log.execute(
        "SELECT DISTINCT row, row_folded FROM ranges WHERE row IS NOT NULL ORDER BY row"
    )
    return Catalogue(
        {k: frozenset(v) for k, v in fields.items()},
        frozenset(r[0] for r in roles),
        tuple((r[0], r[1]) for r in timelines),
        tuple((r[0], r[1]) for r in rows),
    )


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
def _span(f: syntax.FieldRef) -> tuple[int, int]:
    return f.pos, f.pos + len(f.raw)


def _renamed(name: str) -> str:
    """A hint for a field TQL calls something else."""
    new = RENAMED_FIELDS.get(name)
    return f" - TQL calls it {new}" if new else ""


def _error(msg: str, f: syntax.FieldRef) -> TQLError:
    return TQLError(msg, *_span(f))


def bare_scope(cat: Catalogue, f: syntax.FieldRef, single: bool) -> str:
    """Where a bare name in ``WHERE`` lives: ``unit``, ``tl`` or ``file``. A name
    found in several places needs a prefix; in a sequence a unit's own field
    belongs on its step or after ``$n``."""
    where = []
    if single and f.name in UNIT_FIELDS:
        where.append("unit")
    if f.name in TIMELINE_FIELDS:
        where.append("tl")
    if f.name in cat.file_fields:
        where.append("file")
    if not where:
        if not single and f.name in UNIT_FIELDS:
            raise _error(
                f"in a sequence, {f.name!r} is ambiguous - put it in brackets on "
                f"its step, or write $1.{f.name}",
                f,
            )
        raise _error(f"unknown field {f.name!r}{_renamed(f.name)}", f)
    if len(where) > 1:
        options = " or ".join(
            f"{'' if w == 'unit' else w + '.'}{f.name}" for w in where
        )
        raise _error(f"{f.name!r} exists on more than one level - write {options}", f)
    return where[0]


# --------------------------------------------------------------------------- #
# Lanes
# --------------------------------------------------------------------------- #
def lane_names(cat: Catalogue, lane: syntax.Lane, fold_case: bool) -> list[str]:
    """The timeline names and range rows ``lane`` names, with names compared in
    their folded form when ``fold_case``."""
    probe = lane if not fold_case else syntax.Lane(lane.text, False, lane.pos)
    pattern = tql_compile.name_pattern(probe)
    out = []
    for name, folded in (*cat.timelines, *cat.rows):
        shown = folded if not probe.quoted else nfc(name)
        if fnmatch.fnmatchcase(shown, pattern):
            out.append(name)
    return out


def lane_exists(cat: Catalogue, lane: syntax.Lane) -> bool:
    """Whether the corpus has a lane ``lane`` names: a role, a kind, a timeline or
    a range row."""
    if not lane.quoted:
        word = fold(lane.text.strip())
        word = tql_compile.ROLE_ALIASES.get(word, word)
        if (
            word in tql_compile.BUILTIN_ROLES
            or word in cat.roles
            or word in tql_compile.KIND_WORDS
            or word in tql_compile.BAR_WORDS
        ):
            return True
    return bool(lane_names(cat, lane, fold_case=False))


def _check_lane(cat: Catalogue, lane: syntax.Lane | None) -> None:
    if lane is None or lane_exists(cat, lane):
        return
    end = lane.pos + len(lane.text) + (2 if lane.quoted else 0)
    if lane.quoted:  # a quoted name keeps its case: say so where only case differs
        near = lane_names(cat, lane, fold_case=True)
        if near:
            raise TQLError(
                f'no timeline or row called "{lane.text}" - a quoted name keeps '
                f'its case: "{sorted(set(near))[0]}"?',
                lane.pos,
                end,
            )
    raise TQLError(
        f"no timeline, role or kind called {lane.text!r} - roles: "
        f"{', '.join(sorted(tql_compile.BUILTIN_ROLES))}; kinds: {KIND_NAMES}; or a "
        'quoted "timeline name" (* is a wildcard)',
        lane.pos,
        end,
    )


# --------------------------------------------------------------------------- #
# Walking a query
# --------------------------------------------------------------------------- #
def _conditions(query: syntax.Query) -> Iterator[tuple[syntax.Cond, str]]:
    """Every condition of the query with where it stands (``bracket`` or
    ``where``), conditions inside children and relation targets included."""

    def in_conds(conds: list[syntax.Cond], ctx: str) -> Iterator[Any]:
        for c in conds:
            yield c, ctx
            if isinstance(c, syntax.Children):
                yield from in_seq(c.seq)
            elif isinstance(c, syntax.RelCond):
                yield from in_seq(c.relation.target)

    def in_seq(seq: syntax.Seq) -> Iterator[Any]:
        for st in seq.steps:
            if isinstance(st.item, syntax.Group):
                for option in st.item.options:
                    yield from in_seq(option)
            else:
                yield from in_conds(st.item.conds, "bracket")

    p = query.pattern
    if isinstance(p, syntax.SeqPattern):
        yield from in_seq(p.seq)
    elif isinstance(p, syntax.RelPattern):
        yield from in_conds(p.left.conds, "bracket")
        yield from in_seq(p.relation.target)
    yield from in_conds(query.where, "where")


def _lanes(query: syntax.Query) -> Iterator[syntax.Lane | None]:
    p = query.pattern
    if isinstance(p, syntax.SeqPattern):
        yield p.lane
    elif isinstance(p, syntax.RelPattern):
        yield p.lane
        yield p.relation.lane
    for cond, _ in _conditions(query):
        if isinstance(cond, syntax.RelCond):
            yield cond.relation.lane


def is_single(query: syntax.Query) -> bool:
    """Whether ``WHERE`` talks about one unit, so that a bare name may be its own."""
    return not isinstance(query.pattern, syntax.SeqPattern) or query.slot_count == 1


# --------------------------------------------------------------------------- #
# The check
# --------------------------------------------------------------------------- #
def _check_field(cat: Catalogue, f: syntax.FieldRef, ctx: str, single: bool) -> None:
    if f.scope == "tl":
        if f.name not in TIMELINE_FIELDS:
            raise _error(
                f"unknown timeline field {f.name!r}{_renamed(f.name)}; known: "
                f"{', '.join(sorted(TIMELINE_FIELDS))}",
                f,
            )
    elif f.scope == "file":
        if f.name not in cat.file_fields:
            raise _error(
                f"unknown file field {f.name!r}; known: "
                f"{', '.join(sorted(cat.file_fields))}",
                f,
            )
    elif ctx == "bracket" or f.index is not None:
        if f.name not in UNIT_FIELDS:
            hint = (
                f" - write tl.{f.name}"
                if f.name in TIMELINE_FIELDS
                else f" - write file.{f.name}"
                if f.name in cat.file_fields
                else _renamed(f.name)
            )
            raise _error(f"{f.name!r} is not a property of a unit{hint}", f)
    else:
        bare_scope(cat, f, single)


def _check_value(cond: syntax.Compare) -> None:
    """A number field compared with something that is no number or time would
    silently compare as text; ``parent`` is compared with a label."""
    f, v = cond.field, cond.value
    if f.scope:
        return
    if f.name == "parent" and v.kind not in ("word", "string", "regex", "any", "ref"):
        raise TQLError(
            "parent is compared with a label, as in [parent = ST]",
            v.pos,
            v.pos + len(v.raw),
        )
    if f.name in NUMERIC_FIELDS and cond.op != "~":
        if v.kind in ("word", "string") and syntax._scalar(str(v.value)) is None:
            also = ", or 8 bars / 32 beats" if f.name == "duration" else ""
            raise TQLError(
                f"{f.name} is a number - {v.raw} is not a number or a time "
                f"(write 90, 1:30 or 90s{also})",
                v.pos,
                v.pos + len(v.raw),
            )


def check(cat: Catalogue, query: syntax.Query) -> None:
    """Raise :class:`~tilia_core.tql.syntax.TQLError`, at the culprit, for a field
    or a lane the corpus does not have or a bare name two scopes share."""
    single = is_single(query)
    for lane in _lanes(query):
        _check_lane(cat, lane)
    for cond, ctx in _conditions(query):
        if isinstance(cond, syntax.Compare):
            _check_field(cat, cond.field, ctx, single)
            _check_value(cond)
            if cond.value.kind == "ref":
                _check_field(cat, cond.value.value, ctx, single)


def time_needs(query: syntax.Query) -> tuple[bool, bool]:
    """What a query asks of a file besides its components: ``(time map, media
    length)``. The time map for a position, a downbeat, a length or a distance in
    bars or beats and a ``WITHIN`` in bars or beats; the media length for a
    percentage of the piece."""
    needs_map = needs_length = False
    withins: list[syntax.Within | None] = []
    p = query.pattern
    if isinstance(p, syntax.SeqPattern):
        withins.append(p.within)
    elif isinstance(p, syntax.RelPattern):
        withins.append(p.relation.within)
    for cond, _ in _conditions(query):
        if isinstance(cond, syntax.Downbeat):
            needs_map = True
        elif isinstance(cond, syntax.RelCond):
            withins.append(cond.relation.within)
        elif isinstance(cond, syntax.Compare):
            fields = [cond.field] + (
                [cond.value.value] if cond.value.kind == "ref" else []
            )
            if any(
                not f.scope and f.name in tql_compile.POSITION_FIELDS for f in fields
            ):
                needs_map = True
            units = [cond.value.unit]
            if cond.value.offset is not None:
                units.append(cond.value.offset[1])
            needs_map = needs_map or any(u in tql_compile.LENGTH_UNITS for u in units)
            needs_length = needs_length or "%" in units
    needs_map = needs_map or any(
        w is not None and w.unit in tql_compile.LENGTH_UNITS for w in withins
    )
    return needs_map, needs_length


def where_grain(cat: Catalogue, query: syntax.Query) -> str:
    """What a query of only ``WHERE`` lists: ``timeline`` when it names timeline
    fields (and no unit's), ``file`` when only file fields, else ``match``. A bare
    name counts where it resolves: ``WHERE author = …`` lists timelines,
    ``WHERE level = 2`` units."""
    places = set()
    for cond in query.where:
        if not isinstance(cond, syntax.Compare):
            places.add("unit")
            continue
        refs = [cond.field] + ([cond.value.value] if cond.value.kind == "ref" else [])
        for f in refs:
            if f.index is not None:
                places.add("unit")
            else:
                places.add(f.scope or bare_scope(cat, f, True))
    if "unit" in places:
        return "match"
    return "timeline" if "tl" in places else "file"


def named_file_fields(cat: Catalogue, query: syntax.Query) -> list[str]:
    """The file fields ``WHERE`` names, in order of appearance: a file row has a
    column for each."""
    out: list[str] = []
    for cond in query.where:
        if not isinstance(cond, syntax.Compare):
            continue
        refs = [cond.field] + ([cond.value.value] if cond.value.kind == "ref" else [])
        for f in refs:
            if f.index is not None:
                continue
            if (f.scope or bare_scope(cat, f, True)) == "file" and f.name not in out:
                out.append(f.name)
    return out


def asks_about_harmony(query: syntax.Query) -> bool:
    """Whether ``WHERE`` names a chord or key field of a unit, so that a query of
    only ``WHERE`` must look in chords and keys too."""
    refs: list[syntax.FieldRef] = []
    for cond in query.where:
        if isinstance(cond, syntax.Compare):
            refs.append(cond.field)
            if cond.value.kind == "ref":
                refs.append(cond.value.value)
    return any(not f.scope and f.name in HARMONY_FIELDS for f in refs)
