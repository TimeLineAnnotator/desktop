"""A guard against two threads running on one connection."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

_lock = threading.Lock()
_held: dict[int, tuple[int, int]] = {}  # id(connection) -> (thread ident, depth)


@contextmanager
def in_use(con: sqlite3.Connection) -> Iterator[None]:
    """Mark ``con`` as in use by the calling thread for the block.

    A progress handler, an authorizer and the SQL functions belong to the
    connection, so an index reader must give each thread a connection of its
    own. A reader that gives two threads the same connection makes the second
    thread's call block inside sqlite3 with the GIL held, which stops the whole
    process. Entering while another thread holds the mark raises
    ``RuntimeError`` at once, without waiting and without touching ``con``. A
    nested entry on the thread that holds the mark passes.

    The dict of marks is the only state ``tql`` keeps across threads; it is
    empty whenever no call is running."""
    key = id(con)
    me = threading.get_ident()
    with _lock:
        held = _held.get(key)
        if held is not None and held[0] != me:
            raise RuntimeError(
                "another thread is running on this connection; an index reader "
                "must give each thread a connection of its own"
            )
        _held[key] = (me, 1 if held is None else held[1] + 1)
    try:
        yield
    finally:
        with _lock:
            depth = _held[key][1] - 1
            if depth:
                _held[key] = (me, depth)
            else:
                del _held[key]
