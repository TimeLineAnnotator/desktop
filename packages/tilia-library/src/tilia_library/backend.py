"""The seam between the library and tilia-core.

The library calls the core only through ``Backend``. Its methods return plain
JSON-ready data (dicts, lists, str, int, float, bool, None) in the shapes the
HTTP API will send, so a fixture can stand in for the core and a change in the
core's own types stays inside ``CoreBackend``. Corpus handles are opaque.

Shapes returned:

- scan, reread: {"changed": [paths], "added": [...], "removed": [...],
  "unreadable": [{"path", "line", "message"}], "unavailable": [...]}
- files: [{"file_id", "name", "path", "state": "ok" | "unreadable" |
  "unavailable", "reason": str or null, "fields": {...},
  "timelines": {"count": int, "kinds": {"hierarchy": 2, ...}}}]
- file_detail: {"file_id", "name", "path", "fields",
  "timelines": [{"id", "name", "kind", "fields": {...}}]}
- context: {"file_id", "name", "end": float or null, "timelines": [{"id",
  "name", "kind", "rows": {"<level>": "<row name>"}, "components":
  [{"component_id", "level", "start", "end", "label", "color", "point"}]}]}
  (the units of the named timelines, one strip row per level: hierarchy
  levels, range rows, a marker lane; for the cards' strips)
- run: {"columns": [str], "rows": [{<column>: value}], "matches": [{"key",
  "file_id", "name", "start", "end", "match_start", "match_end", "lane":
  {"timeline_id", "timeline", "kind", "level", "row"} or null, "slots":
  [[{"component_id", "timeline_id", "timeline", "label", "start", "end",
  "level", "kind", "target"}]], "timelines": [ids]}], "files": int, "grain":
  "match" | "timeline" | "file", "slots": int, "target": bool, "explain": str,
  "warnings": [str], "action": str or null, "action_error": {"error", "pos",
  "end"} or null, "stopped": null | "max_matches" | "time_limit" |
  "cancelled", "generation": int}. ``rows`` is the result table, one row per
  match, keyed by ``columns`` (TQL's columns: file, title, timeline, lane,
  ids, label, start, end, bar, beat, $1.label, ...; a WHERE-only query lists
  timelines or files with its own columns); ``matches[i]`` is what the cards
  draw for ``rows[i]``. Times are seconds (float).
- query_sql: {"sql", "notes": [...]}
- sql: {"columns": [str], "rows": [[value]], "stopped", "generation"};
  raises ``SqlError``
- statistics: {"generation", "tables": [{"name": "counts" | "durations" |
  "positions" | "transitions", "title", "columns": [str], "rows": [[value]]}],
  "warnings": [str]}. ``by`` is one or two keys (label, category, file,
  timeline, file.<name>, tl.<name> or a component field's name); ``fold``
  folds a category's subtypes into it. counts: the key(s), matches, files;
  durations: the key, n, min, median, mean, max, then the same five with a
  ``_bars`` suffix (n_bars, min_bars, ...); positions: the key, from_pct,
  to_pct, n; transitions: from, to, n. Rows are lists in ``columns`` order;
  raises ``QueryError``
- categories: {"generation", "grammar": bool (whether the corpus has a label
  grammar), "categories": [{"category", "group": str or null, "n"}]}; ``n`` is
  how many components carry the category (with ``fold``, subtypes are counted
  in their category)
- plan: {"plan": [{"key", "file_id", "name", "do": "write" | "skip",
  "reason": str or null, "writes": [{"op": "set" | "add" | "delete",
  "component_id", "timeline_id", "field", "old", "new"}]}], "skipped_files":
  [{"file_id", "reason"}], "summary": {"matches", "writes", "files",
  "deletes"}, "explain", "warnings", "generation"}. ``key`` is the match key
  (the same as in the query answer's ``matches``); ``old`` and ``new`` are
  null where they don't apply (a new component has no old value, a deletion
  no new one). An ``add`` write also carries ``level``, ``start`` and ``end``
  (seconds): where the new component would sit, so the page can draw it; its
  ``component_id`` is the id it will get (or null).
- apply: {"written": [file ids], "skipped": [{"file_id", "reason"}], "entry":
  str (the edit log entry), "generation"}
- edit_log: the entries, newest first: [{"entry": str, "statement": str, "at":
  str (ISO 8601), "files": [file ids], "undone": bool}]
- undo(corpus, entry, skip_files): {"restored": [file ids], "refused":
  [{"file_id", "what_changed"}], "skipped": [{"file_id", "reason"}],
  "generation"}; raises KeyError for an unknown entry
- media_of: {"kind": "local" | "youtube" | "none", "path": the absolute path of
  a local media file, or null, "youtube_id": str or null, "length": float or
  null, "reason": str or null}
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Protocol

from tilia_core import tql
from tilia_core.corpus import Corpus, ScanReport
from tilia_core.corpus import open_corpus as open_core_corpus

logger = logging.getLogger(__name__)


class NotAvailable(Exception):
    """Raised when the core can't do this yet; ``needs`` says what is missing."""

    def __init__(self, needs: str) -> None:
        super().__init__(needs)
        self.needs = needs


