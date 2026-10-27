"""A corpus's index: one SQLite database in memory, read through a pool of
connections, under a readers-writer lock (research R2, R3;
contracts/index-reader.md).

- **The database** is a named shared-cache database in memory. The store keeps
  the writer's connection open for its lifetime, so the database lives as long
  as the store; only changes use it.
- **Reads** borrow a connection from a pool: a thread's outermost
  :meth:`Store.reading` takes an idle one, or opens one when none is idle, and
  reads nested in it share it. When the outermost read ends, the connection
  goes back without a progress handler or an authorizer. The pool holds as
  many connections as the most reads that ran at once.
- **Changes** (:meth:`Store.apply`) take the write side: they wait for the
  running reads, apply everything in one transaction and move the generation
  when anything changed. Every read sees one generation from start to end.
- **Connections are closed only by** :meth:`Store.close`, under the write side.
  On Python 3.10, closing a connection while another thread runs a statement
  that calls a Python function deadlocks, and the garbage collector closes a
  dropped connection the same way; so the pool never drops one, and never
  keeps one per thread.
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
import sys
import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from . import schema
from .build import Rows
from .time_map import TimeMap

LOG = logging.getLogger(__name__)

PATIENCE = 2.0
"""Seconds a change waits before new reads wait for it, and that ``apply``
retries a lock error for."""
RETRY_PAUSE = 0.02  # seconds between two tries of a locked change

# The tables that hold a file's rows, by how they reach its key: the kind
# tables, categories and positions by their component, fields by their owner.
_DELETE = (
    "DELETE FROM {table} WHERE component_id IN "
    "(SELECT id FROM components WHERE file_id = ?)"
)
_BY_COMPONENT = ("hierarchies", "ranges", "chords", "keys", "categories", "positions")
_DELETE_FIELDS = (
    "DELETE FROM fields WHERE (scope = 'file' AND owner_id = ?1) "
    "OR (scope = 'timeline' AND owner_id IN "
    "(SELECT id FROM timelines WHERE file_id = ?1)) "
    "OR (scope = 'component' AND owner_id IN "
    "(SELECT id FROM components WHERE file_id = ?1))"
)


def _allow_all(*args: Any) -> int:
    return sqlite3.SQLITE_OK


def _remove_authorizer(con: sqlite3.Connection) -> None:
    """Take the authorizer off ``con``. Python before 3.11 can't clear it with
    None, so a callback that allows everything stands in (as
    ``tql.readonly._remove_authorizer`` does)."""
    con.set_authorizer(None if sys.version_info >= (3, 11) else _allow_all)


def _is_lock_error(err: sqlite3.Error) -> bool:
    text = str(err).lower()
    return isinstance(err, sqlite3.OperationalError) and "locked" in text


class Reading:
    """One read: its connection, the generation it sees from start to end,
    whether the corpus folder can be reached, and the files' time maps of that
    generation. ``connection`` works only in the thread that opened the read."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        generation: int,
        available: bool,
        time_maps: Mapping[int, TimeMap],
    ) -> None:
        self._connection = connection
        self._thread = threading.get_ident()
        self.generation = generation
        self.available = available
        self._time_maps = time_maps

    @property
    def connection(self) -> sqlite3.Connection:
        """This read's connection. Raises ``RuntimeError`` in any thread but
        the one that opened the read: two threads on one connection would
        replace each other's progress handler and authorizer."""
        if threading.get_ident() != self._thread:
            raise RuntimeError(
                "a read's connection belongs to the thread that opened the read"
            )
        return self._connection

    def time_map(self, file_id: int) -> TimeMap | None:
        """The time map of the file whose key is ``file_id``, None without
        one."""
        return self._time_maps.get(file_id)


