"""The walk of a corpus folder, the files' records, and the build of the index
from them (research R6, R8; data-model.md, "The file record").

- **The walk** (:func:`walk`, TimeLineAnnotator/project-management#122) takes
  every file below the folder whose name ends in one of the reader's
  extensions, in any letter case. Names that start with ``.`` are left out,
  files and folders alike; links to folders and Windows directory junctions
  aren't followed; and the reader's temporary files are left out. A subfolder that can't be listed
  is logged and skipped.
- **Reading** (:func:`read_file`) goes through the reader, with one retry after
  :data:`READ_RETRY_PAUSE` seconds. A file that fails twice is unreadable, with
  its reason; whatever reading it raised, one file never stops the build
  (FR-007).
- **The build** (:meth:`Scanner.build`) reads the files in sorted path order,
  so a fresh build of the same folder gives the same keys, and inserts their
  rows through :meth:`Store.apply <tilia_core.corpus.store.Store.apply>`.

Nothing here writes to the corpus folder (FR-072).
"""

from __future__ import annotations

import itertools
import logging
import os
import stat
import sys
import time
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from . import build
from .build import Rows
from .documents import Document, DocumentReader, UnreadableFile
from .fingerprint import of_document
from .settings import CorpusSettings
from .store import Store
from .time_map import TimeMap, TimeMapOf

LOG = logging.getLogger(__name__)

READ_RETRY_PAUSE = 0.2
"""Seconds between the two tries of reading a file (research R8)."""

sleep: Callable[[float], None] = time.sleep
"""How the scan pauses before a retry (tests replace it)."""

now_ns: Callable[[], int] = time.time_ns
"""The wall clock a file's ``read_at_ns`` comes from (tests replace it)."""


def _no_time_map(document: Document, roles: object) -> None:
    return None


# --------------------------------------------------------------------------- #
# The walk
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Found:
    """A file the walk took in: its path relative to the corpus folder, with
    ``/`` and in NFC; its native path, to open; and its size and modification
    time, None when the walk couldn't ``stat`` it."""

    path: str
    native: Path
    size: int | None
    mtime_ns: int | None


def _is_junction(entry: os.DirEntry) -> bool:
    """Whether ``entry`` is a Windows directory junction, which
    ``is_dir(follow_symlinks=False)`` takes for a folder and ``is_junction()``
    (Python 3.12) would tell."""
    tag = getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0)
    return tag == stat.IO_REPARSE_TAG_MOUNT_POINT


def walk(root: Path, reader: DocumentReader, settings: CorpusSettings) -> list[Found]:
    """The files of the corpus at ``root``, sorted by path.

    The walk goes depth first with ``os.scandir``. Listing ``root`` itself may
    raise ``OSError``; a subfolder that can't be listed is logged and skipped,
    so its files are not found."""
    endings = tuple(e.lower() for e in reader.extensions)
    found: list[Found] = []

    def visit(folder: Path, prefix: str) -> None:
        try:
            with os.scandir(folder) as listing:
                entries = sorted(listing, key=lambda e: e.name)
        except OSError as err:
            if not prefix:
                raise
            LOG.warning("can't list the folder %s; skipped: %s", folder, err)
            return
        for entry in entries:
            name = entry.name
            if name.startswith("."):
                continue
            path = prefix + unicodedata.normalize("NFC", name)
            try:
                # a link to a folder is no folder here, so it isn't followed,
                # and no file either: is_file() follows it to a folder
                folder = entry.is_dir(follow_symlinks=False)
                if folder and _is_junction(entry) or not folder and not entry.is_file():
                    continue
            except OSError as err:
                LOG.warning("can't look at %s; skipped: %s", entry.path, err)
                continue
            if folder:
                visit(Path(entry.path), path + "/")
                continue
            if not name.lower().endswith(endings) or reader.is_temporary(name):
                continue
            if not settings.includes(path):
                continue
            try:
                info = entry.stat()
                size, mtime_ns = info.st_size, info.st_mtime_ns
            except OSError:
                size = mtime_ns = None  # reading it will say why
            found.append(Found(path, Path(entry.path), size, mtime_ns))

    visit(root, "")
    found.sort(key=lambda f: f.path)
    return found


# --------------------------------------------------------------------------- #
# Reading a file
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Outcome:
    """What reading a file gave: its document and fingerprint, or the reason
    and line it couldn't be read for. ``os_error`` is true when it couldn't be
    opened or read at all. ``read_at_ns`` is when the read began."""

    found: Found
    read_at_ns: int
    document: Document | None = None
    fingerprint: str | None = None
    reason: str | None = None
    line: int | None = None
    os_error: bool = False

    @property
    def readable(self) -> bool:
        return self.document is not None


