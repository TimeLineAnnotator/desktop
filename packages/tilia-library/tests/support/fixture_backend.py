"""A stand-in for the core that answers from JSON files, for tests."""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any

from tilia_library.backend import QueryError, SqlError

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _raise_on_error_word(text: str) -> None:
    """Refuse a text with the word "error", pointing at it (in code points)."""
    if "error" in text:
        pos = text.index("error")
        raise QueryError("unexpected word", pos, pos + len("error"))


class FixtureBackend:
    """Implements every Backend method from the files in ``fixtures/``."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def _get(self, name: str) -> Any:
        if name not in self._data:
            self._data[name] = _load(name)
        return copy.deepcopy(self._data[name])

    def _by_id(self, name: str, file_id: str) -> Any:
        data = self._get(name)
        if file_id not in data:
            raise KeyError(file_id)
        return data[file_id]

    def open_corpus(self, path: Path) -> object:
        return Path(path).name

    def generation(self, corpus: object) -> int:
        return 1

    def scan(self, corpus: object) -> dict:
        return self._get("scan")

    def reread(self, corpus: object, path: Path) -> dict:
        return self._get("scan")

    def files(self, corpus: object) -> list[dict]:
        return self._get("files")

    def file_detail(self, corpus: object, file_id: str) -> dict:
        return self._by_id("file_detail", file_id)

    def context(self, corpus: object, file_id: str, timeline_ids: list[str]) -> dict:
        result = self._by_id("context", file_id)
        if timeline_ids:
            result["timelines"] = [
                t for t in result["timelines"] if t["id"] in timeline_ids
            ]
        return result

    def explain(self, text: str) -> str:
        _raise_on_error_word(text)
        return self._get("explain")["text"]

    def run(
        self,
        corpus: object,
        text: str,
        *,
        max_matches: int,
        time_limit: float,
        cancel: threading.Event,
    ) -> dict:
        _raise_on_error_word(text)
        result = self._get("run")
        if "->" in text:
            words = text.split("->", 1)[1].split()
            result["action"] = words[0].lower() if words else None
        if cancel.is_set():
            result["stopped"] = "cancelled"
        return result

    def query_sql(self, corpus: object, text: str) -> dict:
        _raise_on_error_word(text)
        return self._get("query_sql")

    def sql(
        self,
        corpus: object,
        text: str,
        *,
        max_rows: int,
        time_limit: float,
        cancel: threading.Event,
    ) -> dict:
        if not text.strip().lower().startswith(("select", "with")):
            raise SqlError("only SELECT statements can run here")
        result = self._get("sql")
        if cancel.is_set():
            result["stopped"] = "cancelled"
        return result

    def statistics(
        self, corpus: object, text: str, by: list[str], *, fold: bool = False
    ) -> dict:
        _raise_on_error_word(text)
        data = self._get("statistics")
        key = by[0]
        counts = (
            ([key, by[1], "matches", "files"], data["counts2"])
            if len(by) > 1
            else ([key, "matches", "files"], data["counts"])
        )
        tables = [
            ("counts", "Counts", *counts),
            (
                "durations",
                "Durations",
                [key, "n", "min", "median", "mean", "max"]
                + [f"{c}_bars" for c in ("n", "min", "median", "mean", "max")],
                data["durations"],
            ),
            (
                "positions",
                "Positions",
                [key, "from_pct", "to_pct", "n"],
                data["positions"],
            ),
            ("transitions", "Transitions", ["from", "to", "n"], data["transitions"]),
        ]
        return {
            "generation": data["generation"],
            "tables": [
                {"name": n, "title": t, "columns": c, "rows": r}
                for n, t, c, r in tables
            ],
            "warnings": ["subtypes folded"] if fold else [],
        }

    def categories(self, corpus: object, fold: bool) -> dict:
        data = self._get("categories")
        if fold:
            rows = data["categories"]
            by_name = {row["category"]: row for row in rows}
            kept = []
            for row in rows:
                top = row["category"].split(".", 1)[0]
                if top == row["category"]:
                    kept.append(row)
                elif top in by_name:
                    by_name[top]["n"] += row["n"]
                else:
                    kept.append({**row, "category": top})
            data["categories"] = kept
        return data

    def plan(self, corpus: object, statement: str, skip_files: set[Path]) -> dict:
        _raise_on_error_word(statement)
        return self._get("plan")

    def apply(
        self, corpus: object, plan: dict, keys: set[str], skip_files: set[Path]
    ) -> dict:
        result = self._get("apply")
        entries = self._get("plan")["plan"]
        written: list[str] = []
        for entry in entries:
            if entry["key"] in keys and entry["file_id"] not in written:
                written.append(entry["file_id"])
        result["written"] = written
        return result

    def edit_log(self, corpus: object) -> list[dict]:
        return self._get("edit_log")

    def undo(self, corpus: object, entry: str, skip_files: set[Path]) -> dict:
        if entry not in {e["entry"] for e in self._get("edit_log")}:
            raise KeyError(entry)
        return self._get("undo")

    def media_of(self, corpus: object, file_id: str) -> dict:
        return self._by_id("media_of", file_id)
