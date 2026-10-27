"""Statistics tables of a result, and the CSV writing both share.

Every table counts the target of the matches (the units a ``@`` marks, or every
unit without ``@``), never the context, and a target once however many matches
hold it. The tables are long: one row per group. Everything is read from the
index with SQL; nothing is written to it.
"""

from __future__ import annotations

import csv
import itertools
import logging
import statistics
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from tilia_core.labels import fold, nfc
from tilia_core.labels import fold as fold_text  # in _values, fold is a flag

from . import names
from .inuse import in_use
from .lanes import BAR_KIND

if TYPE_CHECKING:
    from .result import Component, Result
    from .values import Facts

NAMES = ("counts", "durations", "positions", "transitions")
LOG = logging.getLogger(__name__)
COMPONENT_COLUMNS = ("id", "kind", "label", "start", "end", "color", "comments")
# The fields of a unit a key may name (tql.md §7.2), read as WHERE reads them;
# `parent` is a unit, not a value to group by.
UNIT_FIELDS = frozenset(names.UNIT_FIELDS - {"parent"})
TENTHS = 10


def csv_cell(value: Any) -> str:
    """``value`` as a CSV field: None is empty, text is in NFC."""
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value))


def write_csv(path: str | Path, columns: Sequence[str], rows: Iterable[Any]) -> None:
    """Write ``columns`` and ``rows`` (sequences of the same length) as UTF-8
    without a byte-order mark, LF line endings and RFC 4180's minimal quoting."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow([csv_cell(c) for c in columns])
        for row in rows:
            writer.writerow([csv_cell(v) for v in row])


@dataclass
class Table:
    """A table: its ``columns`` and ``rows`` (tuples, in order).

    ``stopped`` says why the table holds only some of its rows, else None:
    ``"max_rows"`` (:func:`tilia_core.tql.sql` read as many rows as it was
    allowed), ``"max_matches"``, ``"time_limit"`` or ``"cancelled"``. A table
    from :meth:`Result.stats` carries the reason its result stopped for, and
    counts only the matches that were found. ``to_csv`` returns the reason."""

    columns: list[str]
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    stopped: str | None = None

    def to_csv(self, path: str | Path) -> str | None:
        """Write the table as CSV (UTF-8 in NFC, LF, no byte-order mark) and
        return ``stopped``. The file holds the table and nothing else; when
        ``stopped`` is not None a WARNING is logged that names the reason."""
        write_csv(path, self.columns, self.rows)
        if self.stopped is not None:
            LOG.warning(
                "writing the CSV of a table that stopped (%s): it holds only "
                "the rows found",
                self.stopped,
            )
        return self.stopped


def _sort_key(value: Any) -> tuple[int, int, Any]:
    if value is None:
        return (1, 0, 0)
    if isinstance(value, (int, float)):
        return (0, 0, value)
    return (0, 1, str(value))


def _row_key(values: Sequence[Any]) -> list[tuple[int, int, Any]]:
    return [_sort_key(v) for v in values]


class _Reader:
    """The index reads the tables need, for the targets of one result, inside
    one read of the index (``reading``)."""

    def __init__(self, result: Result, reading: Any) -> None:
        self.index = result._index
        self.reading = reading
        self.con = reading.connection
        self.result = result
        self._facts: dict[str, Facts] = {}
        self._targets: list[Component] | None = None

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[Any]:
        """What :class:`~tilia_core.tql.values.Facts` runs statements with."""
        return self.con.execute(sql, params).fetchall()

    def facts(self, file_id: str) -> Facts:
        """The stored fields of one file's units, as ``WHERE`` reads them."""
        got = self._facts.get(file_id)
        if got is None:
            from .values import Facts  # values imports result, which imports here

            got = self._facts[file_id] = Facts(self, file_id)
        return got

    def targets(self) -> list[Component]:
        """The distinct target units of the matches, in order of appearance.
        When the index has changed since the result was made, the units of
        changed files have new keys: those whose keys are gone are left out,
        with a warning on the result."""
        if self._targets is not None:
            return self._targets
        seen: dict[Any, Component] = {}
        for m in self.result.matches:
            for n, slot in enumerate(m.slots, 1):
                for k, comp in enumerate(slot):
                    if m.is_target(n, k) and comp.id not in seen:
                        seen[comp.id] = comp
        found = list(seen.values())
        if self.reading.generation != self.result.generation:
            kept = [c for c in found if self._still_there(c)]
            gone = len(found) - len(kept)
            if gone:
                _warn(
                    self.result,
                    f"files changed since this result; {gone} of its units "
                    f"{'were' if gone != 1 else 'was'} left out; run it again",
                )
            found = kept
        self._targets = found
        return found

    def _still_there(self, comp: Component) -> bool:
        """Whether the index still holds ``comp`` under its key."""
        if comp.kind == BAR_KIND:
            count = str(comp.id).rpartition(":")[2]
            sql = "SELECT 1 FROM measures WHERE file_id = ? AND count = ?"
            found = self.con.execute(sql, (comp.file_id, int(count))).fetchone()
            return found is not None
        sql = "SELECT 1 FROM components WHERE id = ? AND file_id = ?"
        return self.con.execute(sql, (comp.id, comp.file_id)).fetchone() is not None

    def one(self, sql: str, params: tuple[Any, ...]) -> Any:
        row = self.con.execute(sql, params).fetchone()
        return None if row is None else row[0]

    def file_field_names(self) -> list[str]:
        rows = self.con.execute(
            "SELECT DISTINCT name FROM fields WHERE scope = 'file' ORDER BY name"
        )
        return sorted({"id", *(r[0] for r in rows)})

    def component_field_names(self) -> list[str]:
        rows = self.con.execute(
            "SELECT DISTINCT name FROM fields WHERE scope = 'component'"
        )
        return sorted({*COMPONENT_COLUMNS, *UNIT_FIELDS, *(r[0] for r in rows)})


