"""Values in TQL conditions (tql.md §7.2, §7.3): what a field holds and how it
compares with a query's value or with another unit's field.

:func:`compare_value` and :func:`compare` take the *values* a condition reads, a
list because a ``$n`` stands for any unit its step took (Q7): ``=``, ``<`` and
the others hold when one value satisfies them, ``!=`` when none satisfies ``=``.
:class:`Facts` reads the stored values of one file's units, timelines and file
fields.

Case rules (Q25): a quoted value keeps its case, a bare word ignores it, and two
units' fields compare ignoring it. ``key``, ``roman``, ``symbol`` and regular
expressions keep case anyway. Colours compare as colours. Keys, Roman numerals
and chord symbols compare as music (``c``, ``Cm`` and ``C minor`` are one key),
as text when either side does not parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from tilia_core import derived, harmony
from tilia_core.labels import fold, nfc

from . import syntax
from .lanes import bar_id, pass_numbers
from .result import Component

CASE_SENSITIVE = frozenset({"key", "roman", "symbol"})
LABELS = ("label", "comments")  # two such texts never compare as numbers
RANGE_SLACK = 1e-9  # s: float noise at the ends of a range
ORDER = {
    "=": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "~": lambda a, b: a == b,
}


# --------------------------------------------------------------------------- #
# Comparing values
# --------------------------------------------------------------------------- #
def number(v: Any) -> float | None:
    """``v`` as a number, or None when it is not one."""
    if isinstance(v, bool):
        return float(int(v))
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def text(v: Any) -> str:
    """``v`` as text; a whole number has no decimals."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return "" if v is None else str(v)


def same_harmony(fname: str, have: str, want: str) -> bool | None:
    """Whether ``have`` and ``want`` are one key (``fname`` is ``key``) or one
    chord (``roman``, ``symbol``), read as music; None when either side does not
    parse, and the caller compares text."""
    if not have or not want:
        return None
    try:
        if fname == "key":
            return (
                harmony.parse_key(have).canonical == harmony.parse_key(want).canonical
            )
        return (
            harmony.parse_chord(have).canonical == harmony.parse_chord(want).canonical
        )
    except harmony.HarmonyError:
        return None


def _ordered(op: str, a: Any, b: Any) -> bool:
    try:
        return ORDER[op](a, b)
    except KeyError:
        raise ValueError(f"unknown operator {op}") from None


def _search(
    pattern: str, subject: str, caps: list[str] | None, literal: bool = False
) -> bool:
    """Whether ``pattern`` is found in ``subject`` (NFC, case-sensitive unless
    the pattern starts with ``(?i)``). The groups it captures go to ``caps``.
    ``literal`` reads a pattern that is another unit's data, and so no query's
    to get right, as text when it is no regular expression."""
    subject = nfc(subject)
    try:
        found = re.search(pattern, subject)
    except re.error:
        if not literal:
            raise
        found = re.search(re.escape(pattern), subject)
    if found and caps is not None:
        caps[:] = [g if g is not None else "" for g in found.groups()]
    return bool(found)


def _pair(op: str, lhs: Any, rhs: Any, fname: str, caps: list[str] | None) -> bool:
    """Two field values (``$1.label`` and ``$2.label``), neither of them None."""
    if isinstance(lhs, Component) or isinstance(rhs, Component):
        same = (
            isinstance(lhs, Component)
            and isinstance(rhs, Component)
            and lhs.id == rhs.id
        )
        return same if op == "=" else (not same) if op == "!=" else False
    if fname == "color":
        lhs, rhs = derived.color(text(lhs)), derived.color(text(rhs))
    a, b = number(lhs), number(rhs)
    both_text = isinstance(lhs, str) and isinstance(rhs, str)
    if a is not None and b is not None and not (both_text and fname in LABELS):
        return _ordered(op, a, b)
    if op == "~":
        return _search(nfc(text(rhs)), text(lhs), caps, literal=True)
    if fname in CASE_SENSITIVE:
        have, want = nfc(text(lhs)), nfc(text(rhs))
        same = same_harmony(fname, have.strip(), want.strip())
        if same is not None and op in ("=", "!="):
            return same == (op == "=")
        return _ordered(op, have, want)
    return _ordered(op, fold(text(lhs)), fold(text(rhs)))


