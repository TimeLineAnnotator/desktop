"""The SQL functions TQL's statements call, registered on a connection.

``text REGEXP pattern`` is ``regexp(pattern, text)``; ``tql_fold`` and
``tql_color`` compare labels and colours the way the language does.
``tql_chord`` and ``tql_key`` read a literal as a chord or a key and ask whether
a chord or a key component matches it (a literal that is none matches nothing).
``tql_position``, ``tql_length`` and ``tql_unit_seconds`` ask the time map of a
file (``index.time_map(file_id)``) where a time lies, how long a span lasts and
how long a beat or a bar lasts; they are null for a file without a time map and
for a time off it.
"""

from __future__ import annotations

import re
import sqlite3
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


def _chord_function(
    con: sqlite3.Connection,
) -> Callable[[str | None, str | None], int]:
    def tql_chord(literal: str | None, component_id: str | None) -> int:
        """1 when the chord ``component_id`` matches ``literal``, read in the
        key in force (C major before the first key); a literal that is no chord
        matches nothing."""
        if literal is None:
            return 0
        row = con.cursor().execute(_CHORD_ROW, (component_id,)).fetchone()
        if row is None:
            return 0
        spec = chord_spec(literal)
        if isinstance(spec, str):
            return 0
        chord = dict(zip(_CHORD_COLUMNS, row[:5], strict=True))
        key = None if row[5] is None else _mode(row[5:8])
        return 1 if harmony.chord_matches(spec, chord, key or derived.C_MAJOR) else 0

    return tql_chord


def _key_function(
    con: sqlite3.Connection,
) -> Callable[[str | None, str | None], int]:
    def tql_key(literal: str | None, component_id: str | None) -> int:
        """1 when the key ``component_id`` matches ``literal``; a literal that
        is no key matches nothing."""
        if literal is None:
            return 0
        row = (
            con.cursor()
            .execute(
                "SELECT step, accidental, mode FROM keys WHERE component_id = ?",
                (component_id,),
            )
            .fetchone()
        )
        if row is None:
            return 0
        spec = key_spec(literal)
        if isinstance(spec, str):
            return 0
        return 1 if harmony.key_matches(spec, _mode(row)) else 0

    return tql_key


_CHORD_COLUMNS = ("step", "accidental", "quality", "inversion", "applied_to")
_CHORD_ROW = (
    "SELECT ch.step, ch.accidental, ch.quality, ch.inversion, ch.applied_to, "
    "k.step, k.accidental, k.mode FROM chords ch "
    "LEFT JOIN keys k ON k.component_id = ch.key_id WHERE ch.component_id = ?"
)


def _mode(row: Any) -> dict[str, Any]:
    """The mode dict ``harmony`` reads, from a ``(step, accidental, mode)`` row."""
    return {"step": row[0], "accidental": row[1], "type": row[2]}


class _TimeMaps:
    """The time maps of one index, asked for once per file."""

    def __init__(self, index: Any) -> None:
        self.index = index
        self._maps: dict[Any, Any] = {}

    def get(self, file_id: Any) -> Any:
        if self.index is None:
            return None
        if file_id not in self._maps:
            self._maps[file_id] = self.index.time_map(file_id)
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
    the others once."""
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
    con.create_function("tql_chord", 2, _chord_function(con))
    con.create_function("tql_key", 2, _key_function(con))
