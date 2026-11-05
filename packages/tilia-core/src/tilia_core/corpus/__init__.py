"""Corpora: a folder of TiLiA files, its index in memory, and the scan that keeps
the index true to the files.

``open_corpus(folder)`` reads every file of the folder and builds the index; the
corpus it returns goes straight to ``tql.run``, ``tql.sql`` and the statistics
(contracts/corpus.md, contracts/index-reader.md). Nothing in this package writes,
moves or deletes a file of a corpus, or creates anything in its folder.
"""

from __future__ import annotations

import errno
import os
import stat
import sqlite3
import threading
import unicodedata
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

from . import schema
from .documents import DocumentReader
from .fingerprint import NO_READER
from .fingerprint import of_path as fingerprint
from .scan import RESCAN_AFTER, ScanReport, Scanner
from .settings import CorpusSettings, NoSettings
from .store import Reading, Store
from .time_map import TimeMap, TimeMapOf

__all__ = [
    "open_corpus",
    "fingerprint",
    "Corpus",
    "ScanReport",
    "FileRow",
    "TimelineRow",
    "FileDetail",
    "ComponentRow",
]


@dataclass(frozen=True)
class FileRow:
    """A file the corpus has seen in this run (``files``). ``fields`` are the
    file's fields, by name, and ``timeline_kinds`` how many timelines of each
    kind it has; both are empty for an unreadable or unavailable file, which
    has no rows but this one."""

    id: int
    path: str
    document_id: str | None
    state: str
    reason: str | None
    format_version: str | None
    fingerprint: str | None
    fields: dict[str, tuple[str, ...]]
    timeline_kinds: dict[str, int]


@dataclass(frozen=True)
class TimelineRow:
    """A timeline of a file (``timelines``), with its fields by name."""

    id: int
    uuid: str
    kind: str
    name: str
    ordinal: int
    role: str | None
    author: str | None
    fields: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class FileDetail:
    """A file, and its timelines in ordinal order."""

    file: FileRow
    timelines: tuple[TimelineRow, ...]


@dataclass(frozen=True)
class ComponentRow:
    """One unit: what every unit has, and in ``properties`` its row in its
    kind's own table (``schema.KIND_TABLES``), by column and without
    ``component_id``, and its ``color`` when it has one. A point (a marker, a
    beat) has ``start == end``."""

    id: int
    timeline_id: int
    uuid: str
    kind: str
    start: float
    end: float
    label: str
    properties: dict[str, Any]


def _fields(
    rows: Iterable[tuple[Any, str, str]]
) -> dict[Any, dict[str, tuple[str, ...]]]:
    """``(owner, name, value)`` rows, by owner, then by name."""
    out: dict[Any, dict[str, list[str]]] = {}
    for owner, name, value in rows:
        out.setdefault(owner, {}).setdefault(name, []).append(value)
    return {o: {n: tuple(v) for n, v in by.items()} for o, by in out.items()}


def _marks(n: int) -> str:
    return ", ".join("?" for _ in range(n))


