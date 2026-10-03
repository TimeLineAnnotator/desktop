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
- context: {"file_id", "timelines": [{"id", "name", "kind",
  "units": [{"id", "start", "end", "label"}]}]}
- run: {"rows": [{"file_id", "path", "start", "end", "match_start",
  "match_end", ...}], "count", "total", "truncated", "files", "explain",
  "warnings": [...], "sql", "stopped": null | "max_matches" | "time_limit" |
  "cancelled", "generation"}
- query_sql: {"sql", "notes": [...]}
- sql: {"columns": [...], "rows": [[...]], "stopped", "generation"}
- statistics: {"generation", "tables": [{"name", "title", "columns", "rows"}]}
- categories: {"generation", "categories": [{"category", "group", "n"}]}
- plan: {"plan": [{"key", "file_id", "do", "reason", "writes": [{"op",
  "component_id", "timeline_id", "field", "old", "new"}]}],
  "skipped_files": [{"file_id", "reason"}], "summary", "explain",
  "warnings", "generation"}
- apply: {"written": [file ids], "skipped": [{"file_id", "reason"}],
  "entry", "generation"}
- edit_log: [{"entry", "statement", "at", "files", "undone"}]
- undo: {"restored": [file ids], "refused": [{"file_id", "what_changed"}],
  "skipped": [{"file_id", "reason"}], "generation"}
- media_of: {"kind": "local" | "youtube" | "none", "path": str or null,
  "youtube_id": str or null, "length": float or null, "reason": str or null}
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

    def statistics(self, corpus: object, text: str, by: list[str]) -> dict:
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

    def statistics(self, corpus: object, text: str, by: list[str]) -> dict:
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