def compare(
    op: str, lhs: list[Any], rhs: list[Any], fname: str, caps: list[str] | None = None
) -> bool:
    """Whether the values ``lhs`` stand in ``op`` to the values ``rhs`` (a field
    against a field, ``$1.label != $2.label``): some pair does, and for ``!=``
    no pair is equal. A side without a value never holds."""
    left = [x for x in lhs if x is not None]
    right = [x for x in rhs if x is not None]
    if not left or not right:
        return False
    if op == "!=":
        return not any(_pair("=", a, b, fname, caps) for a in left for b in right)
    return any(_pair(op, a, b, fname, caps) for a in left for b in right)


def _one(
    op: str, lhs: Any, v: syntax.Value, fname: str, caps: list[str] | None
) -> bool:
    """One field value, not None, against a literal value of the query."""
    if v.kind == "range":
        a = number(lhs)
        if a is None:
            return False
        lo, hi = v.value
        inside = lo - RANGE_SLACK <= a <= hi + RANGE_SLACK
        return inside if op == "=" else not inside
    if v.kind == "regex" or op == "~":
        pattern = v.value if v.kind == "regex" else text(v.value)
        if op not in ("=", "~"):
            raise ValueError(f"a regular expression goes with ~ or =, not {op}")
        return _search(pattern, text(lhs), caps)
    if fname == "color":  # raw: `808080` was read as a number
        raw = v.raw if v.kind == "number" else v.value
        return _ordered(op, derived.color(text(lhs)), derived.color(text(raw)))
    if v.kind == "number":
        a = number(lhs)
        if a is not None:
            return _ordered(op, a, float(v.value))
        return _ordered(op, fold(text(lhs)), fold(v.raw))
    a, b = number(lhs), number(v.value)
    if a is not None and b is not None and not isinstance(lhs, str):
        return _ordered(op, a, b)
    have, want = nfc(text(lhs).strip()), str(v.value).strip()
    if fname in CASE_SENSITIVE:
        same = same_harmony(fname, have, want)
        if same is not None and op in ("=", "!="):
            return same == (op == "=")
    if fname in CASE_SENSITIVE or v.kind == "string":  # quoted: case included
        return _ordered(op, have, want)
    return _ordered(op, fold(have), fold(want))


def compare_value(
    op: str,
    lhs: list[Any],
    v: syntax.Value,
    fname: str,
    caps: list[str] | None = None,
) -> bool:
    """Whether the values ``lhs`` of a field stand in ``op`` to the literal
    ``v``: some value does; for ``!=`` none is equal. ``*`` asks whether the
    field has one (``!=``: has none); a unit without a value never matches
    anything else."""
    if v.kind == "any":
        present = any(x is not None and x != "" for x in lhs)
        return not present if op == "!=" else present
    values = [x for x in lhs if x is not None]
    if not values:
        return False
    if op == "!=":
        return not any(_one("=", x, v, fname, caps) for x in values)
    return any(_one(op, x, v, fname, caps) for x in values)


# --------------------------------------------------------------------------- #
# What a condition reads fields of
# --------------------------------------------------------------------------- #
@dataclass
class Subject:
    """The units a condition is about: ``slots`` are the units each step of the
    match took (``$1`` is ``slots[0]``), in the timeline ``timeline_id``. In
    brackets (``bracket``) a bare name is the one unit's field; in ``WHERE`` it
    is the unit's when ``single`` (one step), else a timeline's or a file's."""

    slots: list[list[Component]]
    timeline_id: str | None
    single: bool = True
    bracket: bool = False


class Log(Protocol):
    """What :class:`Facts` runs statements with (the engine's statement log)."""

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[Any]:
        ...