class Corpus:
    """A folder of TiLiA files and its index. It is an index reader
    (contracts/index-reader.md): pass it to ``tql.run``, ``tql.sql`` and the
    statistics as it is. Every member may be called from any thread."""

    def __init__(
        self,
        path: Path,
        scanner: Scanner,
        report: ScanReport,
        rescan_before_reads: bool,
    ) -> None:
        self.path = path
        """The resolved corpus folder."""
        self._scanner = scanner
        self._store: Store = scanner.store
        self.open_report = report
        """The report of the first build: every file in ``added``, the
        unreadable ones, and every group of copies in ``shared_ids``."""
        self.rescan_before_reads = rescan_before_reads
        self._lock = threading.Lock()
        self._reads: dict[int, int] = {}  # thread -> how deep in reads

    # -- the index reader ------------------------------------------------------ #
    @property
    def available(self) -> bool:
        """False while the corpus folder is missing or can't be reached: the
        index keeps the files as last read (FR-021)."""
        return self._store.available

    @property
    def generation(self) -> int:
        """The index's generation: 1 once the first build filled it, one more
        with every change."""
        return self._store.generation

    def _in_read(self) -> bool:
        with self._lock:
            return threading.get_ident() in self._reads

    @contextmanager
    def reading(self) -> Iterator[Reading]:
        """Hold the read side for the block, and give the read's connection,
        generation, availability and time maps (contracts/index-reader.md).

        A corpus opened with ``rescan_before_reads`` first rescans when its
        last scan began more than 2 s ago (FR-024); readers that arrive while
        that rescan runs wait for it, and share it. A read nested in another,
        or on a thread that holds the change mutex, doesn't rescan."""
        me = threading.get_ident()
        if (
            self.rescan_before_reads
            and not self._in_read()
            and not self._scanner.turn.held_by_me()
        ):
            self._scanner.scan(older_than=RESCAN_AFTER)
        with self._store.reading() as read:
            with self._lock:
                self._reads[me] = self._reads.get(me, 0) + 1
            try:
                yield read
            finally:
                with self._lock:
                    depth = self._reads.pop(me) - 1
                    if depth:
                        self._reads[me] = depth

    def connection(self) -> sqlite3.Connection:
        """The connection of the calling thread's read; raises
        ``RuntimeError`` outside :meth:`reading`."""
        return self._store.connection()

    def time_map(self, file_id: int) -> TimeMap | None:
        """The time map of the file whose key is ``file_id``, None without
        one."""
        return self._store.time_map(file_id)

    # -- changes --------------------------------------------------------------- #
    def _no_change_inside_a_read(self, what: str) -> None:
        if self._in_read():
            raise RuntimeError(
                f"{what} can't start inside a read on the same thread: it would "
                "wait for that read forever"
            )

    def scan(self) -> ScanReport:
        """Bring the index in line with the folder, and report what changed
        (data-model.md, "The scan report"); the generation moves only when
        anything did. Concurrent calls share one scan. Raises
        ``RuntimeError`` inside a read on the same thread."""
        self._no_change_inside_a_read("a scan")
        report = self._scanner.scan()
        assert report is not None
        return report

    def _member(self, path: str | os.PathLike) -> tuple[str, Path]:
        """The relative path, in NFC, and the native path of ``path``, a file
        of the corpus, relative to its folder or as given. Raises
        ``ValueError`` for a path outside the folder, or one the walk would
        leave out."""
        given = Path(path)
        native = (given if given.is_absolute() else self.path / given).resolve()
        try:
            parts = native.relative_to(self.path).parts
        except ValueError:
            raise ValueError(f"{path} is outside the corpus {self.path}") from None
        rel = unicodedata.normalize("NFC", "/".join(parts))
        reader = self._scanner.reader
        name = parts[-1] if parts else ""
        endings = tuple(e.lower() for e in reader.extensions)
        if (
            not parts
            or any(part.startswith(".") for part in parts)
            or not name.lower().endswith(endings)
            or reader.is_temporary(name)
            or not self._scanner.settings.includes(rel)
            or native.is_dir()
        ):
            raise ValueError(f"{path} is not a file of the corpus {self.path}")
        return rel, native

    def reread(self, path: str | os.PathLike) -> ScanReport:
        """Read one file at once, without scanning the rest: a TiLiA window
        saved it (FR-020). A new file of the corpus is added, and a missing one
        becomes unavailable. ``path`` is relative to the corpus folder, or as
        given. Raises ``ValueError`` for a path outside the corpus, and
        ``RuntimeError`` inside a read on the same thread."""
        self._no_change_inside_a_read("a reread")
        rel, native = self._member(path)
        return self._scanner.reread(rel, native)

    @contextmanager
    def writing(self) -> Iterator[None]:
        """Hold the corpus for a writer (WP14) around its atomic write and
        :meth:`written`: it waits for a running scan or reread, and while it
        is held, scans and rereads of other threads wait, and reads on this
        thread don't rescan (research R2, R11). It is re-entrant. Raises
        ``RuntimeError`` inside a read on the same thread."""
        self._no_change_inside_a_read("writing()")
        with self._scanner.turn:
            yield

    def written(
        self, path: str | os.PathLike, fingerprint: str | None = None
    ) -> ScanReport:
        """Record the core's own write of the file at ``path``: the index
        reads it again at once and records it, moving the generation only if
        its content changed (FR-030), so the next scan doesn't report it.
        ``fingerprint`` is the one the writer wrote: when the file's differs,
        the index keeps what is on disk, and logs it. Raises ``ValueError``
        for a path outside the corpus, and ``RuntimeError`` inside a read on
        the same thread."""
        self._no_change_inside_a_read("written()")
        rel, native = self._member(path)
        return self._scanner.written(rel, native, fingerprint)

    # -- the files and their units ------------------------------------------- #
    def _file_rows(
        self, con: sqlite3.Connection, where: str, args: tuple
    ) -> list[FileRow]:
        found = con.execute(
            "SELECT id, path, document_id, state, reason, format_version, "
            f"fingerprint FROM files {where} ORDER BY path",
            args,
        ).fetchall()
        if not found:
            return []
        ids = [r[0] for r in found]
        fields = _fields(
            con.execute(
                "SELECT owner_id, name, value FROM fields WHERE scope = 'file' "
                f"AND owner_id IN ({_marks(len(ids))}) ORDER BY rowid",
                ids,
            )
        )
        kinds: dict[int, dict[str, int]] = {}
        for file_id, kind, n in con.execute(
            "SELECT file_id, kind, count(*) FROM timelines "
            f"WHERE file_id IN ({_marks(len(ids))}) GROUP BY file_id, kind "
            "ORDER BY file_id, min(ordinal)",
            ids,
        ):
            kinds.setdefault(file_id, {})[kind] = n
        return [
            FileRow(
                *row,
                fields=fields.get(row[0], {}),
                timeline_kinds=kinds.get(row[0], {}),
            )
            for row in found
        ]

    def files(self) -> list[FileRow]:
        """Every file seen in this run, sorted by path."""
        with self.reading() as r:
            return self._file_rows(r.connection, "", ())

    def _relative(self, path: str | os.PathLike) -> str | None:
        p = Path(path)
        if p.is_absolute():
            try:
                p = p.resolve().relative_to(self.path)
            except ValueError:
                return None
        return unicodedata.normalize("NFC", "/".join(p.parts))

    def file(self, path: str | os.PathLike) -> FileRow | None:
        """One file's row, by its path relative to the corpus folder or as
        given; None for a file the corpus hasn't seen."""
        rel = self._relative(path)
        if rel is None:
            return None
        with self.reading() as r:
            rows = self._file_rows(r.connection, "WHERE path = ?", (rel,))
        return rows[0] if rows else None

    def file_detail(self, file_id: int) -> FileDetail:
        """One file and its timelines. Raises ``KeyError`` for a key the
        index doesn't hold."""
        with self.reading() as r:
            con = r.connection
            rows = self._file_rows(con, "WHERE id = ?", (file_id,))
            if not rows:
                raise KeyError(f"no file with the key {file_id}")
            timelines = con.execute(
                "SELECT id, uuid, kind, name, ordinal, role, author FROM timelines "
                "WHERE file_id = ? ORDER BY ordinal",
                (file_id,),
            ).fetchall()
            fields = _fields(
                con.execute(
                    "SELECT owner_id, name, value FROM fields WHERE scope = 'timeline' "
                    "AND owner_id IN (SELECT id FROM timelines WHERE file_id = ?) "
                    "ORDER BY rowid",
                    (file_id,),
                )
            )
        return FileDetail(
            file=rows[0],
            timelines=tuple(
                TimelineRow(*t, fields=fields.get(t[0], {})) for t in timelines
            ),
        )

    def components(
        self, file_id: int, timeline_ids: Iterable[int]
    ) -> list[ComponentRow]:
        """The units of those timelines of one file, in time order: what every
        unit has, and in ``properties`` its row in the table
        ``schema.KIND_TABLES`` gives for its kind and its colour, if any."""
        tids = list(timeline_ids)
        if not tids:
            return []
        chosen = f"file_id = ? AND timeline_id IN ({_marks(len(tids))})"
        args = (file_id, *tids)
        with self.reading() as r:
            con = r.connection
            units = con.execute(
                'SELECT id, timeline_id, uuid, kind, start, "end", label, color '
                f"FROM components WHERE {chosen} ORDER BY start, id",
                args,
            ).fetchall()
            properties: dict[int, dict[str, Any]] = {}
            for table in schema.KIND_TABLES.values():
                cur = con.execute(
                    f"SELECT * FROM {table} WHERE component_id IN "
                    f"(SELECT id FROM components WHERE {chosen})",
                    args,
                )
                names = [d[0] for d in cur.description]
                for row in cur:
                    values = dict(zip(names, row, strict=True))
                    properties[values.pop("component_id")] = values
        out = []
        for cid, tid, uuid, kind, start, end, label, color in units:
            props = properties.get(cid, {})
            if color is not None:
                props["color"] = color
            out.append(ComponentRow(cid, tid, uuid, kind, start, end, label, props))
        return out

    # -- the end --------------------------------------------------------------- #
    def close(self) -> None:
        """Close the index and every connection to it, once running reads have
        ended. A closed corpus raises on use; a second ``close()`` does
        nothing; ``close()`` inside a read raises ``RuntimeError``."""
        self._store.close()

    def __enter__(self) -> Corpus:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _naming(err: OSError, folder: Path) -> OSError:
    """``err``, or one of its type whose message names ``folder``."""
    if err.filename is not None:
        return err
    return type(err)(err.errno, err.strerror or str(err), str(folder))