class QueryError(Exception):
    """A query that can't be understood.

    ``pos`` and ``end`` are character offsets in the query as typed; None
    means the whole query.
    """

    def __init__(self, msg: str, pos: int | None = None, end: int | None = None):
        super().__init__(msg)
        self.msg = msg
        self.pos = pos
        self.end = end


class SqlError(Exception):
    """A SQL statement the core refuses, or SQLite's own error."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Backend(Protocol):
    """Everything the library asks of the core."""

    # the index and the scan
    def open_corpus(self, path: Path) -> object:
        ...

    def generation(self, corpus: object) -> int:
        ...

    def scan(self, corpus: object) -> dict:
        ...

    def reread(self, corpus: object, path: Path) -> dict:
        ...

    def files(self, corpus: object) -> list[dict]:
        ...

    def file_detail(self, corpus: object, file_id: str) -> dict:
        ...

    def context(self, corpus: object, file_id: str, timeline_ids: list[str]) -> dict:
        ...

    # the query engine
    def explain(self, text: str) -> str:
        ...

    def run(
        self,
        corpus: object,
        text: str,
        *,
        max_matches: int,
        time_limit: float,
        cancel: threading.Event,
    ) -> dict:
        ...

    def query_sql(self, corpus: object, text: str) -> dict:
        ...

    def sql(
        self,
        corpus: object,
        text: str,
        *,
        max_rows: int,
        time_limit: float,
        cancel: threading.Event,
    ) -> dict:
        ...

    def statistics(
        self, corpus: object, text: str, by: list[str], *, fold: bool = False
    ) -> dict:
        ...

    def categories(self, corpus: object, fold: bool) -> dict:
        ...

    # bulk edits
    def plan(self, corpus: object, statement: str, skip_files: set[Path]) -> dict:
        ...

    def apply(
        self, corpus: object, plan: dict, keys: set[str], skip_files: set[Path]
    ) -> dict:
        ...

    def edit_log(self, corpus: object) -> list[dict]:
        ...

    def undo(self, corpus: object, entry: str, skip_files: set[Path]) -> dict:
        ...

    # media
    def media_of(self, corpus: object, file_id: str) -> dict:
        ...


def _parse(text: str) -> tql.Query:
    """``tql.parse``, with its error as the library's QueryError."""
    try:
        return tql.parse(text)
    except tql.TQLError as error:
        raise QueryError(error.msg, error.pos, error.end) from error


class _Handle:
    """A corpus as CoreBackend holds it. The core can't open a folder that
    isn't there, and the library keeps listing such a folder as unavailable,
    so the handle opens the corpus once its folder exists."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._corpus: Corpus | None = None
        self._lock = threading.Lock()

    def corpus(self) -> Corpus | None:
        """The corpus, opened now if it wasn't; None while the folder is missing."""
        with self._lock:
            if self._corpus is None:
                try:
                    # The library rescans on its own timer (liveness), so a read
                    # answers from the index as the last scan left it.
                    self._corpus = open_core_corpus(
                        self.path, rescan_before_reads=False
                    )
                except FileNotFoundError:
                    return None
            return self._corpus