class Facts:
    """The stored values of one file: its units' colour, comments, tags, depth,
    positions and chord and key columns, its timelines' fields and its own
    fields. Everything is loaded when first asked for."""

    def __init__(self, log: Log, file_id: str) -> None:
        self.log = log
        self.file_id = file_id
        self._units: dict[str, dict[str, Any]] | None = None
        self._timelines: dict[str, dict[str, Any]] = {}
        self._file: dict[str, list[Any]] | None = None
        self._media_length: list[float | None] | None = None

    def media_length(self) -> float | None:
        """The length of the file's media in seconds; None without one."""
        if self._media_length is None:
            rows = self.log.execute(
                "SELECT media_length FROM files WHERE id = ?", (self.file_id,)
            )
            self._media_length = [rows[0][0] if rows else None]
        return self._media_length[0]

    def unit(self, comp_id: str) -> dict[str, Any]:
        """The stored fields of one component (``tags`` is a list)."""
        if self._units is None:
            self._units = self._load_units()
        return self._units.get(comp_id, {})

    def _load_units(self) -> dict[str, dict[str, Any]]:
        rows = self.log.execute(
            "SELECT c.id, c.color, c.comments, h.depth, ch.quality, ch.inversion, "
            "ch.applied_to, ch.root, ch.roman, ch.symbol, COALESCE(ch.key, k.key), "
            "k.tonic, k.mode, p.bar, p.end_bar, p.beat, p.pass, p.bar_count, "
            "p.bar_label, p.bar_beat_count, p.downbeat FROM components c "
            "LEFT JOIN hierarchies h ON h.component_id = c.id "
            "LEFT JOIN chords ch ON ch.component_id = c.id "
            "LEFT JOIN keys k ON k.component_id = c.id "
            "LEFT JOIN positions p ON p.component_id = c.id WHERE c.file_id = ?",
            (self.file_id,),
        )
        names = (
            "color comments depth quality inversion applied_to root roman symbol "
            "key tonic mode bar end_bar beat pass bar.count bar.label "
            "bar.beat_count downbeat"
        ).split()
        units = {r[0]: dict(zip(names, r[1:], strict=True)) for r in rows}
        units.update(self._load_bars())
        for fields in units.values():
            fields["tags"] = []
        tags = self.log.execute(
            "SELECT f.owner_id, f.value FROM fields f "
            "JOIN components c ON c.id = f.owner_id "
            "WHERE f.scope = 'component' AND f.name = 'tags' AND c.file_id = ? "
            "ORDER BY f.rowid",
            (self.file_id,),
        )
        for owner, value in tags:
            units[owner]["tags"].append(value)
        return units

    def _load_bars(self) -> dict[str, dict[str, Any]]:
        """The position fields of the units of the bars lane, which no component
        row holds: each bar starts on its downbeat, at its first beat."""
        rows = self.log.execute(
            "SELECT count, number, label, beats FROM measures WHERE file_id = ? "
            "ORDER BY count",
            (self.file_id,),
        )
        passes = pass_numbers([r[1] for r in rows])
        return {
            bar_id(self.file_id, count): {
                "bar": number,
                "end_bar": number,
                "beat": 1.0,
                "pass": nth,
                "bar.count": count,
                "bar.label": label,
                "bar.beat_count": beats,
                "downbeat": 1,
            }
            for (count, number, label, beats), nth in zip(rows, passes, strict=True)
        }

    def timeline(self, timeline_id: str | None) -> dict[str, Any]:
        """The fields of a timeline: name, kind, role, author, id, ordinal."""
        if timeline_id is None:
            return {}
        got = self._timelines.get(timeline_id)
        if got is None:
            rows = self.log.execute(
                "SELECT name, kind, role, author, id, ordinal FROM timelines "
                "WHERE id = ?",
                (timeline_id,),
            )
            names = ("name", "kind", "role", "author", "id", "ordinal")
            got = dict(zip(names, rows[0], strict=True)) if rows else {}
            self._timelines[timeline_id] = got
        return got

    def file(self) -> dict[str, list[Any]]:
        """The file's fields, each with its values: ``id`` and those the
        ``fields`` table holds."""
        if self._file is None:
            got: dict[str, list[Any]] = {"id": [self.file_id]}
            rows = self.log.execute(
                "SELECT name, value FROM fields WHERE scope = 'file' "
                "AND owner_id = ? ORDER BY rowid",
                (self.file_id,),
            )
            for name, value in rows:
                got.setdefault(name, []).append(value)
            self._file = got
        return self._file