_Failure = tuple[
    str, "int | None", bool, "tuple[type, BaseException, TracebackType] | None"
]


def _try_read(reader: DocumentReader, found: Found) -> Outcome | _Failure:
    read_at = now_ns()
    try:
        document = reader.read(found.native)
        return Outcome(found, read_at, document, of_document(reader, document))
    except UnreadableFile as err:
        return (str(err), err.line, False, None)
    except OSError as err:
        return (f"can't read: {err.strerror or err}", None, True, None)
    except Exception as err:  # noqa: BLE001 - a bug in the reader stops nothing
        info = sys.exc_info()
        return (f"can't read: {type(err).__name__}: {err}", None, False, info)  # type: ignore[return-value]


def read_file(reader: DocumentReader, found: Found) -> Outcome:
    """Read ``found`` through ``reader``, trying once more after
    :data:`READ_RETRY_PAUSE` seconds when the first try fails.

    A file the reader refuses (``UnreadableFile``) is unreadable with its
    reason and line; one that can't be opened or read (``OSError``) with the
    system's message, and ``os_error``; one on which the reader fails in any
    other way with the error's type and message, and its traceback is logged.
    Nothing it raises goes through, but ``KeyboardInterrupt`` and
    ``SystemExit``."""
    first = _try_read(reader, found)
    if isinstance(first, Outcome):
        return first
    sleep(READ_RETRY_PAUSE)
    read_at = now_ns()
    second = _try_read(reader, found)
    if isinstance(second, Outcome):
        return second
    reason, line, os_error, info = second
    if info is not None:
        LOG.error("the reader failed on %s: %s", found.native, reason, exc_info=info)
    return Outcome(found, read_at, reason=reason, line=line, os_error=os_error)


# --------------------------------------------------------------------------- #
# The files' records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FileRecord:
    """What the corpus keeps of a file beside the tables (data-model.md, "The
    file record").

    ``key`` is its ``files.id``; ``path`` its relative path, in NFC, and
    ``native`` the path to open; ``size`` and ``mtime_ns`` as the last scan saw
    them; ``read_at_ns`` when it was last read. ``state``, ``reason``,
    ``fingerprint`` and ``document_id`` are as in ``files``, and ``line`` the
    line of an unreadable file's reason. ``os_error`` is true when the file
    couldn't be opened or read. ``time_map`` is what ``time_map_of`` gave.
    ``keys`` are the keys its rows took, in the order they were handed out."""

    key: int
    path: str
    native: Path
    size: int | None
    mtime_ns: int | None
    read_at_ns: int | None
    state: str
    reason: str | None = None
    line: int | None = None
    fingerprint: str | None = None
    document_id: str | None = None
    format_version: str | None = None
    media_length: float | None = None
    time_unit: str | None = None
    os_error: bool = False
    time_map: TimeMap | None = None
    keys: tuple[int, ...] = ()


class _Keys:
    """The keys for one file's rows: ``first``, then the next of the corpus's
    counter; it remembers what it handed out."""

    def __init__(self, first: int, counter: Iterator[int]) -> None:
        self._first: int | None = first
        self._counter = counter
        self.handed: list[int] = []

    def __call__(self) -> int:
        if self._first is not None:
            key, self._first = self._first, None
        else:
            key = next(self._counter)
        self.handed.append(key)
        return key


def file_row(
    key: int,
    path: str,
    state: str,
    reason: str | None = None,
    record: FileRecord | None = None,
) -> Rows:
    """The rows of a file that has no rows but its own in ``files``: an
    unreadable file (``reason``), or an unavailable one, which keeps the
    document id, format version, media length and time unit of ``record``,
    as last read."""
    kept = (
        (record.document_id, record.format_version)
        if record is not None
        else (None, None)
    )
    lengths = (
        (record.media_length, record.time_unit) if record is not None else (None, None)
    )
    return Rows(
        file_id=key,
        files=[(key, path, *kept, state, reason, None, *lengths, None, None)],
    )


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ScanReport:
    """What a scan, or the first build, changed (data-model.md, "The scan
    report"). ``unreadable`` holds ``(path, line, reason)``. ``error`` is the
    error of a change that couldn't be applied: then nothing changed."""

    added: tuple[str, ...]
    changed: tuple[str, ...]
    moved: tuple[tuple[str, str], ...]
    unavailable: tuple[str, ...]
    back: tuple[str, ...]
    unreadable: tuple[tuple[str, int | None, str], ...]
    shared_ids: tuple[tuple[str, ...], ...]
    generation_before: int
    generation_after: int
    error: str | None = None

    def __bool__(self) -> bool:
        """True when anything changed."""
        return any(
            (
                self.added,
                self.changed,
                self.moved,
                self.unavailable,
                self.back,
                self.unreadable,
                self.shared_ids,
            )
        )