def _handle(handle: object) -> _Handle:
    if not isinstance(handle, _Handle):
        raise TypeError("not a corpus handle of CoreBackend")
    return handle


def _corpus(handle: object) -> Corpus:
    """The opened corpus; QueryError while its folder is missing."""
    found = _handle(handle).corpus()
    if found is None:
        raise QueryError("the corpus folder is missing")
    return found


def _opened(handle: object, file_id: str) -> Corpus:
    """The opened corpus; KeyError for ``file_id`` while its folder is missing."""
    found = _handle(handle).corpus()
    if found is None:
        raise KeyError(file_id)
    return found


def _flat(fields: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    """A field with one value as that value, with several as a list."""
    return {n: (v[0] if len(v) == 1 else list(v)) for n, v in fields.items()}


_NO_CHANGE: dict = {
    "changed": [],
    "added": [],
    "removed": [],
    "unreadable": [],
    "unavailable": [],
}


def _report(report: ScanReport) -> dict:
    if report.error is not None:
        logger.warning("A change to the index couldn't be applied: %s", report.error)
    return {
        "changed": list(report.changed) + [new for _, new in report.moved],
        "added": list(report.added) + list(report.back),
        "removed": [old for old, _ in report.moved],
        "unreadable": [
            {"path": path, "line": line, "message": message}
            for path, line, message in report.unreadable
        ],
        "unavailable": list(report.unavailable),
    }


def _key(file_id: str) -> int:
    """The index's key of an id the page sent; KeyError when it is none."""
    try:
        return int(file_id)
    except (TypeError, ValueError):
        raise KeyError(file_id) from None


def _json(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


_ENGINE = "the query engine"
_EDITS = "bulk edits"
_MEDIA = "media"

SHOW_SQL_TIME_LIMIT_S = 10.0
STATISTICS_MAX_MATCHES = 20_000
STATISTICS_TIME_LIMIT_S = 30.0
_STATISTICS = (
    ("counts", "Counts"),
    ("durations", "Durations"),
    ("positions", "Positions"),
    ("transitions", "Transitions"),
)
_STRIP_KINDS = ("hierarchy", "range", "marker", "harmony")
"""The kinds whose strips a card draws when it names no timelines."""


class CoreBackend:
    """Backend on tilia-core. What the core can't do yet raises NotAvailable.

    The index's keys are integers and the page's ids are text, so every id goes
    out as ``str`` and comes back through ``int``.
    """

    def open_corpus(self, path: Path) -> object:
        handle = _Handle(Path(path))
        handle.corpus()
        return handle

    def generation(self, corpus: object) -> int:
        found = _handle(corpus).corpus()
        return 0 if found is None else found.generation

    def scan(self, corpus: object) -> dict:
        found = _handle(corpus).corpus()
        if found is None:
            return {name: [] for name in _NO_CHANGE}
        return _report(found.scan())

    def reread(self, corpus: object, path: Path) -> dict:
        found = _handle(corpus).corpus()
        if found is None:
            return {name: [] for name in _NO_CHANGE}
        try:
            return _report(found.reread(path))
        except ValueError as error:
            # outside the folder, or a path the scan leaves out
            logger.debug("Not rereading %s: %s", path, error)
            return {name: [] for name in _NO_CHANGE}

    def files(self, corpus: object) -> list[dict]:
        found = _handle(corpus).corpus()
        if found is None:
            return []
        out = []
        for row in found.files():
            kinds = dict(row.timeline_kinds)
            out.append(
                {
                    "file_id": str(row.id),
                    "name": Path(row.path).name,
                    "path": row.path,
                    "state": "ok" if row.state == "readable" else row.state,
                    "reason": row.reason,
                    "fields": _flat(row.fields),
                    "timelines": {"count": sum(kinds.values()), "kinds": kinds},
                }
            )
        return out

    def file_detail(self, corpus: object, file_id: str) -> dict:
        c = _opened(corpus, file_id)
        detail = c.file_detail(_key(file_id))
        with c.reading() as r:
            con = r.connection
            units = dict(
                con.execute(
                    "SELECT timeline_id, count(*) FROM components WHERE file_id = ? "
                    "GROUP BY timeline_id",
                    (detail.file.id,),
                ).fetchall()
            )
            levels = dict(
                con.execute(
                    "SELECT c.timeline_id, count(DISTINCT h.level) FROM components c "
                    "JOIN hierarchies h ON h.component_id = c.id WHERE c.file_id = ? "
                    "GROUP BY c.timeline_id",
                    (detail.file.id,),
                ).fetchall()
            )
        timelines = []
        for tl in detail.timelines:
            fields = _flat(tl.fields)
            if tl.role:
                fields["role"] = tl.role
            if tl.author:
                fields["author"] = tl.author
            if tl.id in levels:
                fields["levels"] = levels[tl.id]
            fields["units"] = units.get(tl.id, 0)
            timelines.append(
                {"id": str(tl.id), "name": tl.name, "kind": tl.kind, "fields": fields}
            )
        return {
            "file_id": str(detail.file.id),
            "name": Path(detail.file.path).name,
            "path": detail.file.path,
            "fields": _flat(detail.file.fields),
            "timelines": timelines,
        }

    def context(self, corpus: object, file_id: str, timeline_ids: list[str]) -> dict:
        c = _opened(corpus, file_id)
        fid = _key(file_id)
        wanted = {_key(t) for t in timeline_ids}
        with c.reading() as r:
            con = r.connection
            row = con.execute(
                "SELECT path, media_length FROM files WHERE id = ?", (fid,)
            ).fetchone()
            if row is None:
                raise KeyError(file_id)
            path, end = row
            if end is None:
                end = con.execute(
                    'SELECT max("end") FROM components WHERE file_id = ?', (fid,)
                ).fetchone()[0]
            timelines = []
            for tid, name, kind in con.execute(
                "SELECT id, name, kind FROM timelines WHERE file_id = ? "
                "ORDER BY ordinal, id",
                (fid,),
            ).fetchall():
                if wanted:
                    if tid not in wanted:
                        continue
                elif kind not in _STRIP_KINDS:
                    continue
                timelines.append(_context_timeline(con, tid, name, kind))
        return {
            "file_id": str(fid),
            "name": Path(path).name,
            "end": end,
            "timelines": timelines,
        }

    def explain(self, text: str) -> str:
        return tql.explain(_parse(text))

    def run(
        self,
        corpus: object,
        text: str,
        *,
        max_matches: int,
        time_limit: float,
        cancel: threading.Event,
    ) -> dict:
        c = _corpus(corpus)
        query = _parse(text)
        result = _run(c, query, max_matches, time_limit, cancel)
        return _run_json(c, query, result)

    def query_sql(self, corpus: object, text: str) -> dict:
        c = _corpus(corpus)
        result = _run(c, _parse(text), 1, SHOW_SQL_TIME_LIMIT_S, None)
        # one statement runs per lane or file: show each part once
        blocks = list({b.comment: b for b in result.sql_blocks}.values())
        sql = "\n\n".join(b.text for b in blocks if b.statement is not None)
        notes = [b.comment for b in blocks if b.statement is None]
        return {"sql": sql, "notes": notes}

    def sql(
        self,
        corpus: object,
        text: str,
        *,
        max_rows: int,
        time_limit: float,
        cancel: threading.Event,
    ) -> dict:
        c = _handle(corpus).corpus()
        if c is None:
            raise SqlError("the corpus folder is missing")
        try:
            table = tql.sql(
                c, text, max_rows=max_rows, time_limit=time_limit, cancel=cancel
            )
        except tql.TQLError as error:
            raise SqlError(error.msg) from error
        return {
            "columns": list(table.columns),
            "rows": [[_json(v) for v in row] for row in table.rows],
            "stopped": table.stopped,
            "generation": c.generation,
        }

    def statistics(
        self, corpus: object, text: str, by: list[str], *, fold: bool = False
    ) -> dict:
        c = _corpus(corpus)
        query = _parse(text)
        keys = list(by)
        if not 1 <= len(keys) <= 2:
            raise QueryError("by must name one or two keys")
        result = _run(c, query, STATISTICS_MAX_MATCHES, STATISTICS_TIME_LIMIT_S, None)
        tables = []
        try:
            for name, title in _STATISTICS:
                if name == "transitions":
                    table = result.stats(name, fold_subtypes=fold)
                elif name == "counts":
                    table = result.stats(name, keys, fold_subtypes=fold)
                else:
                    table = result.stats(name, keys[0], fold_subtypes=fold)
                tables.append(
                    {
                        "name": name,
                        "title": title,
                        "columns": list(table.columns),
                        "rows": [[_json(v) for v in row] for row in table.rows],
                    }
                )
        except ValueError as error:
            raise QueryError(str(error)) from error
        warnings = list(result.warnings)
        if result.stopped is not None:
            warnings.append(
                f"the query stopped early ({result.stopped}): the tables count "
                "only the matches found"
            )
        return {"generation": result.generation, "tables": tables, "warnings": warnings}

    def categories(self, corpus: object, fold: bool) -> dict:
        raise NotAvailable(_ENGINE)

    def plan(self, corpus: object, statement: str, skip_files: set[Path]) -> dict:
        raise NotAvailable(_EDITS)

    def apply(
        self, corpus: object, plan: dict, keys: set[str], skip_files: set[Path]
    ) -> dict:
        raise NotAvailable(_EDITS)

    def edit_log(self, corpus: object) -> list[dict]:
        raise NotAvailable(_EDITS)

    def undo(self, corpus: object, entry: str, skip_files: set[Path]) -> dict:
        raise NotAvailable(_EDITS)

    def media_of(self, corpus: object, file_id: str) -> dict:
        raise NotAvailable(_MEDIA)


# --------------------------------------------------------------------------- #
# CoreBackend's shapes
# --------------------------------------------------------------------------- #
def _run(
    c: Corpus,
    query: tql.Query,
    max_matches: int | None,
    time_limit: float | None,
    cancel: threading.Event | None,
) -> tql.Result:
    try:
        return tql.run(
            c, query, max_matches=max_matches, time_limit=time_limit, cancel=cancel
        )
    except tql.TQLError as error:
        raise QueryError(error.msg, error.pos, error.end) from error


def _context_timeline(con: Any, tid: int, name: str, kind: str) -> dict:
    """One timeline of ``context``: its strip rows and its units."""
    found = con.execute(
        'SELECT c.id, c.kind, c.start, c."end", c.label, c.color, h.level, r.row, '
        "ch.symbol, k.key "
        "FROM components c "
        "LEFT JOIN hierarchies h ON h.component_id = c.id "
        "LEFT JOIN ranges r ON r.component_id = c.id "
        "LEFT JOIN chords ch ON ch.component_id = c.id "
        "LEFT JOIN keys k ON k.component_id = c.id "
        'WHERE c.timeline_id = ? ORDER BY c.start, c."end", c.id',
        (tid,),
    ).fetchall()
    rows: dict[str, str] = {}
    row_levels: dict[str, int] = {}
    if kind == "hierarchy":
        for level in sorted({r[6] for r in found if r[6] is not None}):
            rows[str(level)] = f"level {level}"
    elif kind == "range":
        for r in found:
            if r[7] not in row_levels:
                row_levels[r[7]] = len(row_levels) + 1
                rows[str(row_levels[r[7]])] = r[7] or ""
    elif kind == "harmony":
        rows = {"1": "chords", "2": "keys"}
    else:
        rows = {"1": name}
    components = []
    for cid, ckind, start, end, label, color, level, row, symbol, key in found:
        if kind == "hierarchy":
            at = level if level is not None else 1
        elif kind == "range":
            at = row_levels[row]
        elif kind == "harmony":
            at = 2 if ckind == "key" else 1
            label = label or symbol or key or ""
        else:
            at = 1
        components.append(
            {
                "component_id": str(cid),
                "level": at,
                "start": start,
                "end": end,
                "label": label,
                "color": color,
                "point": start == end,
            }
        )
    return {
        "id": str(tid),
        "name": name,
        "kind": kind,
        "rows": rows,
        "components": components,
    }


def _run_json(c: Corpus, query: tql.Query, result: tql.Result) -> dict:
    with c.reading() as r:
        con = r.connection
        names = dict(con.execute("SELECT id, name FROM timelines").fetchall())
        paths = dict(con.execute("SELECT id, path FROM files").fetchall())
    matches = [_match_json(m, names, paths) for m in result.matches]
    rows = []
    for row, match in zip(result.rows, matches, strict=True):
        row = {k: _json(v) for k, v in row.items()}
        # TQL's file column is the document's id; the page shows the file's name.
        if "file" in row and match["name"]:
            row["file"] = match["name"]
        rows.append(row)
    action = query.action
    action_error = None
    if action is not None:
        action_error = {
            "error": "bulk edits are not available yet",
            "pos": action.pos,
            "end": len(query.text),
        }
    return {
        "columns": list(result.columns),
        "rows": rows,
        "matches": matches,
        "files": len({m["file_id"] for m in matches}),
        "grain": result.grain,
        "slots": query.slot_count,
        "target": query.has_target,
        "explain": result.explain,
        "warnings": list(result.warnings),
        "action": None if action is None else action.verb.lower(),
        "action_error": action_error,
        "stopped": result.stopped,
        "generation": result.generation,
    }


def _match_json(m: tql.Match, names: dict[int, str], paths: dict[int, str]) -> dict:
    slots = []
    spans: list[tuple[float, float]] = []
    targets: list[tuple[float, float]] = []
    timelines: list[str] = []
    file_id = m.file_id
    first = None
    for n, slot in enumerate(m.slots, 1):
        units = []
        for k, comp in enumerate(slot):
            segment = (
                m.segments[n - 1][k]
                if m.segments and len(m.segments) >= n and len(m.segments[n - 1]) > k
                else (comp.start, comp.end)
            )
            target = m.is_target(n, k)
            spans.append(segment)
            if target:
                targets.append(segment)
            if first is None:
                first = comp
                file_id = comp.file_id
            if str(comp.timeline_id) not in timelines:
                timelines.append(str(comp.timeline_id))
            units.append(
                {
                    "component_id": str(comp.id),
                    "timeline_id": str(comp.timeline_id),
                    "timeline": names.get(comp.timeline_id, ""),
                    "label": comp.label,
                    "start": segment[0],
                    "end": segment[1],
                    "level": comp.level,
                    "kind": comp.kind,
                    "target": target,
                }
            )
        slots.append(units)
    if m.timeline_id is not None and str(m.timeline_id) not in timelines:
        timelines.append(str(m.timeline_id))
    lane = None
    if first is not None:
        lane = {
            "timeline_id": str(first.timeline_id),
            "timeline": names.get(first.timeline_id, ""),
            "kind": first.kind,
            "level": m.lane_level,
            "row": m.lane_row,
        }
    path = paths.get(file_id) if file_id is not None else None
    return {
        "key": m.key,
        "file_id": None if file_id is None else str(file_id),
        "name": Path(path).name if path else None,
        "start": min((s for s, _ in spans), default=None),
        "end": max((e for _, e in spans), default=None),
        "match_start": min((s for s, _ in targets), default=None),
        "match_end": max((e for _, e in targets), default=None),
        "lane": lane,
        "slots": slots,
        "timelines": timelines,
    }
