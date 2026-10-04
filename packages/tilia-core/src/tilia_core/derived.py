"""What the index stores beside a file's own values.

Pure functions over plain data: the parent of a hierarchy unit, the end of a
chord or key, the key in force at a chord, the labels and properties of
harmony components, categories, colours and field names.
"""

import re
from collections.abc import Sequence
from typing import Any

from tilia_core import harmony
from tilia_core.labels import LabelGrammar

EPS = 1e-6

C_MAJOR: dict[str, Any] = {"step": 0, "accidental": 0, "type": "major"}
"""The mode TiLiA reads a chord with no key before it in."""


def hierarchy_structure(
    units: Sequence[tuple[str, int, float, float]],
) -> dict[str, tuple[str | None, int]]:
    """For each unit ``(id, level, start, end)`` of one hierarchy timeline,
    ``id -> (parent id, depth)``.

    The parent is the unit on a higher level whose span holds this one (with
    1e-6 s of slack), the smallest by (level, length); the file stores no
    links. Depth is 1 for a unit without parent.
    """
    parents: dict[str, str | None] = {}
    for uid, level, start, end in units:
        best: tuple[tuple[int, float], str] | None = None
        for pid, p_level, p_start, p_end in units:
            if pid == uid or p_level <= level:
                continue
            if p_start <= start + EPS and p_end >= end - EPS:
                key = (p_level, p_end - p_start)
                if best is None or key < best[0]:
                    best = (key, pid)
        parents[uid] = best[1] if best else None

    depths: dict[str, int] = {}

    def depth(uid: str) -> int:
        if uid not in depths:
            parent = parents[uid]
            depths[uid] = 1 if parent is None else depth(parent) + 1
        return depths[uid]

    return {uid: (parents[uid], depth(uid)) for uid in parents}


def implied_spans(starts: Sequence[float], file_end: float) -> list[float]:
    """The end of each point in ``starts`` (sorted): the next start, and for
    the last one ``max(file_end, its start)``."""
    ends = list(starts[1:])
    if starts:
        ends.append(max(file_end, starts[-1]))
    return ends


def key_in_force(
    chord_starts: Sequence[float], key_starts: Sequence[float]
) -> list[int | None]:
    """Per chord, the index of the last key starting at or before it (with
    1e-6 s of slack), or None before the first key. Both sequences are sorted."""
    result: list[int | None] = []
    k = -1
    for start in chord_starts:
        while k + 1 < len(key_starts) and key_starts[k + 1] <= start + EPS:
            k += 1
        result.append(k if k >= 0 else None)
    return result


def chord_fields(chord: dict, key: dict | None) -> dict:
    """The properties of a chord read in ``key`` (C major when it has none),
    plus ``label``: its custom text, else its Roman numeral, else its symbol.
    ``key`` of the result is the key in force's label, None without one."""
    props = harmony.chord_props(chord, key or C_MAJOR)
    if key is None:
        props["key"] = None
    props["label"] = chord.get("custom_text") or props["roman"] or props["symbol"] or ""
    return props


def key_fields(mode: dict) -> dict:
    """The properties of a key, plus ``label``, its ``key``."""
    props = harmony.key_props(mode)
    props["label"] = props["key"]
    return props


def categories(label: str, grammar: LabelGrammar) -> tuple[str, ...]:
    """The categories of ``label`` under ``grammar``."""
    return grammar.categories(label)


_CSS = dict(
    pair.split(":")
    for pair in (
        "black:000000 silver:c0c0c0 gray:808080 grey:808080 white:ffffff "
        "maroon:800000 red:ff0000 purple:800080 fuchsia:ff00ff magenta:ff00ff "
        "green:008000 lime:00ff00 olive:808000 yellow:ffff00 navy:000080 "
        "blue:0000ff teal:008080 aqua:00ffff cyan:00ffff orange:ffa500 "
        "pink:ffc0cb hotpink:ff69b4 deeppink:ff1493 lightpink:ffb6c1 "
        "brown:a52a2a gold:ffd700 khaki:f0e68c beige:f5f5dc violet:ee82ee "
        "indigo:4b0082 orchid:da70d6 plum:dda0dd lavender:e6e6fa "
        "salmon:fa8072 coral:ff7f50 tomato:ff6347 crimson:dc143c tan:d2b48c "
        "chocolate:d2691e sienna:a0522d turquoise:40e0d0 skyblue:87ceeb "
        "lightblue:add8e6 steelblue:4682b4 royalblue:4169e1 darkblue:00008b "
        "darkgreen:006400 lightgreen:90ee90 seagreen:2e8b57 "
        "forestgreen:228b22 darkred:8b0000 darkorange:ff8c00 "
        "lightgray:d3d3d3 lightgrey:d3d3d3 darkgray:a9a9a9 darkgrey:a9a9a9 "
        "ivory:fffff0 mintcream:f5fffa"
    ).split()
)


def color(value: str | None) -> str | None:
    """A colour as lower-case ``#rrggbb``, from a CSS name or a hex code
    (three or six digits, ``#`` optional). None stays None; anything else
    comes back stripped and in lower case."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in _CSS:
        return "#" + _CSS[s]
    m = re.fullmatch(r"#?([0-9a-f]{6})", s)
    if m:
        return "#" + m.group(1)
    m = re.fullmatch(r"#?([0-9a-f])([0-9a-f])([0-9a-f])", s)
    if m:
        return "#" + "".join(c * 2 for c in m.groups())
    return s


def field_name(name: str) -> str:
    """``name`` in lower case, with runs of whitespace as ``_``."""
    return re.sub(r"\s+", "_", name.strip().lower())