def shared_ids(records: dict[str, FileRecord]) -> list[tuple[str, ...]]:
    """The groups of paths of readable files that share a document id, each
    sorted, in the order of their first path."""
    groups: dict[str, list[str]] = {}
    for path in sorted(records):
        rec = records[path]
        if rec.state == "readable" and rec.document_id is not None:
            groups.setdefault(rec.document_id, []).append(path)
    return sorted(tuple(g) for g in groups.values() if len(g) > 1)


# --------------------------------------------------------------------------- #
# The scanner
# --------------------------------------------------------------------------- #
class Scanner:
    """Keeps a corpus's records, and builds its index in its store."""

    def __init__(
        self,
        root: Path,
        store: Store,
        reader: DocumentReader,
        settings: CorpusSettings,
        time_map_of: TimeMapOf | None = None,
    ) -> None:
        self.root = root
        self.store = store
        self.reader = reader
        self.settings = settings
        self.time_map_of: TimeMapOf = time_map_of or _no_time_map
        self.records: dict[str, FileRecord] = {}
        self._counter = itertools.count(1)

    def _readable(
        self, outcome: Outcome, key: int, replay: tuple[int, ...] = ()
    ) -> tuple[FileRecord, Rows]:
        """The record and rows of a file read without a problem, under ``key``.
        ``replay`` are keys the rows take again, in order (a file whose
        content is the same)."""
        document = outcome.document
        assert document is not None
        counter = iter(replay[1:]) if replay else iter(())
        keys = _Keys(key, itertools.chain(counter, self._counter))
        tmap = self.time_map_of(document, build.roles(document, self.settings))
        rows = build.rows(document, self.settings, keys, tmap)
        found = outcome.found
        record = FileRecord(
            key=key,
            path=found.path,
            native=found.native,
            size=found.size,
            mtime_ns=found.mtime_ns,
            read_at_ns=outcome.read_at_ns,
            state="readable",
            fingerprint=outcome.fingerprint,
            document_id=document.document_id,
            format_version=document.format_version,
            media_length=document.media_length,
            time_unit=document.time_unit,
            time_map=tmap,
            keys=tuple(keys.handed),
        )
        return record, rows.at(found.path, outcome.fingerprint)

    def _unreadable(self, outcome: Outcome, key: int) -> tuple[FileRecord, Rows]:
        """The record and rows of a file that couldn't be read, under
        ``key``."""
        found = outcome.found
        record = FileRecord(
            key=key,
            path=found.path,
            native=found.native,
            size=found.size,
            mtime_ns=found.mtime_ns,
            read_at_ns=outcome.read_at_ns,
            state="unreadable",
            reason=outcome.reason,
            line=outcome.line,
            os_error=outcome.os_error,
            keys=(key,),
        )
        return record, file_row(key, found.path, "unreadable", outcome.reason)

    def build(self) -> ScanReport:
        """Read every file of the folder and fill the empty index with their
        rows: the index's first generation, 1 (0 while it is empty). Listing the corpus
        folder itself may raise ``OSError``; nothing inside it does."""
        found = walk(self.root, self.reader, self.settings)
        before = self.store.generation
        records: dict[str, FileRecord] = {}
        inserts: list[Rows] = []
        maps: dict[int, TimeMap | None] = {}
        unreadable: list[tuple[str, int | None, str]] = []
        for f in found:  # sorted by path: the same folder gives the same keys
            outcome = read_file(self.reader, f)
            key = next(self._counter)
            if outcome.readable:
                record, rows = self._readable(outcome, key)
                maps[key] = record.time_map
            else:
                record, rows = self._unreadable(outcome, key)
                unreadable.append((f.path, outcome.line, outcome.reason or ""))
                LOG.warning("%s is unreadable: %s", f.native, outcome.reason)
            records[f.path] = record
            inserts.append(rows)
        error = None
        if inserts:
            err = self.store.apply([], inserts, maps)
            error = None if err is None else str(err)
        if error is None:
            self.records = records
        else:
            records, unreadable = {}, []
        return ScanReport(
            added=tuple(records),
            changed=(),
            moved=(),
            unavailable=(),
            back=(),
            unreadable=tuple(unreadable),
            shared_ids=tuple(shared_ids(records)),
            generation_before=before,
            generation_after=self.store.generation,
            error=error,
        )
