"""Compare tilia-core's TQL with the prototype's matches on a corpus.

    python scripts/tql_compare.py CORPUS PROTOTYPE_JSON [options]

Run by maintainers, not by CI: the corpora are private or licensed for
non-commercial use, and the prototype is private. ``PROTOTYPE_JSON`` is what the
prototype's ``ql_export_matches.py`` writes for a list of queries on the same
corpus. The script indexes the folder ``CORPUS`` with ``open_corpus``, runs
each of the JSON's queries through ``tql.run`` and compares the two sides' matches
by content (TimeLineAnnotator/project-management#120; WP13's research R18):

* a match is its file's path relative to the corpus folder and, for each ``$n``,
  each unit's timeline name, kind, start and end (to 1e-6), label and whether it
  is the result;
* a query's verdict is ``same``, ``differs`` (with a sample of the matches only
  one side has), ``error`` on one side, or ``both errors``; and each side's time,
  with the ratio of the core's to the prototype's.

The prototype speaks TQL 0.1.0 and the core 0.2. Each query is translated for
the core first (:func:`translate`), as WP13's differences.md says, and the
translated queries are listed.

The prototype works out roles from timeline names; the core reads the stored
``role`` and ``author`` fields (TimeLineAnnotator/project-management#61). The
index gets the prototype's roles from ``--roles``, in memory: nothing is
written to a corpus file.

``--roles analysts``: a hierarchy named "Form (X)" has the role ``form`` and
the author X, and one named "Supplemented", "Supplemented (alt)" or
"Supplemented (alt N)" the role ``form`` and its name as author.
``--roles single --form NAME [--form NAME …]``: in each file, the hierarchies
named after the first of the ``--form`` names the file has (ignoring case)
have the role ``form``, and their name as author. In both, a marker timeline
whose name holds "cadenc" (ignoring case) has the role ``cadences``, a harmony
timeline ``harmony``, and the first beat timeline ``time_map``; no other
timeline has a role.

``--grammar`` is ``whole`` (each label read whole), ``whole-dots`` (read
whole, with the part before a dot as a supertype, as the prototype reads a
label without a grammar) or ``de-clercq`` (parts split on ``/``, with
qualifiers, trailing numbers and question marks dropped). ``--glob`` narrows
the corpus to the files that match it. ``--file-field NAME=JSON`` gives each
file the field NAME from a JSON object keyed by file stem, for fields the
prototype reads from beside the files.

Some differences follow from decisions TQL 0.2 took after the prototype's
0.1.0, and are counted as explained rather than as differences: where a
file's last bar ends (Q43), a piece of a higher unit in a hole of 0.1 s or
less, which the core doesn't show, and a result off the time map, which no
position condition matches (both decided 2026-10-26). WP13's differences.md
lists them.

Chord and key labels are left out of the comparison unless
``--chord-labels``: the core labels chords and keys as TiLiA does today, and
the prototype as TiLiA 0.6.3 did (a recorded difference).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tilia_core import open_corpus, tla, tql
from tilia_core import timemap as tm
from tilia_core.corpus.documents import (
    ComponentDoc,
    Document,
    TimelineDoc,
    UnreadableFile,
)
from tilia_core.labels import WholeLabel, fold
from tilia_core.tql import syntax

LOG = logging.getLogger(__name__)

ROUND = 6
TOLERANCE = 2e-6  # two roundings to 1e-6 apart
SHORT_HOLE = 0.1  # tql.md §6.1: a gap of 0.1 s or less is no hole
LABELLESS_KINDS = ("chord", "key")

# --------------------------------------------------------------------------- #
# Reading the corpus with the prototype's roles
# --------------------------------------------------------------------------- #
_FORM_X = re.compile(r"^Form \((.+)\)$")
_SUPPLEMENTED = re.compile(r"^Supplemented(?: \(alt(?: [2-9])?\))?$")


@dataclass(frozen=True)
class Recipe:
    """Which timelines get which role and author, as the prototype works them
    out from timeline names."""

    mode: str  # "analysts" or "single"
    form_names: tuple[str, ...] = ()

    def roles(self, doc: tla.Document) -> dict[str, tuple[str, str | None]]:
        """``{timeline id: (role, author)}`` for the timelines with a role."""
        timelines = sorted(doc.timelines.values(), key=lambda t: _ordinal(t.ordinal))
        out: dict[str, tuple[str, str | None]] = {}
        winner = self._single_winner(timelines) if self.mode == "single" else None
        beat_seen = False
        for tl in timelines:
            kind, name = _kind(tl.kind), tl.name or ""
            if kind == "hierarchy":
                if self.mode == "single":
                    if winner is not None and name == winner:
                        out[tl.id] = ("form", name)
                else:
                    found = _FORM_X.match(name)
                    if found:
                        out[tl.id] = ("form", found.group(1))
                    elif _SUPPLEMENTED.match(name):
                        out[tl.id] = ("form", name)
            elif kind == "marker" and "cadenc" in name.lower():
                out[tl.id] = ("cadences", None)
            elif kind == "harmony":
                out[tl.id] = ("harmony", None)
            elif kind == "beat" and not beat_seen:
                beat_seen = True
                out[tl.id] = ("time_map", None)
        return out

    def _single_winner(self, timelines: list[tla.Timeline]) -> str | None:
        present: dict[str, str] = {}
        for tl in timelines:
            if _kind(tl.kind) == "hierarchy" and tl.name:
                present.setdefault(tl.name.strip().lower(), tl.name)
        for name in self.form_names:
            if name.strip().lower() in present:
                return present[name.strip().lower()]
        return None


def _ordinal(value: Any) -> tuple[int, float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return 0, float(value)
    return 1, 0.0


def _kind(kind: Any) -> str:
    return kind.spelling if isinstance(kind, tla.UnknownKind) else str(kind)


@dataclass(frozen=True)
class _Document(Document):
    source: Any = field(default=None, compare=False, repr=False)


class Reader:
    """The index's ``DocumentReader`` on ``tilia_core.tla``, with the recipe's
    roles and authors in place of the stored ones."""

    extensions: tuple[str, ...] = (".tla",)

    def __init__(
        self, recipe: Recipe, file_fields: dict[str, dict[str, Any]] | None = None
    ) -> None:
        self.recipe = recipe
        self.file_fields = file_fields or {}

    def read(self, path: Path) -> Document:
        try:
            doc = tla.read(path)
        except tla.UnreadableFile as err:
            raise UnreadableFile(Path(path), err.message, err.line) from err
        roles = self.recipe.roles(doc)
        timelines = []
        for tl in sorted(doc.timelines.values(), key=lambda t: _ordinal(t.ordinal)):
            fields = {
                k: v
                for k, v in dict(tl.metadata).items()
                if k not in ("role", "author")
            }
            if tl.id in roles:
                role, author = roles[tl.id]
                fields["role"] = role
                if author is not None:
                    fields["author"] = author
            timelines.append(
                TimelineDoc(
                    id=tl.id,
                    kind=_kind(tl.kind),
                    name=tl.name or "",
                    ordinal=tl.ordinal,
                    fields=fields,
                    attrs=dict(tl.attrs),
                    components=tuple(
                        ComponentDoc(
                            id=c.id,
                            kind=_kind(c.kind),
                            attrs=dict(c.attrs),
                            fields=dict(c.metadata),
                        )
                        for c in tl.components.values()
                    ),
                )
            )
        return _Document(
            document_id=doc.document_id,
            format_version=doc.format_version,
            media_length=doc.media_length,
            time_unit=doc.time_unit,
            fields={
                **dict(doc.metadata),
                **{
                    name: values[Path(path).stem]
                    for name, values in self.file_fields.items()
                    if Path(path).stem in values
                },
            },
            timelines=tuple(timelines),
            source=doc,
        )

    def canonical_bytes(self, document: Document) -> bytes:
        return tla.canonical_bytes(document.source)  # type: ignore[attr-defined]

    def is_temporary(self, name: str) -> bool:
        return tla.is_temporary(name)


_QUALIFIER = re.compile(r"\[[^\]]*\]")
_TRAILING_NUMBER = re.compile(r"\s+\d+$")


class DeClercq:
    """The de Clercq label grammar: parts split on ``/``; in each part,
    whitespace collapsed, a trailing number, ``[qualifiers]`` and trailing
    ``?`` dropped, ``.`` subtypes kept, and the rest folded."""

    def categories(self, label: str) -> tuple[str, ...]:
        found: list[str] = []
        for part in _QUALIFIER.sub("", label).split("/"):
            part = " ".join(part.split()).rstrip("?").rstrip()
            part = _TRAILING_NUMBER.sub("", part).rstrip("?").rstrip()
            category = fold(part)
            if category and category not in found:
                found.append(category)
        return tuple(found)

    def supertype(self, category: str) -> str | None:
        head, dot, _ = category.partition(".")
        return head if dot and head else None

    def group(self, category: str) -> str | None:
        return None


class WholeLabelDots(WholeLabel):
    """Each label read whole, with the part before a dot as its supertype: the
    prototype's reading without a grammar, which TQL dropped on 2026-10-26 (a
    dot marks no subtype without a grammar). For checking what else differs."""

    def supertype(self, category: str) -> str | None:
        head, dot, _ = category.partition(".")
        return head if dot and head else None


GRAMMARS = {"whole": WholeLabel, "whole-dots": WholeLabelDots, "de-clercq": DeClercq}


class Settings:
    """The corpus's settings: no manifest, the stored roles (the reader set
    them), one label grammar, and the files that match ``glob``."""

    manifest_paths: tuple[str, ...] = ()

    def __init__(self, grammar: Any, glob: str | None) -> None:
        self._grammar = grammar
        self._glob = glob

    def role(self, timeline: TimelineDoc, document: Document) -> str | None:
        return None

    def grammar(self, timeline: TimelineDoc, document: Document) -> Any:
        return self._grammar

    def includes(self, path: str) -> bool:
        return self._glob is None or fnmatch.fnmatchcase(path, self._glob)


def time_map_of(document: Document, roles: Any) -> Any:
    """The file's time map, as WP9 chooses it."""
    return tm.time_map_of(document.source, roles)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# TQL 0.1.0 to 0.2