def open_corpus(
    path: str | os.PathLike,
    *,
    rescan_before_reads: bool = True,
    reader: DocumentReader | None = None,
    settings: CorpusSettings | None = None,
    time_map_of: TimeMapOf | None = None,
) -> Corpus:
    """Open the folder ``path`` as a corpus: read every file below it and build
    its index (contracts/corpus.md).

    ``~`` is expanded and the path resolved. Raises ``FileNotFoundError`` for a
    path that doesn't exist, ``NotADirectoryError`` for a file, and the
    system's ``OSError`` for a folder it can't list; nothing inside the folder
    makes it raise: a file it can't read is listed as unreadable, and a
    subfolder it can't list is skipped. ``reader`` reads the files (WP3's, once
    it lands); ``settings`` are the corpus manifest's (none until WP15);
    ``time_map_of`` gives a file's time map (none until WP9)."""
    folder = Path(os.path.expanduser(os.fspath(path))).resolve()
    try:
        info = os.stat(folder)
    except FileNotFoundError as err:
        raise FileNotFoundError(errno.ENOENT, "no such folder", str(folder)) from err
    if not stat.S_ISDIR(info.st_mode):
        message = f"{folder} is a file, not a folder"
        if folder.suffix.lower() == ".tla":
            message += f"; to open the corpus it belongs to, open {folder.parent}"
        raise NotADirectoryError(errno.ENOTDIR, message, str(folder))
    if reader is None:
        raise NotImplementedError(NO_READER)
    store = Store()
    scanner = Scanner(folder, store, reader, settings or NoSettings(), time_map_of)
    try:
        report = scanner.build()
    except OSError as err:
        store.close()
        named = _naming(err, folder)
        if named is err:
            raise
        raise named from err
    return Corpus(folder, scanner, report, rescan_before_reads)
