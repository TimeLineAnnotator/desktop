"""The SQL functions TQL's statements call, registered on a connection.

``text REGEXP pattern`` is ``regexp(pattern, text)``; ``tql_fold`` and
``tql_color`` compare labels and colours the way the language does.
"""

from __future__ import annotations

import re
import sqlite3

from tilia_core import derived
from tilia_core.labels import fold, nfc


def regexp(pattern: str | None, text: str | None) -> int:
    """Whether ``pattern`` is found in ``text`` read in NFC; case-sensitive
    unless the pattern starts with ``(?i)``. No text is no match."""
    if pattern is None or text is None:
        return 0
    return 1 if re.search(pattern, nfc(str(text))) else 0


def tql_fold(text: str | None) -> str | None:
    """``text`` folded for comparing words and labels."""
    return None if text is None else fold(str(text))


def tql_color(text: str | None) -> str | None:
    """A colour as lower-case ``#rrggbb``, from a CSS name or a hex code."""
    return derived.color(text)


def register(con: sqlite3.Connection) -> None:
    """Register the functions on ``con``. Calling it again does nothing."""
    try:
        con.execute("SELECT tql_color(NULL)")
        return
    except sqlite3.OperationalError:
        pass
    con.create_function("regexp", 2, regexp, deterministic=True)
    con.create_function("tql_fold", 1, tql_fold, deterministic=True)
    con.create_function("tql_color", 1, tql_color, deterministic=True)
