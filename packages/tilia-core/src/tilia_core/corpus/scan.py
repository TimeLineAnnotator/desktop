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
- **The scan** (:meth:`Scanner.scan`; research R7-R9; data-model.md, "File
  states") reads again the files whose size or date differ, racy files and
  files that couldn't be opened; compares them by fingerprint; recognises
  moves and copies by document id; and marks missing files unavailable. The
  change goes through one ``Store.apply``, and the records follow only once it
  is applied. A corpus folder that can't be reached changes nothing (FR-021).
  Scans take turns under :attr:`Scanner.turn`, the change mutex.

Nothing here writes to the corpus folder (FR-072).
"""

from __future__ import annotations

import itertools
import logging
import os
import stat
import sys
import threading
import time
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
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

clock: Callable[[], float] = time.monotonic
"""The clock that dates scans (tests replace it)."""


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


RACY_NS = 2_000_000_000
"""A file whose modification time lies within this many nanoseconds of its
latest read, in either direction, is read again at the next scan (research
R7)."""


def is_racy(record: FileRecord) -> bool:
    """Whether ``record``'s modification time lies within 2 s of its latest
    read: then a change within the file system's time resolution could hide
    behind an unchanged size and date."""
    if record.mtime_ns is None or record.read_at_ns is None:
        return False
    return abs(record.mtime_ns - record.read_at_ns) <= RACY_NS


def needs_reading(record: FileRecord | None, found: Found) -> bool:
    """Whether a scan reads ``found`` again: a new file, one that couldn't be
    opened or read (``os_error``), a racy one, and any whose size or
    modification time differ, newer or older; so one unavailable until now,
    whose record has neither."""
    if record is None or record.os_error:
        return True
    if (record.size, record.mtime_ns) != (found.size, found.mtime_ns):
        return True
    return is_racy(record)


class Turn:
    """A re-entrant mutex that knows its holder and how many wait for it."""

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._owner: int | None = None
        self._depth = 0
        self.waiting = 0
        """How many threads wait to take it."""

    def held_by_me(self) -> bool:
        with self._cond:
            return self._owner == threading.get_ident()

    def __enter__(self) -> Turn:
        me = threading.get_ident()
        with self._cond:
            if self._owner == me:
                self._depth += 1
                return self
            self.waiting += 1
            try:
                while self._owner is not None:
                    self._cond.wait()
            finally:
                self.waiting -= 1
            self._owner, self._depth = me, 1
        return self

    def __exit__(self, *exc: object) -> None:
        with self._cond:
            self._depth -= 1
            if self._depth == 0:
                self._owner = None
                self._cond.notify()


class _Job:
    """A running scan, which other threads' calls share."""

    def __init__(self, thread: int) -> None:
        self.thread = thread
        self.done = threading.Event()
        self.report: ScanReport | None = None
        self.error: BaseException | None = None
        self.waiters = 0


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
        self.turn = Turn()
        """The change mutex: scans take turns with each other, and with
        rereads and the core's own writes (research R2)."""
        self.last_scan: float | None = None
        """When the last scan began, by :data:`clock`."""
        self._jobs = threading.Lock()
        self._job: _Job | None = None

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
        rows: its first generation, 1 (0 while it is empty). Listing the corpus
        folder itself may raise ``OSError``; nothing inside it does."""
        with self.turn:
            self.last_scan = clock()
            return self._refresh(walk(self.root, self.reader, self.settings))

    # -- scans ---------------------------------------------------------------- #
    def scan(self) -> ScanReport:
        """Bring the index in line with the folder, and say what changed.

        Calls from several threads at once share one scan: a call that finds
        another thread's scan running waits for it and returns its report."""
        me = threading.get_ident()
        with self._jobs:
            job = self._job
            if job is not None and job.thread != me and not self.turn.held_by_me():
                job.waiters += 1
                shared: _Job | None = job
            else:
                shared = None
                if job is None:
                    job = self._job = _Job(me)
                else:
                    job = None  # this thread's own turn, nested
        if shared is not None:
            shared.done.wait()
            if shared.error is not None:
                raise shared.error
            assert shared.report is not None
            return shared.report
        try:
            with self.turn:
                report = self._scan()
            if job is not None:
                job.report = report
            return report
        except BaseException as err:
            if job is not None:
                job.error = err
            raise
        finally:
            if job is not None:
                with self._jobs:
                    self._job = None
                job.done.set()

    def _scan(self) -> ScanReport:
        """One scan, under the change mutex."""
        self.last_scan = clock()
        try:
            found = walk(self.root, self.reader, self.settings)
        except OSError as err:
            # the corpus folder itself can't be reached: change nothing (FR-021)
            if self.store.available:
                LOG.warning("the corpus folder %s can't be reached: %s", self.root, err)
            self.store.available = False
            generation = self.store.generation
            return ScanReport((), (), (), (), (), (), (), generation, generation)
        if not self.store.available:
            LOG.warning("the corpus folder %s can be reached again", self.root)
        self.store.available = True
        return self._refresh(found)

    def _refresh(
        self,
        found: list[Found],
        scope: set[str] | None = None,
        force: frozenset[str] = frozenset(),
    ) -> ScanReport:
        """Bring the records and the index in line with ``found``: the whole
        folder, or, with ``scope``, only those paths. Files in ``force`` are
        read whatever their size and date. The records change only once the
        change is applied (research R2)."""
        before = self.store.generation
        old = self.records
        here = {f.path: f for f in found}
        outcomes = {
            f.path: read_file(self.reader, f)
            for f in found
            if f.path in force or needs_reading(old.get(f.path), f)
        }
        vanished = [
            rec
            for path, rec in sorted(old.items())
            if path not in here
            and rec.state != "unavailable"
            and (scope is None or path in scope)
        ]
        new = dict(old)
        deletes: list[int] = []
        inserts: list[Rows] = []
        maps: dict[int, TimeMap | None] = {}
        added: list[str] = []
        changed: list[str] = []
        moved: list[tuple[str, str]] = []
        gone: list[str] = []
        back: list[str] = []
        unreadable: list[tuple[str, int | None, str]] = []

        def put(record: FileRecord, rows: Rows, replaces: FileRecord | None) -> None:
            if replaces is not None:
                deletes.append(replaces.key)
                if replaces.path != record.path:
                    new.pop(replaces.path, None)
            new[record.path] = record
            inserts.append(rows)
            maps[record.key] = record.time_map

        # moves: a vanished file whose document id a new file has (research R9)
        fresh = [p for p in sorted(outcomes) if p not in old]
        claims: dict[str, FileRecord] = {}

        def claim(records: list[FileRecord]) -> None:
            for rec in records:
                if rec.document_id is None:
                    continue
                same_id = [
                    p
                    for p in fresh
                    if p not in claims
                    and outcomes[p].document is not None
                    and outcomes[p].document.document_id == rec.document_id
                ]
                same_content = [
                    p for p in same_id if outcomes[p].fingerprint == rec.fingerprint
                ]
                if same_id:
                    claims[(same_content or same_id)[0]] = rec

        claim([r for r in vanished if r.state == "readable"])
        if scope is None:  # unavailable files found again elsewhere
            claim(
                [
                    r
                    for path, r in sorted(old.items())
                    if r.state == "unavailable" and path not in here
                ]
            )

        for path in sorted(outcomes):  # new keys in path order
            o = outcomes[path]
            rec = claims.get(path) or old.get(path)
            if rec is None:
                key = next(self._counter)
                if o.readable:
                    put(*self._readable(o, key), None)
                else:
                    put(*self._unreadable(o, key), None)
                    unreadable.append((path, o.line, o.reason or ""))
                    LOG.warning("%s is unreadable: %s", o.found.native, o.reason)
                added.append(path)
                continue
            is_move = path in claims
            if is_move:
                moved.append((rec.path, path))
            if rec.state == "unavailable":
                back.append(path)
            if o.readable:
                assert o.document is not None
                same = rec.state == "readable" and o.fingerprint == rec.fingerprint
                newer = o.document.format_version != rec.format_version
                if same and not newer and not is_move:
                    new[path] = replace(
                        rec,
                        native=o.found.native,
                        size=o.found.size,
                        mtime_ns=o.found.mtime_ns,
                        read_at_ns=o.read_at_ns,
                        os_error=False,
                    )
                    continue
                # the same content keeps its rows' keys
                put(*self._readable(o, rec.key, rec.keys if same else ()), rec)
                if rec.state != "unavailable" and (not same or newer):
                    changed.append(path)
            else:
                if rec.state == "unreadable" and rec.reason == o.reason:
                    new[path] = replace(
                        rec,
                        native=o.found.native,
                        size=o.found.size,
                        mtime_ns=o.found.mtime_ns,
                        read_at_ns=o.read_at_ns,
                        os_error=o.os_error,
                    )
                    continue
                put(*self._unreadable(o, rec.key), rec)
                unreadable.append((path, o.line, o.reason or ""))
                LOG.warning("%s is unreadable: %s", o.found.native, o.reason)

        taken = {r.path for r in claims.values()}
        for rec in vanished:
            if rec.path in taken:
                continue
            if rec.state == "readable":
                # a copy indexed earlier, and the original gone: moved onto it
                targets = [
                    p
                    for p, r in sorted(new.items())
                    if p in old
                    and p in here
                    and r.state == "readable"
                    and r.document_id == rec.document_id
                ]
                if targets:
                    same_content = [
                        p for p in targets if new[p].fingerprint == rec.fingerprint
                    ]
                    new.pop(rec.path)
                    deletes.append(rec.key)
                    maps[rec.key] = None
                    moved.append((rec.path, (same_content or targets)[0]))
                    continue
            kept = rec if rec.state == "readable" else None
            record = FileRecord(
                key=rec.key,
                path=rec.path,
                native=rec.native,
                size=None,
                mtime_ns=None,
                read_at_ns=rec.read_at_ns,
                state="unavailable",
                fingerprint=kept.fingerprint if kept else None,
                document_id=kept.document_id if kept else None,
                format_version=kept.format_version if kept else None,
                media_length=kept.media_length if kept else None,
                time_unit=kept.time_unit if kept else None,
                keys=(rec.key,),
            )
            put(record, file_row(rec.key, rec.path, "unavailable", None, kept), rec)
            gone.append(rec.path)
            LOG.warning("%s is unavailable", rec.native)

        if deletes or inserts:
            err = self.store.apply(deletes, inserts, maps)
            if err is not None:
                after = self.store.generation
                return ScanReport((), (), (), (), (), (), (), before, after, str(err))
        self.records = new
        new_paths = set(added)
        return ScanReport(
            added=tuple(added),
            changed=tuple(sorted(changed)),
            moved=tuple(sorted(moved)),
            unavailable=tuple(gone),
            back=tuple(sorted(back)),
            unreadable=tuple(unreadable),
            shared_ids=tuple(g for g in shared_ids(new) if new_paths.intersection(g)),
            generation_before=before,
            generation_after=self.store.generation,
        )
