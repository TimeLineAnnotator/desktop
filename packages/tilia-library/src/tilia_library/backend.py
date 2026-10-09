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
- categories: {"generation", "categories": [{"category", "group", "n"}]}
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
- edit_log: [{"entry", "statement", "at", "files", "undone"}]
- undo: {"restored": [file ids], "refused": [{"file_id", "what_changed"}],
  "skipped": [{"file_id", "reason"}], "generation"}
- media_of: {"kind": "local" | "youtube" | "none", "path": the absolute path of
  a local media file, or null, "youtube_id": str or null, "length": float or
  null, "reason": str or null}
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Protocol


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


_INDEX = "the index"
_ENGINE = "the query engine"
_EDITS = "bulk edits"
_MEDIA = "media"


class CoreBackend:
    """Backend on tilia-core. For now every method raises NotAvailable."""

    def open_corpus(self, path: Path) -> object:
        raise NotAvailable(_INDEX)

    def generation(self, corpus: object) -> int:
        raise NotAvailable(_INDEX)

    def scan(self, corpus: object) -> dict:
        raise NotAvailable(_INDEX)

    def reread(self, corpus: object, path: Path) -> dict:
        raise NotAvailable(_INDEX)

    def files(self, corpus: object) -> list[dict]:
        raise NotAvailable(_INDEX)

    def file_detail(self, corpus: object, file_id: str) -> dict:
        raise NotAvailable(_INDEX)

    def context(self, corpus: object, file_id: str, timeline_ids: list[str]) -> dict:
        raise NotAvailable(_INDEX)

    def explain(self, text: str) -> str:
        raise NotAvailable(_ENGINE)

    def run(
        self,
        corpus: object,
        text: str,
        *,
        max_matches: int,
        time_limit: float,
        cancel: threading.Event,
    ) -> dict:
        raise NotAvailable(_ENGINE)

    def query_sql(self, corpus: object, text: str) -> dict:
        raise NotAvailable(_ENGINE)

    def sql(
        self,
        corpus: object,
        text: str,
        *,
        max_rows: int,
        time_limit: float,
        cancel: threading.Event,
    ) -> dict:
        raise NotAvailable(_ENGINE)

    def statistics(
        self, corpus: object, text: str, by: list[str], *, fold: bool = False
    ) -> dict:
        raise NotAvailable(_ENGINE)

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