# --------------------------------------------------------------------------- #
_LABEL_TOKENS = ("WORD", "STRING", "REGEX")
_RELATIONS = {
    "DURING", "CONTAINS", "OVERLAPS", "SAME", "STARTS", "ENDS", "BEFORE", "AFTER",
    "CONSISTS",
}  # fmt: skip


def _is_label(tok: syntax.Tok) -> bool:
    return tok.type in _LABEL_TOKENS and not (
        tok.type == "WORD" and tok.upper in syntax.KEYWORDS | {"WITH", "OF"}
    )


def _wrap_not_or(text: str) -> str:
    """``NOT a OR b`` meant "neither a nor b" in 0.1.0; in 0.2 ``NOT`` binds
    tightest, so the labels go in parentheses: ``NOT (a OR b)``."""
    toks = syntax.lex(text)
    for i, t in enumerate(toks):
        if t.upper != "NOT" or i + 2 >= len(toks):
            continue
        if not _is_label(toks[i + 1]) or toks[i + 2].upper != "OR":
            continue
        j = i + 1
        while (
            j + 2 < len(toks) and toks[j + 1].upper == "OR" and _is_label(toks[j + 2])
        ):
            j += 2
        a, b = toks[i + 1].pos, toks[j].end
        return _wrap_not_or(text[:a] + "(" + text[a:b] + ")" + text[b:])
    return text


