"""Read-only SQL on an index: :func:`sql` runs one statement of the user's.

The statement may only read. Two layers stop it before it changes anything:

- An authorizer set for the call allows SQLite's ``SELECT``, ``READ``,
  ``FUNCTION`` and ``RECURSIVE`` actions and refuses the rest when the
  statement is compiled (writes, ``ATTACH``, ``DETACH``, ``PRAGMA``,
  transactions, temporary tables, views and triggers, ``load_extension``).
- ``PRAGMA query_only`` is on for the call and put back as it was afterwards,
  so SQLite refuses a statement as soon as it starts to write: ``INSERT``,
  ``UPDATE``, ``DELETE``, ``CREATE`` (``TEMP`` too), ``DROP``, ``ALTER``,
  ``PRAGMA user_version = n`` and ``VACUUM INTO`` (which can still leave an
  empty file at its path). It lets ``ATTACH``, ``BEGIN`` and the pragmas that
  set the connection through, ``PRAGMA query_only = OFF`` among them: the
  authorizer alone refuses those.

Loading extensions is never enabled on the connection.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
import time
from typing import Any

from . import regexes, sqlfuncs
from .stats import Table
from .syntax import TQLError

ALLOWED = (
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
)
DENIED_FUNCTIONS = ("load_extension", "fts3_tokenizer")
CHECK_EVERY = 100  # SQLite virtual machine instructions between two checks


def _authorize(
    action: int, arg1: str | None, arg2: str | None, db: str | None, source: str | None
) -> int:
    """Allow what only reads (see the module docstring)."""
    if action not in ALLOWED:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in DENIED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _allow_all(*args: Any) -> int:
    return sqlite3.SQLITE_OK


def _remove_authorizer(con: sqlite3.Connection) -> None:
    """Take the authorizer off ``con``. Python before 3.11 cannot clear it with
    None, so a callback that allows everything stands in."""
    con.set_authorizer(None if sys.version_info >= (3, 11) else _allow_all)


class _Limits:
    """The progress handler of one call: what stopped it, once something has.
    It is also the call's budget for regular expressions (see
    :mod:`~tilia_core.tql.regexes`)."""

    def __init__(
        self, time_limit: float | None, cancel: threading.Event | None
    ) -> None:
        self.deadline = None if time_limit is None else time.monotonic() + time_limit
        self.cancel = cancel
        self.stopped: str | None = None

    def check(self) -> bool:
        """Whether the statement should stop; remember why."""
        if self.stopped is None:
            if self.cancel is not None and self.cancel.is_set():
                self.stopped = "cancelled"
            elif self.deadline is not None and time.monotonic() >= self.deadline:
                self.stopped = "time_limit"
        return self.stopped is not None

    def __call__(self) -> int:
        return 1 if self.check() else 0

    def seconds_left(self) -> float | None:
        """The time a regular expression may take, None if there is no limit."""
        if self.deadline is None:
            return None
        # not negative: regex reads a negative timeout as none at all
        return max(0.0, self.deadline - time.monotonic())

    def ran_out(self) -> None:
        """A regular expression reached the time limit."""
        if self.stopped is None:
            self.stopped = "time_limit"


def sql(
    index: Any,
    text: str,
    *,
    max_rows: int | None = None,
    time_limit: float | None = None,
    cancel: threading.Event | None = None,
) -> Table:
    """Run the one read-only statement ``text`` on ``index``.

    ``max_rows`` stops reading after that many rows, ``time_limit`` (seconds)
    and ``cancel`` (an event) stop a long statement; the rows read so far are
    returned and ``Table.stopped`` says why (``"max_rows"``, ``"time_limit"`` or
    ``"cancelled"``). A statement stopped before its first row returns no
    column names either (``columns == []``). A statement that SQLite refuses
    or that fails raises
    :class:`~tilia_core.tql.syntax.TQLError` with SQLite's message; nothing is
    ever written to the index.

    Both limits are checked between the steps of the statement, and one
    regular expression (``REGEXP``) is one step. With the ``regex`` package
    installed (``pip install "tilia-core[regex]"``) a regular expression is
    bounded by ``time_limit``, though not to the instant: the bound is
    approximate. ``cancel`` cannot interrupt a regular expression that is
    running; it takes effect once the expression ends. Without the ``regex``
    package, neither limit covers a regular expression, and a pattern that
    backtracks badly can hold the whole process."""
    con = index.connection()
    sqlfuncs.register(con, index)
    limits = _Limits(time_limit, cancel)
    columns: list[str] = []
    rows: list[tuple[Any, ...]] = []
    stopped: str | None = None
    in_transaction = con.in_transaction
    # The authorizer refuses PRAGMA: set query_only before it goes on and
    # restore it after it comes off.
    query_only = con.execute("PRAGMA query_only").fetchone()[0]
    con.execute("PRAGMA query_only = ON")
    con.set_authorizer(_authorize)
    con.set_progress_handler(limits, CHECK_EVERY)
    try:
        with regexes.within(limits):
            cursor = con.execute(text)
            try:
                if cursor.description is None:
                    raise TQLError("not a statement that reads")
                columns = [d[0] for d in cursor.description]
                while True:
                    if max_rows is not None and len(rows) >= max_rows:
                        if cursor.fetchone() is not None:
                            stopped = "max_rows"
                        break
                    row = cursor.fetchone()
                    if row is None:
                        break
                    rows.append(tuple(row))
                    if limits.check():
                        break
            finally:
                cursor.close()
    except TQLError:
        raise
    except (sqlite3.Error, sqlite3.Warning, ValueError) as err:
        # ValueError: text sqlite3 cannot pass on, such as a NUL character
        # (Python 3.10) or a lone surrogate (UnicodeEncodeError)
        if limits.stopped is None:
            raise TQLError(str(err)) from err
    finally:
        con.set_progress_handler(None, 0)
        _remove_authorizer(con)
        if con.in_transaction and not in_transaction:
            # Python's sqlite3 begins one before INSERT, UPDATE, DELETE and
            # REPLACE; if the authorizer let one of them through, query_only
            # refused its write and left the transaction open.
            con.rollback()
        con.execute(f"PRAGMA query_only = {int(query_only)}")
    return Table(columns, rows, stopped=stopped or limits.stopped)