def _check_key(reader: _Reader, key: str) -> None:
    """Raise ``ValueError`` naming the allowed keys unless ``key`` is one."""
    if key in ("label", "category", "file", "timeline"):
        return
    if key.startswith("file.") and key[5:] in reader.file_field_names():
        return
    if key.startswith("tl.") and key[3:] in names.TIMELINE_FIELDS:
        return
    if "." not in key and key in reader.component_field_names():
        return
    allowed = [
        "label",
        "category",
        "file",
        "timeline",
        *(f"file.{n}" for n in reader.file_field_names()),
        *(f"tl.{n}" for n in sorted(names.TIMELINE_FIELDS)),
        *reader.component_field_names(),
    ]
    raise ValueError(f"unknown key {key!r}; allowed: {', '.join(allowed)}")


def _values(reader: _Reader, comp: Component, key: str, fold: bool) -> list[Any]:
    """The group values of ``comp`` under ``key``: one, except for categories
    and tags.

    ``label`` is the label in NFC, case and spacing kept (``category`` folds
    them); a target without a category has the one value None. ``tags`` gives
    each tag once, folded as ``category`` folds and gives each category, so a
    unit tagged ``fast`` and ``loud`` counts under each, and ``Fast`` is
    ``fast``; one without tags has the one value None. Another field with several values (a file field, a component field
    set twice) gives them joined by ``, ``, as the result table does."""
    if key == "label":
        return [nfc(comp.label)]
    if key == "file":  # by path: keys change between runs, copies share an id
        return [reader.one("SELECT path FROM files WHERE id = ?", (comp.file_id,))]
    if key == "timeline":
        return [
            reader.one("SELECT name FROM timelines WHERE id = ?", (comp.timeline_id,))
        ]
    if key == "category":
        rows = reader.con.execute(
            "SELECT category, supertype FROM categories WHERE component_id = ?",
            (comp.id,),
        )
        # folded, a subtype counts as the category its label grammar puts it
        # under; with no grammar a dot is part of the category
        found = [(r[1] or r[0]) if fold else r[0] for r in rows]
        return sorted(set(found)) or [None]
    if key.startswith("file."):
        name = key[5:]
        if name == "id":  # the document id the file stores
            return [
                reader.one(
                    "SELECT document_id FROM files WHERE id = ?", (comp.file_id,)
                )
            ]
        rows = reader.con.execute(
            "SELECT value FROM fields WHERE scope = 'file' AND owner_id = ? "
            "AND name = ? ORDER BY rowid",
            (comp.file_id, name),
        ).fetchall()
        return [", ".join(str(r[0]) for r in rows) if rows else None]
    if key.startswith("tl."):
        column = key[3:]  # one of names.TIMELINE_FIELDS, checked
        if column == "id":  # the timeline's id in its file
            column = "uuid"
        return [
            reader.one(
                f"SELECT {column} FROM timelines WHERE id = ?", (comp.timeline_id,)
            )
        ]
    if key in COMPONENT_COLUMNS:
        # a unit's id is its id in its file, not the index's key
        column = {"end": '"end"', "id": "uuid"}.get(key, key)
        return [reader.one(f"SELECT {column} FROM components WHERE id = ?", (comp.id,))]
    if key == "level":
        return [
            reader.one(
                "SELECT level FROM hierarchies WHERE component_id = ?", (comp.id,)
            )
        ]
    if key == "depth":
        return [
            reader.one(
                "SELECT depth FROM hierarchies WHERE component_id = ?", (comp.id,)
            )
        ]
    if key == "row":
        return [reader.one("SELECT row FROM ranges WHERE component_id = ?", (comp.id,))]
    if key in ("time", "duration"):
        return [comp.start if key == "time" else comp.end - comp.start]
    if key in UNIT_FIELDS:  # a chord, key or position field, or tags
        value = reader.facts(comp.file_id).unit(comp.id).get(key)
        if key == "tags":  # one group per tag, folded as a category is
            return sorted({fold_text(str(v).strip()) for v in value or []}) or [None]
        if isinstance(value, list):
            return [", ".join(str(v) for v in value) if value else None]
        return [value]
    rows = reader.con.execute(
        "SELECT value FROM fields WHERE scope = 'component' AND owner_id = ? "
        "AND name = ? ORDER BY rowid",
        (comp.id, key),
    ).fetchall()
    return [", ".join(str(r[0]) for r in rows) if rows else None]