def _slash_to_and(text: str, err: syntax.TQLError) -> str | None:
    """``a/b`` outside a chords lane: one unit with both labels, ``a AND b``."""
    toks = [
        t
        for t in syntax.lex(text)
        if t.type == "SLASH"
        and err.pos is not None
        and err.pos <= t.pos < (err.end or 0)
    ]
    if not toks:
        return None
    for t in reversed(toks):
        text = text[: t.pos] + " AND " + text[t.end :]
    return text


def _parenthesize_target(text: str, err: syntax.TQLError) -> str | None:
    """``[DURING a OR b IN form]``: in 0.2, ``OR`` in brackets joins conditions,
    so the target's labels go in parentheses."""
    toks = syntax.lex(text)
    before = [t for t in toks if err.pos is not None and t.end <= err.pos]
    j = len(before) - 1
    while j >= 0 and (_is_label(before[j]) or before[j].upper == "OR"):
        j -= 1
    first = before[j + 1] if j + 1 < len(before) else None
    if first is None or j < 0 or before[j].upper not in _RELATIONS | {"WITH", "OF"}:
        return None
    a, b = first.pos, before[-1].end
    return text[:a] + "(" + text[a:b] + ")" + text[b:]


def translate(text: str) -> str:
    """``text`` (TQL 0.1.0) as TQL 0.2, following WP13's differences.md: ``a/b``
    between labels becomes ``a AND b``; ``NOT a OR b``, ``NOT (a OR b)``; and a
    relation's ``a OR b`` in brackets, ``(a OR b)``. Anything else is kept, and a
    query 0.2 refuses for another reason is returned unchanged."""
    out = _wrap_not_or(text)
    for _ in range(20):
        try:
            syntax.parse(out)
            return out
        except syntax.TQLError as err:
            fixed = None
            if "is a unit with both" in err.msg:
                fixed = _slash_to_and(out, err)
            elif "labels of one unit go in parentheses" in err.msg:
                fixed = _parenthesize_target(out, err)
            if fixed is None or fixed == out:
                return out
            out = fixed
    return out