class Store:
    """One corpus's index. ``reading()`` reads it, ``apply`` changes it,
    ``close()`` ends it."""

    def __init__(self) -> None:
        self._uri = f"file:tilia-corpus-{secrets.token_hex(8)}?mode=memory&cache=shared"
        self._writer = sqlite3.connect(
            self._uri, uri=True, check_same_thread=False, isolation_level=None
        )
        schema.create_schema(self._writer)
        self._cond = threading.Condition(threading.Lock())
        self._connections: list[sqlite3.Connection] = []  # every one opened
        self._idle: list[sqlite3.Connection] = []
        self._reads: dict[int, tuple[Reading, int]] = {}  # thread -> (read, depth)
        self._writer_thread: int | None = None
        self._waiting: dict[int, float] = {}  # a waiting change's thread -> since
        self._generation = 0
        self._time_maps: dict[int, TimeMap] = {}
        self._closed = False
        self.available = True
        """False while the corpus folder can't be reached (FR-021); reads that
        start then say so."""

    # -- reads ---------------------------------------------------------------- #
    @property
    def generation(self) -> int:
        """The generation of the index: 0 while it is empty, one more with every
        change that changed something."""
        return self._generation

    @property
    def connections(self) -> int:
        """How many read connections the store has opened (its pool)."""
        with self._cond:
            return len(self._connections)

    @contextmanager
    def reading(self) -> Iterator[Reading]:
        """Hold the read side for the block, and give a :class:`Reading`.

        A read nested in another on the same thread takes nothing new: it
        shares the connection and never waits, even behind a waiting change.
        Statements must not outlive the block: read cursors to the end."""
        me = threading.get_ident()
        with self._cond:
            if self._closed:
                raise RuntimeError("the index is closed")
            held = self._reads.get(me)
            if held is not None:
                self._reads[me] = (held[0], held[1] + 1)
                read = held[0]
            else:
                while self._writer_thread is not None or self._change_has_waited():
                    self._cond.wait()
                    if self._closed:
                        raise RuntimeError("the index is closed")
                con = self._idle.pop() if self._idle else self._open()
                read = Reading(con, self._generation, self.available, self._time_maps)
                self._reads[me] = (read, 1)
        try:
            yield read
        finally:
            self._end_read(me)

    def connection(self) -> sqlite3.Connection:
        """The connection of the calling thread's read. Raises
        ``RuntimeError`` outside :meth:`reading`."""
        with self._cond:
            held = self._reads.get(threading.get_ident())
        if held is None:
            raise RuntimeError("connection() works only inside reading()")
        return held[0].connection

    def time_map(self, file_id: int) -> TimeMap | None:
        """The time map of the file whose key is ``file_id``, in the current
        generation."""
        return self._time_maps.get(file_id)

    def _change_has_waited(self) -> bool:
        """Whether a change has waited longer than ``PATIENCE``: then new reads
        wait for it."""
        if not self._waiting:
            return False
        return time.monotonic() - min(self._waiting.values()) > PATIENCE

    def _open(self) -> sqlite3.Connection:
        """A new read connection, in the pool from the moment it is opened."""
        con = sqlite3.connect(self._uri, uri=True, check_same_thread=False)
        self._connections.append(con)
        return con

    def _end_read(self, me: int) -> None:
        with self._cond:
            read, depth = self._reads[me]
            if depth > 1:
                self._reads[me] = (read, depth - 1)
                return
            del self._reads[me]
            con = read._connection
            # leave it as it was found, for the next read of any thread
            con.set_progress_handler(None, 0)
            _remove_authorizer(con)
            con.row_factory = None
            self._idle.append(con)
            self._cond.notify_all()

    # -- changes -------------------------------------------------------------- #
    @contextmanager
    def _write_side(self) -> Iterator[None]:
        me = threading.get_ident()
        with self._cond:
            if me in self._reads:
                raise RuntimeError(
                    "a change can't start inside a read on the same thread: it "
                    "would wait for that read forever"
                )
            if self._closed:
                raise RuntimeError("the index is closed")
            self._waiting[me] = time.monotonic()
            try:
                while self._writer_thread is not None or self._reads:
                    self._cond.wait()
                    if self._closed:
                        raise RuntimeError("the index is closed")
            finally:
                del self._waiting[me]
            self._writer_thread = me
        try:
            yield
        finally:
            with self._cond:
                self._writer_thread = None
                self._cond.notify_all()

    def apply(
        self,
        rows_to_delete: Iterable[int],
        rows_to_insert: Iterable[Rows],
        time_maps: Mapping[int, TimeMap | None] | None = None,
    ) -> sqlite3.Error | None:
        """Apply one change in one transaction, under the write side: delete
        every row of the files whose keys are in ``rows_to_delete``, then insert
        ``rows_to_insert`` (each a :class:`~tilia_core.corpus.build.Rows`, which
        may hold only a file's row). ``time_maps`` gives the time maps of the
        files it names (None: the file has none).

        The generation goes up when anything changed. A lock error, such as a
        statement left open after a read, is retried for up to ``PATIENCE``
        seconds; then the transaction is rolled back, and the error logged and
        returned: nothing changed, neither the rows nor the generation nor the
        time maps. Returns None when the change was applied."""
        deletes = list(rows_to_delete)
        inserts = list(rows_to_insert)
        with self._write_side():
            deadline = time.monotonic() + PATIENCE
            while True:
                try:
                    changed = self._transaction(deletes, inserts)
                    break
                except sqlite3.Error as err:
                    if self._writer.in_transaction:
                        self._writer.execute("ROLLBACK")
                    if _is_lock_error(err) and time.monotonic() < deadline:
                        time.sleep(RETRY_PAUSE)
                        continue
                    LOG.error("the index couldn't be changed: %s", err)
                    return err
            if changed:
                self._generation += 1
            if time_maps:
                maps = dict(self._time_maps)  # reads keep the maps they started with
                for file_id, tmap in time_maps.items():
                    if tmap is None:
                        maps.pop(file_id, None)
                    else:
                        maps[file_id] = tmap
                self._time_maps = maps
        return None

    def _transaction(self, deletes: list[int], inserts: list[Rows]) -> bool:
        """Run the change in one transaction; whether it changed any row."""
        con = self._writer
        before = con.total_changes
        con.execute("BEGIN")
        for file_id in deletes:
            for table in _BY_COMPONENT:
                con.execute(_DELETE.format(table=table), (file_id,))
            con.execute(_DELETE_FIELDS, (file_id,))
            con.execute("DELETE FROM measures WHERE file_id = ?", (file_id,))
            con.execute("DELETE FROM components WHERE file_id = ?", (file_id,))
            con.execute("DELETE FROM timelines WHERE file_id = ?", (file_id,))
            con.execute("DELETE FROM files WHERE id = ?", (file_id,))
        for rows in inserts:
            for table, found in rows.tables().items():
                if found:
                    marks = ", ".join("?" for _ in found[0])
                    con.executemany(f"INSERT INTO {table} VALUES ({marks})", found)
        con.execute("COMMIT")
        return con.total_changes != before

    # -- the end -------------------------------------------------------------- #
    def close(self) -> None:
        """Close every connection, the pool's and then the writer's, once no
        read is running: the database is gone. Raises ``RuntimeError`` inside a
        read; a second ``close()`` does nothing. After it, reads and changes
        raise ``RuntimeError``."""
        with self._cond:
            if self._closed:
                return
        try:
            with self._write_side():
                for con in self._connections:
                    con.close()
                self._writer.close()
                with self._cond:
                    self._closed = True
                    self._idle.clear()
        except RuntimeError:
            with self._cond:
                if self._closed:
                    return  # another thread closed it meanwhile
            raise