def _groups(
    reader: _Reader, keys: list[str], fold: bool
) -> dict[tuple[Any, ...], list[Component]]:
    """The targets by group (a tuple of the keys' values), each target once
    per group."""
    groups: dict[tuple[Any, ...], list[Component]] = {}
    for comp in reader.targets():
        per_key = [_values(reader, comp, k, fold) for k in keys]
        for group in itertools.product(*per_key):
            groups.setdefault(group, []).append(comp)
    return groups


def _warn(result: Result, message: str) -> None:
    if message not in result.warnings:
        result.warnings.append(message)


def _counts(reader: _Reader, keys: list[str], fold: bool) -> Table:
    rows = [
        (*group, len(comps), len({c.file_id for c in comps}))
        for group, comps in _groups(reader, keys, fold).items()
    ]
    rows.sort(key=lambda r: _row_key(r[: len(keys)]))
    return Table([*keys, "matches", "files"], rows)


def _spread(values: list[float]) -> tuple[Any, ...]:
    if not values:
        return (None, None, None, None)
    return (
        round(min(values), 6),
        round(statistics.median(values), 6),
        round(statistics.mean(values), 6),
        round(max(values), 6),
    )


def _durations(reader: _Reader, key: str, fold: bool) -> Table:
    no_map: set[str] = set()
    off_map: set[str] = set()
    rows = []
    for group, comps in _groups(reader, [key], fold).items():
        spans = [c for c in comps if c.end > c.start]  # points have no duration
        seconds = [c.end - c.start for c in spans]
        bars: list[float] = []
        for c in spans:
            tmap = reader.reading.time_map(c.file_id)
            if tmap is None:
                no_map.add(c.file_id)
                continue
            length = tmap.length(c.start, c.end, "bar")
            if length is None:
                off_map.add(c.id)
            else:
                bars.append(length)
        rows.append(
            (*group, len(seconds), *_spread(seconds), len(bars), *_spread(bars))
        )
    if no_map:
        n = len(no_map)
        _warn(
            reader.result,
            f"{n} file{'s' if n != 1 else ''} without a time map could not answer "
            "for the bar durations",
        )
    if off_map:
        n = len(off_map)
        _warn(
            reader.result,
            f"{n} unit{'s' if n != 1 else ''} outside the time map "
            f"{'were' if n != 1 else 'was'} left out of the bar columns",
        )
    rows.sort(key=lambda r: _row_key(r[:1]))
    columns = [key, "n", "min", "median", "mean", "max"]
    columns += ["n_bars", "min_bars", "median_bars", "mean_bars", "max_bars"]
    return Table(columns, rows)