# --------------------------------------------------------------------------- #
# Matches by content
# --------------------------------------------------------------------------- #
def _seconds(value: Any) -> float | None:
    return None if value is None else round(float(value), ROUND)


def _norm_kind(kind: str) -> str:
    return {"bar": "bar", "beat": "beat"}.get(kind, kind)


def _unit_key(u: dict[str, Any], chord_labels: bool) -> tuple[Any, ...]:
    label = u.get("label") or ""
    if not chord_labels and u.get("kind") in LABELLESS_KINDS:
        label = ""
    return (
        u.get("timeline"),
        _norm_kind(u.get("kind") or ""),
        label,
        bool(u.get("target")),
    )


def _match_key(m: dict[str, Any], chord_labels: bool) -> tuple[Any, ...]:
    if "slots" not in m:
        return (m["file"], m.get("timeline"))
    return (
        m["file"],
        tuple(
            tuple(
                _unit_key(u, chord_labels) + (u.get("start"), u.get("end")) for u in s
            )
            for s in m["slots"]
        ),
    )


def _shape_key(m: dict[str, Any], chord_labels: bool) -> tuple[Any, ...]:
    """The key without the times, for pairing matches whose times differ by
    rounding only."""
    if "slots" not in m:
        return (m["file"], m.get("timeline"))
    return (
        m["file"],
        tuple(tuple(_unit_key(u, chord_labels) for u in s) for s in m["slots"]),
    )


def _times(m: dict[str, Any]) -> list[float]:
    return [t for s in m.get("slots", ()) for u in s for t in (u["start"], u["end"])]


