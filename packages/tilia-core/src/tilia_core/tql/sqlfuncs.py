"""The SQL functions TQL's statements call, registered on a connection.

Their names are public, like the index's tables: ``Result.sql`` shows them and
``tql.sql`` lets users call them, so renaming one changes what users have
written (``test_tql_show_sql.py`` pins them). They are:

- ``regexp(pattern, text)``, which SQLite calls for ``text REGEXP pattern``:
  1 when the regular expression is found in the text read in NFC.
- ``tql_fold(text)``: the text folded the way TQL compares words and labels.
- ``tql_color(text)``: a colour, from a CSS name or a hex code, as ``#rrggbb``.
- ``tql_chord(literal, step, accidental, quality, inversion, applied_to,
  key_step, key_accidental, key_mode)``: 1 when the chord of those ``chords``
  and ``keys`` columns matches the literal read as a chord.
- ``tql_key(literal, step, accidental, mode)``: 1 when the key of those
  ``keys`` columns matches the literal read as a key.
- ``tql_position(file_id, time, unit)``: where a time lies in the file's score,
  in bars or beats.
- ``tql_length(file_id, start, end, unit)``: how many bars or beats a span lasts.
- ``tql_unit_seconds(file_id, time, unit)``: how many seconds the bar or beat
  holding a time lasts.

A literal that is no chord or no key matches nothing. The last three ask the
time map of the file (``index.time_map(file_id)``) and are null for a file
without one and for a time off it.
"""

from __future__ import annotations

import re
import sqlite3
import weakref
from functools import lru_cache
from typing import Any, Callable

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


class _TimeMaps:
    """The time maps of one index, asked for once per file. The index is held
    weakly, since it may hold the connection the functions are registered on;
    one that takes no weak reference is held, and keeps that connection."""

    def __init__(self, index: Any) -> None:
        self._index: Callable[[], Any]
        try:
            self._index = weakref.ref(index)
        except TypeError:
            self._index = lambda: index
        self._maps: dict[Any, Any] = {}

    def get(self, file_id: Any) -> Any:
        index = self._index()
        if index is None:
            return None
        if file_id not in self._maps:
            self._maps[file_id] = index.time_map(file_id)
        return self._maps[file_id]


def _is_time(t: Any) -> bool:
    return isinstance(t, (int, float)) and not isinstance(t, bool)


def _time_map_functions(maps: _TimeMaps) -> dict[str, tuple[int, Callable[..., Any]]]:
    def tql_position(file_id: Any, time: Any, unit: Any) -> float | None:
        """Where ``time`` lies along the score, in bars or beats."""
        tmap = maps.get(file_id)
        if tmap is None or not _is_time(time):
            return None
        return tmap.position(time, unit)

    def tql_length(file_id: Any, start: Any, end: Any, unit: Any) -> float | None:
        """How long ``start`` to ``end`` lasts, in bars or beats."""
        tmap = maps.get(file_id)
        if tmap is None or not _is_time(start) or not _is_time(end):
            return None
        return tmap.length(start, end, unit)

    def tql_unit_seconds(file_id: Any, time: Any, unit: Any) -> float | None:
        """How long the beat or the bar holding ``time`` lasts, in seconds."""
        tmap = maps.get(file_id)
        if tmap is None or not _is_time(time):
            return None
        return tmap.unit_seconds(time, unit)

    return {
        "tql_position": (3, tql_position),
        "tql_length": (4, tql_length),
        "tql_unit_seconds": (3, tql_unit_seconds),
    }


def register(con: sqlite3.Connection, index: Any = None) -> None:
    """Register the functions on ``con``. ``index``, when given, is the index
    whose time maps ``tql_position``, ``tql_length`` and ``tql_unit_seconds``
    ask (without one they are null); they are registered anew on every call,
    the others once. No function holds ``con``: SQLite's references to them
    are hidden from the garbage collector, so one that did would keep ``con``
    open for good."""
    for name, (n_args, function) in _time_map_functions(_TimeMaps(index)).items():
        con.create_function(name, n_args, function)
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