def _positions(reader: _Reader, key: str, fold: bool) -> Table:
    lengths = {
        fid: length
        for fid, length in reader.con.execute(
            "SELECT id, media_length FROM files WHERE state = 'readable'"
        )
    }
    no_length: set[str] = set()
    outside: set[str] = set()
    tenths: dict[tuple[Any, ...], int] = {}
    for group, comps in _groups(reader, [key], fold).items():
        for c in comps:
            length = lengths.get(c.file_id)
            if not length:
                no_length.add(c.file_id)
                continue
            tenth = int(round(c.start * TENTHS / length, 9) // 1)
            if tenth == TENTHS:  # a start at the very end is in the last tenth
                tenth = TENTHS - 1
            if not 0 <= tenth < TENTHS:
                outside.add(c.id)
                continue
            slot = (*group, tenth)
            tenths[slot] = tenths.get(slot, 0) + 1
    if no_length:
        n = len(no_length)
        _warn(
            reader.result,
            f"{n} file{'s' if n != 1 else ''} without a media length could not "
            "answer for positions",
        )
    if outside:
        n = len(outside)
        _warn(
            reader.result,
            f"{n} unit{'s' if n != 1 else ''} outside the media length "
            f"{'were' if n != 1 else 'was'} left out of positions",
        )
    rows = [
        (*slot[:-1], slot[-1] * TENTHS, (slot[-1] + 1) * TENTHS, n)
        for slot, n in tenths.items()
    ]
    rows.sort(key=lambda r: _row_key(r[:-1]))
    return Table([key, "from_pct", "to_pct", "n"], rows)


def _transitions(reader: _Reader) -> Table:
    # a lane: the level or row of one timeline; a harmony timeline has two,
    # its chords and its keys (tql.md §4), so the kind is part of the key
    lanes: dict[tuple[str, str, str, Any], list[Component]] = {}
    for c in reader.targets():
        lane = c.level if c.level is not None else c.row
        lanes.setdefault((c.file_id, c.timeline_id, c.kind, lane), []).append(c)
    pairs: dict[tuple[str, str], int] = {}
    for comps in lanes.values():
        comps.sort(key=lambda c: (c.start, c.end, fold(c.label), c.id))
        for a, b in zip(comps, comps[1:], strict=False):
            pair = (nfc(a.label), nfc(b.label))
            pairs[pair] = pairs.get(pair, 0) + 1
    rows = [(a, b, n) for (a, b), n in pairs.items()]
    rows.sort(key=lambda r: _row_key(r[:2]))
    return Table(["from", "to", "n"], rows)


def compute(
    result: Result,
    name: str,
    by: str | Sequence[str] | None = None,
    *,
    fold_subtypes: bool = False,
) -> Table:
    """The statistics table ``name`` of ``result`` (see :meth:`Result.stats`),
    with the ``stopped`` of ``result``.

    Raises ``ValueError`` for an unknown ``name`` or key, and for a result of
    only ``WHERE`` that lists files or timelines: the tables are of units."""
    if name not in NAMES:
        raise ValueError(f"unknown statistics {name!r}; allowed: {', '.join(NAMES)}")
    if result.grain != "match":
        raise ValueError(
            f"this result lists {result.grain}s, not units; statistics are of "
            "the units a query matched, so it must name one or a lane"
        )
    index = result._index
    if index is None:
        raise ValueError("this result has no index to read statistics from")
    with index.reading() as reading:
        reader = _Reader(result, reading)
        with in_use(reader.con):
            table = _compute_on(reader, name, by, fold_subtypes)
    table.stopped = result.stopped
    return table


def _compute_on(
    reader: _Reader,
    name: str,
    by: str | Sequence[str] | None,
    fold: bool,
) -> Table:
    """:func:`compute` once ``reader``'s connection is marked in use."""
    if name == "transitions":
        if by is not None:
            raise ValueError("transitions takes no key")
        return _transitions(reader)
    keys = ["label"] if by is None else [by] if isinstance(by, str) else list(by)
    limit = 2 if name == "counts" else 1
    if not 1 <= len(keys) <= limit:
        raise ValueError(
            f"{name} takes {'one key or two' if limit == 2 else 'one key'}"
        )
    for key in keys:
        _check_key(reader, key)
    if name == "counts":
        return _counts(reader, keys, fold)
    if name == "durations":
        return _durations(reader, keys[0], fold)
    return _positions(reader, keys[0], fold)