def _close(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ta, tb = _times(a), _times(b)
    return len(ta) == len(tb) and all(
        x is not None and y is not None and abs(x - y) <= TOLERANCE
        for x, y in zip(ta, tb, strict=True)
    )


def diff(
    core: list[dict[str, Any]], proto: list[dict[str, Any]], chord_labels: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The matches only the core has, and those only the prototype has, as
    multisets; matches whose times differ by rounding only are the same."""
    left = Counter(_match_key(m, chord_labels) for m in core)
    right = Counter(_match_key(m, chord_labels) for m in proto)
    only_core_keys, only_proto_keys = left - right, right - left
    only_core = _take(core, only_core_keys, chord_labels)
    only_proto = _take(proto, only_proto_keys, chord_labels)
    by_shape: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for m in only_proto:
        by_shape.setdefault(_shape_key(m, chord_labels), []).append(m)
    kept_core = []
    for m in only_core:
        pool = by_shape.get(_shape_key(m, chord_labels), [])
        twin = next((p for p in pool if _close(m, p)), None)
        if twin is None:
            kept_core.append(m)
        else:
            pool.remove(twin)
    kept_proto = [m for pool in by_shape.values() for m in pool]
    return kept_core, kept_proto


def last_bar_ends(corpus: Any) -> dict[str, float]:
    """Where each file's last bar ends in the core, by path."""
    with corpus.reading() as reading:
        rows = reading.connection.execute(
            'SELECT f.path, MAX(m."end") FROM measures m JOIN files f '
            "ON f.id = m.file_id GROUP BY f.path"
        ).fetchall()
    return {path: end for path, end in rows}


def _only_last_bar(
    core: dict[str, Any], proto: dict[str, Any], last: dict[str, float]
) -> bool:
    """Whether two matches differ only in where a file's last bar ends: the
    core ends it as TQL 0.2 says, the prototype adds the beats it lacks
    (differences.md, "Where the last bar ends", Q43)."""
    if core["file"] != proto["file"] or "slots" not in core or "slots" not in proto:
        return False
    end = last.get(core["file"])
    units = [
        (a, b)
        for sa, sb in zip(core["slots"], proto["slots"], strict=False)
        for a, b in zip(sa, sb, strict=False)
    ]
    if len(units) != sum(len(s) for s in core["slots"]) or end is None:
        return False
    differs = False
    for a, b in units:
        if {k: v for k, v in a.items() if k != "end"} != {
            k: v for k, v in b.items() if k != "end"
        }:
            return False
        if abs(a["end"] - b["end"]) > TOLERANCE:
            if a["kind"] != "bar" or abs(a["end"] - round(end, ROUND)) > TOLERANCE:
                return False
            differs = True
    return differs


def explain_last_bars(
    only_core: list[dict[str, Any]],
    only_proto: list[dict[str, Any]],
    last: dict[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Pair off the matches that differ only in where the last bar ends; return
    what is left of each side and how many pairs were explained."""
    left_proto = list(only_proto)
    kept = []
    explained = 0
    for m in only_core:
        twin = next((p for p in left_proto if _only_last_bar(m, p, last)), None)
        if twin is None:
            kept.append(m)
        else:
            left_proto.remove(twin)
            explained += 1
    return kept, left_proto, explained


def _units(m: dict[str, Any]) -> list[dict[str, Any]]:
    return [u for s in m.get("slots", ()) for u in s]


def _pieces(m: dict[str, Any]) -> list[int]:
    """The places, in the match's units, of the units that start well before
    the unit before them ends: a higher unit that the prototype shows in a
    lane where it only fills a hole between two units of the level."""
    units = _units(m)
    return [
        i
        for i in range(1, len(units))
        if units[i]["start"] < units[i - 1]["end"] - SHORT_HOLE
        and units[i]["end"] > units[i - 1]["end"] + TOLERANCE
    ]


def _unit_id(u: dict[str, Any]) -> tuple[Any, ...]:
    return (
        u["timeline"],
        u["kind"],
        u["label"],
        round(u["start"], 4),
        round(u["end"], 4),
    )


def _targets(m: dict[str, Any], drop: list[int]) -> list[tuple[Any, ...]]:
    units = _units(m)
    every = all(u["target"] for u in units)
    return [
        _unit_id(u)
        for i, u in enumerate(units)
        if i not in drop and (every or u["target"])
    ]


def explain_short_holes(
    only_core: list[dict[str, Any]], only_proto: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Pair off the matches where the prototype's lane shows a piece of a
    higher unit in a hole of 0.1 s or less between two units of a level, and
    the core, as TQL 0.2 says, shows no piece there (tql.md §4, decided
    2026-10-26): the same file, and the same result units once the pieces
    are left out."""
    left_core = list(only_core)
    kept = []
    explained = 0
    for m in only_proto:
        pieces = _pieces(m)
        twin = None
        if pieces:
            want = _targets(m, pieces)
            twin = next(
                (
                    c
                    for c in left_core
                    if c["file"] == m["file"] and _targets(c, []) == want
                ),
                None,
            )
        if twin is None:
            kept.append(m)
        else:
            left_core.remove(twin)
            explained += 1
    return left_core, kept, explained


_POSITIONS = re.compile(r"\b(downbeat|bar|end_bar|beat|pass|bars|beats)\b", re.I)


def first_bar_starts(corpus: Any) -> dict[str, float]:
    """Where each file's first bar starts in the core, by path."""
    with corpus.reading() as reading:
        rows = reading.connection.execute(
            "SELECT f.path, MIN(m.start) FROM measures m JOIN files f "
            "ON f.id = m.file_id GROUP BY f.path"
        ).fetchall()
    return {path: start for path, start in rows}


def explain_off_map(
    query: str, only_proto: list[dict[str, Any]], first: dict[str, float]
) -> tuple[list[dict[str, Any]], int]:
    """Leave out the prototype's matches of a query with a position, or a
    distance in bars or beats, whose result starts before the file's first
    bar: off the time map, where TQL 0.2 answers no position condition,
    ``NOT`` included (tql.md §7.3, decided 2026-10-26)."""
    if not _POSITIONS.search(query):
        return only_proto, 0
    kept = []
    for m in only_proto:
        start = first.get(m["file"])
        targets = [u for u in _units(m) if u["target"]] or _units(m)
        if (
            start is not None
            and targets
            and all(u["start"] < start - SHORT_HOLE for u in targets)
        ):
            continue
        kept.append(m)
    return kept, len(only_proto) - len(kept)


def _take(
    matches: list[dict[str, Any]], keys: Counter, chord_labels: bool
) -> list[dict[str, Any]]:
    left = Counter(keys)
    out = []
    for m in matches:
        k = _match_key(m, chord_labels)
        if left[k] > 0:
            left[k] -= 1
            out.append(m)
    return out


def core_entries(corpus: Any, result: tql.Result) -> list[dict[str, Any]]:
    """The core's matches in the prototype's JSON shape."""
    with corpus.reading() as reading:
        con = reading.connection
        paths = dict(con.execute("SELECT id, path FROM files").fetchall())
        names = {
            r[0]: (r[1], r[2])
            for r in con.execute("SELECT id, name, kind FROM timelines").fetchall()
        }
    out = []
    for m in result.matches:
        units = [c for s in m.slots for c in s]
        if not units:
            entry: dict[str, Any] = {"file": paths.get(m.file_id, str(m.file_id))}
            if m.timeline_id is not None:
                entry["timeline"] = names.get(m.timeline_id, (None, None))[0]
            out.append(entry)
            continue
        entry = {"file": paths.get(units[0].file_id, str(units[0].file_id))}
        entry["slots"] = [
            [
                {
                    "timeline": names.get(c.timeline_id, (None, None))[0],
                    "kind": c.kind,
                    "start": _seconds(c.start),
                    "end": _seconds(c.end),
                    "label": c.label,
                    "target": bool(m.is_target(n, k)),
                }
                for k, c in enumerate(s)
            ]
            for n, s in enumerate(m.slots, 1)
        ]
        out.append(entry)
    return out


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #
def run_one(corpus: Any, text: str) -> dict[str, Any]:
    """The core's side of one query: status, error, time, matches, warnings."""
    t0 = time.perf_counter()
    try:
        result = tql.run(corpus, text)
    except tql.TQLError as err:
        return {
            "status": "error",
            "error": str(err),
            "seconds": time.perf_counter() - t0,
            "matches": [],
            "warnings": [],
        }
    except Exception as err:  # noqa: BLE001 - a crash is a finding, not the end
        LOG.exception("the core crashed on %r", text)
        return {
            "status": "crash",
            "error": f"{type(err).__name__}: {err}",
            "seconds": time.perf_counter() - t0,
            "matches": [],
            "warnings": [],
        }
    seconds = time.perf_counter() - t0
    return {
        "status": "ok",
        "error": None,
        "seconds": seconds,
        "grain": result.grain,
        "matches": core_entries(corpus, result),
        "warnings": list(result.warnings),
        "stopped": result.stopped,
    }


def compare(
    corpus: Any, proto: dict[str, Any], chord_labels: bool, sample: int
) -> list[dict[str, Any]]:
    out = []
    last = last_bar_ends(corpus)
    first = first_bar_starts(corpus)
    for i, q in enumerate(proto["queries"], 1):
        text = q["query"]
        core_text = translate(text)
        core = run_one(corpus, core_text)
        p_ok, c_ok = q["status"] == "ok", core["status"] == "ok"
        row: dict[str, Any] = {
            "n": i,
            "query": text,
            "core_query": core_text if core_text != text else None,
            "proto_status": q["status"],
            "proto_error": (q.get("error") or {}).get("message") if not p_ok else None,
            "core_status": core["status"],
            "core_error": core["error"],
            "proto_seconds": q["seconds"],
            "core_seconds": round(core["seconds"], 4),
            "proto_matches": len(q["matches"]),
            "core_matches": len(core["matches"]),
            "core_warnings": core["warnings"],
            "proto_warnings": q.get("warnings") or [],
        }
        if p_ok and c_ok:
            only_core, only_proto = diff(core["matches"], q["matches"], chord_labels)
            explained: dict[str, int] = {}
            only_core, only_proto, n = explain_last_bars(only_core, only_proto, last)
            explained["where the last bar ends (Q43)"] = n
            only_core, only_proto, n = explain_short_holes(only_core, only_proto)
            explained["a piece in a hole of 0.1 s or less (2026-10-26)"] = n
            only_proto, n = explain_off_map(text, only_proto, first)
            explained["off the time map (2026-10-26)"] = n
            explained = {k: v for k, v in explained.items() if v}
            row["explained"] = explained
            if only_core or only_proto:
                row["verdict"] = "differs"
            else:
                row["verdict"] = "same, explained" if explained else "same"
            row["only_core"] = only_core
            row["only_proto"] = only_proto
        elif not p_ok and not c_ok:
            row["verdict"] = "both errors"
        else:
            row["verdict"] = "error on the core" if p_ok else "error on the prototype"
        ratio = None
        if q["seconds"] and q["seconds"] > 0:
            ratio = round(core["seconds"] / q["seconds"], 2)
        row["ratio"] = ratio
        out.append(row)
        LOG.info("%d/%d %s %s", i, len(proto["queries"]), row["verdict"], text)
        print(_line(row, sample), flush=True)
    return out


def _line(row: dict[str, Any], sample: int) -> str:
    head = (
        f"{row['n']:>3} {row['verdict']:<22} core {row['core_matches']:>6} "
        f"({row['core_seconds']:.3f} s)  prototype {row['proto_matches']:>6} "
        f"({row['proto_seconds']:.3f} s)  {row['query']}"
    )
    lines = [head]
    if row["core_query"]:
        lines.append(f"      as 0.2: {row['core_query']}")
    if row["verdict"].startswith("error") or row["verdict"] == "both errors":
        if row["core_error"]:
            lines.append(f"      core: {row['core_error']}")
        if row["proto_error"]:
            lines.append(f"      prototype: {row['proto_error']}")
    for why, n in (row.get("explained") or {}).items():
        lines.append(f"      explained, {why}: {n}")
    for side in ("only_core", "only_proto"):
        found = row.get(side) or []
        if found:
            lines.append(f"      {side.replace('_', ' ')}: {len(found)}")
            for m in found[:sample]:
                lines.append("        " + json.dumps(m, ensure_ascii=False))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("corpus", type=Path, help="the corpus folder")
    ap.add_argument("prototype", type=Path, help="ql_export_matches.py's JSON")
    ap.add_argument("--roles", choices=("analysts", "single"), default="single")
    ap.add_argument(
        "--form", action="append", default=[], help="a form timeline's name"
    )
    ap.add_argument("--grammar", choices=tuple(GRAMMARS), default="whole")
    ap.add_argument("--glob", help="only the files whose path matches this")
    ap.add_argument(
        "--file-field",
        action="append",
        default=[],
        metavar="NAME=JSON",
        help="a file field from beside the files: a JSON object from file stem to value",
    )
    ap.add_argument("--chord-labels", action="store_true")
    ap.add_argument("--sample", type=int, default=3)
    ap.add_argument("--out", type=Path, help="write every row as JSON here")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # labels in any script
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )

    proto = json.loads(args.prototype.read_text(encoding="utf-8"))
    file_fields = {}
    for spec in args.file_field:
        name, _, source = spec.partition("=")
        values = json.loads(Path(source).read_text(encoding="utf-8"))
        file_fields[name] = {str(k): v for k, v in values.items() if v}
    grammar = GRAMMARS[args.grammar]()
    t0 = time.perf_counter()
    corpus = open_corpus(
        args.corpus,
        rescan_before_reads=False,
        reader=Reader(Recipe(args.roles, tuple(args.form)), file_fields),
        settings=Settings(grammar, args.glob),
        time_map_of=time_map_of,
    )
    built = time.perf_counter() - t0
    report = corpus.open_report
    print(
        f"index: {len(report.added)} files in {built:.1f} s, "
        f"{len(report.unreadable)} unreadable; prototype: {proto.get('files')} files "
        f"at {proto.get('commit')}",
        flush=True,
    )
    rows = compare(corpus, proto, args.chord_labels, args.sample)
    verdicts = Counter(r["verdict"] for r in rows)
    print("\n" + ", ".join(f"{v}: {n}" for v, n in sorted(verdicts.items())))
    translated = [r for r in rows if r["core_query"]]
    print(f"translated for 0.2: {len(translated)}")
    for r in translated:
        print(f"  {r['query']}  ->  {r['core_query']}")
    if args.out:
        doc = {
            "index_seconds": round(built, 2),
            "files": len(report.added),
            "unreadable": [str(u) for u in report.unreadable],
            "prototype_commit": proto.get("commit"),
            "rows": rows,
        }
        args.out.write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
