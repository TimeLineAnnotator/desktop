"""The library's list of corpora, kept in library.toml.

A corpus is a folder of TiLiA files. The file is read fresh on every call and
changed in place, so hand edits made while the library runs are seen and kept.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import unicodedata
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomlkit

from tilia_core import state
from tilia_core.state import StateFile
from tilia_library.backend import Backend

LIBRARY_NAME = "library.toml"
FORMAT_VERSION = 1

_SLUG_LENGTH = 40
_MIN_DIGITS = 4


@dataclass(frozen=True)
class Corpus:
    """A folder of TiLiA files the library knows about."""

    id: str
    path: Path
    added: datetime
    last_opened: datetime | None

    @property
    def name(self) -> str:
        """The folder's name."""
        return self.path.name or str(self.path)

    @property
    def available(self) -> bool:
        """Whether the folder exists right now."""
        return self.path.is_dir()


def _slug(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    kept = "".join(c for c in decomposed if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", kept.lower()).strip("-")
    return slug[:_SLUG_LENGTH].rstrip("-") or "corpus"


def corpus_id(path: Path, taken: Collection[str] = ()) -> str:
    """Make an id from the folder's name and a hash of its path.

    The id gets longer until it is not in ``taken``.
    """
    digest = hashlib.sha256(os.path.normcase(str(path)).encode("utf-8")).hexdigest()
    slug = _slug(Path(path).name)
    digits = _MIN_DIGITS
    while f"{slug}-{digest[:digits]}" in taken and digits < len(digest):
        digits += 1
    return f"{slug}-{digest[:digits]}"


def same_path(a: Path, b: Path) -> bool:
    """Tell whether two resolved paths are the same (case-folded on Windows)."""
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


def _now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.astimezone()


def _is_corpus_table(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("id"), str)
        and isinstance(entry.get("path"), str)
    )


def _to_corpus(entry: Any) -> Corpus:
    added = _aware(entry.get("added")) or datetime.fromtimestamp(0, timezone.utc)
    return Corpus(
        id=str(entry["id"]),
        path=Path(str(entry["path"])),
        added=added,
        last_opened=_aware(entry.get("last_opened")),
    )


class Corpora:
    """The corpora listed in library.toml."""

    def __init__(self, path: Path | None = None) -> None:
        self.path: Path = (
            state.state_dir() / LIBRARY_NAME if path is None else Path(path)
        )
        self.set_aside_to: Path | None = None
        self.problem: str | None = None
        self._lock = threading.Lock()

    def _load(self) -> tuple[StateFile, tomlkit.TOMLDocument]:
        state_file = StateFile(self.path, FORMAT_VERSION)
        doc = state_file.load()
        if state_file.set_aside_to is None and "corpora" in doc:
            entries = doc["corpora"]
            if not isinstance(entries, list) or not all(
                isinstance(e, dict) for e in entries
            ):
                state_file.set_aside("its corpora aren't a list of tables")
                doc = tomlkit.document()
                doc["version"] = FORMAT_VERSION
        if state_file.set_aside_to is not None:
            self.set_aside_to = state_file.set_aside_to
            self.problem = state_file.problem
        return state_file, doc

    @staticmethod
    def _entries(doc: tomlkit.TOMLDocument) -> list[Any]:
        return list(doc["corpora"]) if "corpora" in doc else []

    def all(self) -> list[Corpus]:
        """Return the corpora in the file's order."""
        with self._lock:
            state_file, doc = self._load()
            return [_to_corpus(e) for e in self._entries(doc) if _is_corpus_table(e)]

    def get(self, cid: str) -> Corpus | None:
        """Return the corpus with this id, if any."""
        return next((c for c in self.all() if c.id == cid), None)

    def last(self) -> Corpus | None:
        """Return the corpus named by ``last_corpus``, if it exists."""
        with self._lock:
            state_file, doc = self._load()
            cid = doc.get("last_corpus")
            for entry in self._entries(doc):
                if _is_corpus_table(entry) and entry["id"] == cid:
                    return _to_corpus(entry)
        return None

    def add(self, folder: Path) -> Corpus:
        """Add a folder (or find it if it is listed) and mark it as last opened."""
        path = Path(folder).expanduser().resolve()
        if not path.is_dir():
            raise NotADirectoryError(f"{folder} is not a folder")
        with self._lock:
            state_file, doc = self._load()
            now = _now()
            entry = next(
                (
                    e
                    for e in self._entries(doc)
                    if _is_corpus_table(e) and same_path(Path(e["path"]), path)
                ),
                None,
            )
            if entry is None:
                taken = {e["id"] for e in self._entries(doc) if _is_corpus_table(e)}
                table = tomlkit.table()
                table["id"] = corpus_id(path, taken)
                table["path"] = str(path)
                table["added"] = now
                entry = self._append(doc, table)
            entry["last_opened"] = now
            doc["last_corpus"] = entry["id"]
            state_file.save(doc)
            return _to_corpus(entry)

    @staticmethod
    def _append(doc: tomlkit.TOMLDocument, table: Any) -> Any:
        if "corpora" not in doc:
            doc["corpora"] = tomlkit.aot()
        doc["corpora"].append(table)
        return doc["corpora"][-1]

    def remove(self, cid: str) -> bool:
        """Delete a corpus from the list; its folder is not touched."""
        with self._lock:
            state_file, doc = self._load()
            entries = doc["corpora"] if "corpora" in doc else []
            for index, entry in enumerate(entries):
                if _is_corpus_table(entry) and entry["id"] == cid:
                    del entries[index]
                    if doc.get("last_corpus") == cid:
                        del doc["last_corpus"]
                    state_file.save(doc)
                    return True
            return False

    def opened(self, cid: str) -> None:
        """Record that a corpus was just opened."""
        with self._lock:
            state_file, doc = self._load()
            for entry in self._entries(doc):
                if _is_corpus_table(entry) and entry["id"] == cid:
                    now = _now()
                    entry["last_opened"] = now
                    doc["last_corpus"] = cid
                    state_file.save(doc)
                    return


class CorpusHandles:
    """The core's handle on each corpus opened in this run, opened on first use."""

    def __init__(
        self,
        backend: Backend,
        corpora: Corpora,
        on_open: Callable[[str, Corpus, object], None] | None = None,
    ) -> None:
        self._backend = backend
        self._corpora = corpora
        self._on_open = on_open
        self._handles: dict[str, object] = {}
        self._lock = threading.Lock()

    def get(self, cid: str) -> tuple[Corpus, object]:
        """Return the corpus and its handle; ``KeyError`` for an unknown id."""
        corpus = self._corpora.get(cid)
        if corpus is None:
            raise KeyError(cid)
        with self._lock:
            opened = cid not in self._handles
            if opened:
                self._handles[cid] = self._backend.open_corpus(corpus.path)
            handle = self._handles[cid]
        if opened and self._on_open is not None:
            self._on_open(cid, corpus, handle)
        return corpus, handle

    def opened(self) -> list[tuple[str, Corpus, object]]:
        """The corpora opened so far, with their handles; opens nothing."""
        with self._lock:
            handles = list(self._handles.items())
        found = []
        for cid, handle in handles:
            corpus = self._corpora.get(cid)
            if corpus is not None:
                found.append((cid, corpus, handle))
        return found
