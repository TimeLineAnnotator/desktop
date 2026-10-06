"""The SQL functions TQL's statements call, registered on a connection.

``text REGEXP pattern`` is ``regexp(pattern, text)``; ``tql_fold`` and
``tql_color`` compare labels and colours the way the language does.
``tql_chord`` and ``tql_key`` read a literal as a chord or a key and ask whether
the columns of a ``chords`` or ``keys`` row match it (a literal that is none
matches nothing).
"""

from __future__ import annotations

import re
import sqlite3
from functools import lru_cache
from typing import Any

from tilia_core import derived, harmony
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


@lru_cache(maxsize=1024)
def chord_spec(text: str) -> harmony.ChordSpec | str:
    """The chord ``text`` names, or why it names none."""
    try:
        return harmony.parse_chord(text)
    except harmony.HarmonyError as exc:
        return str(exc)


@lru_cache(maxsize=1024)
def key_spec(text: str) -> harmony.KeySpec | str:
    """The key ``text`` names, or why it names none."""
    try:
        return harmony.parse_key(text)
    except harmony.HarmonyError as exc:
        return str(exc)


def tql_chord(
    literal: str | None,
    step: int | None,
    accidental: int | None,
    quality: str | None,
    inversion: int | None,
    applied_to: int | None,
    key_step: int | None,
    key_accidental: int | None,
    key_mode: str | None,
) -> int:
    """1 when the chord of these ``chords`` columns matches ``literal``, read in
    the key of the ``keys`` columns (C major when they are null); a literal that
    is no chord matches nothing."""
    if literal is None:
        return 0
    spec = chord_spec(literal)
    if isinstance(spec, str):
        return 0
    chord = dict(
        zip(
            _CHORD_COLUMNS,
            (step, accidental, quality, inversion, applied_to),
            strict=True,
        )
    )
    key = None if key_step is None else _mode((key_step, key_accidental, key_mode))
    return 1 if harmony.chord_matches(spec, chord, key or derived.C_MAJOR) else 0


def tql_key(
    literal: str | None, step: int | None, accidental: int | None, mode: str | None
) -> int:
    """1 when the key of these ``keys`` columns matches ``literal``; a literal
    that is no key matches nothing."""
    if literal is None:
        return 0
    spec = key_spec(literal)
    if isinstance(spec, str):
        return 0
    return 1 if harmony.key_matches(spec, _mode((step, accidental, mode))) else 0


_CHORD_COLUMNS = ("step", "accidental", "quality", "inversion", "applied_to")


def _mode(row: Any) -> dict[str, Any]:
    """The mode dict ``harmony`` reads, from a ``(step, accidental, mode)`` row."""
    return {"step": row[0], "accidental": row[1], "type": row[2]}


def register(con: sqlite3.Connection) -> None:
    """Register the functions on ``con``. Calling it again does nothing. No
    function holds ``con``: SQLite's references to them are hidden from the
    garbage collector, so one that did would keep ``con`` open for good."""
    try:
        con.execute("SELECT tql_color(NULL)")
        return
    except sqlite3.OperationalError:
        pass
    con.create_function("regexp", 2, regexp, deterministic=True)
    con.create_function("tql_fold", 1, tql_fold, deterministic=True)
    con.create_function("tql_color", 1, tql_color, deterministic=True)
    con.create_function("tql_chord", 9, tql_chord, deterministic=True)
    con.create_function("tql_key", 4, tql_key, deterministic=True)
