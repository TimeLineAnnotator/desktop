"""What the index stores beside a file's own values.

Pure functions over plain data: the parent of a hierarchy unit, the end of a
chord or key, the key in force at a chord, the labels and properties of
harmony components, categories, colours and field names.
"""

import math
import re
from bisect import bisect_right
from collections.abc import Sequence
from typing import Any

from tilia_core import harmony
from tilia_core.colors import CSS_COLORS
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
    1e-6 s of slack), the smallest by (level, length), and the first of those
    in ``units``; the file stores no links. Depth is 1 for a unit without
    parent.

    Each level's units are sorted by start, with a tree of the largest end
    under each range of them, so that the units of a level that hold a span
    are found in O(log n) each: O(n log n) in all for units that nest, as a
    hierarchy's do (TimeLineAnnotator/project-management#156). Units that
    overlap on one level cost more, at worst O(n²) as before.
    """
    # Per level: the units that can hold another (no NaN), sorted by start,
    # and a segment tree of their ends' maximum.
    held: dict[int, tuple[list[float], list[float], list[int]]] = {}
    for n, (_, level, start, end) in enumerate(units):
        if not (math.isnan(start) or math.isnan(end)):  # NaN holds nothing
            held.setdefault(level, ([], [], []))[2].append(n)
    trees: dict[int, tuple[int, list[float]]] = {}
    for level, (starts, ends, order) in held.items():
        order.sort(key=lambda n: units[n][2])
        starts += [units[n][2] for n in order]
        ends += [units[n][3] for n in order]
        size = 1
        while size < len(order):
            size *= 2
        tree = [-math.inf] * (2 * size)
        tree[size : size + len(ends)] = ends
        for i in range(size - 1, 0, -1):
            tree[i] = max(tree[2 * i], tree[2 * i + 1])
        trees[level] = (size, tree)
    levels = sorted(held)
    place = {level: n for n, level in enumerate(levels)}

    def holder(uid: str, level: int, start: float, end: float) -> int | None:
        """The index in ``units`` of the smallest unit of ``level`` that holds
        ``start``-``end``, the first of equals; None without one."""
        starts, ends, order = held[level]
        size, tree = trees[level]
        until = bisect_right(starts, start + EPS)  # these start early enough
        reach = end - EPS
        best: tuple[float, int] | None = None
        nodes = [(1, 0, size)]
        while nodes:
            node, lo, hi = nodes.pop()
            if lo >= until or tree[node] < reach:
                continue
            if hi - lo > 1:
                mid = (lo + hi) // 2
                nodes += [(2 * node, lo, mid), (2 * node + 1, mid, hi)]
                continue
            n = order[lo]
            if units[n][0] == uid:
                continue
            key = (ends[lo] - starts[lo], n)
            if best is None or key < best:
                best = key
        return None if best is None else best[1]

    parents: dict[str, str | None] = {}
    for uid, level, start, end in units:
        found = None
        if not (math.isnan(start) or math.isnan(end)):  # nor is it held
            for p_level in levels[place[level] + 1 :]:  # its level is in held
                found = holder(uid, p_level, start, end)
                if found is not None:
                    break
        parents[uid] = None if found is None else units[found][0]

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
    plus ``label``, its symbol, as TiLiA's default display ("letter") shows
    it. The label never follows the chord's ``display_mode``: which of symbol
    and Roman numeral to show is a setting of the interface, not of each chord
    (Felipe, 2026-10-27), and its custom text stays a field of its own.
    ``key`` of the result is the key in force's label, None without one."""
    props = harmony.chord_props(chord, key or C_MAJOR)
    if key is None:
        props["key"] = None
    props["label"] = props["symbol"] or ""
    return props


def key_fields(mode: dict) -> dict:
    """The properties of a key, plus ``label``, its ``key``."""
    props = harmony.key_props(mode)
    props["label"] = props["key"]
    return props


def categories(label: str, grammar: LabelGrammar) -> tuple[str, ...]:
    """The categories of ``label`` under ``grammar``."""
    return grammar.categories(label)


def color(value: str | None) -> str | None:
    """A colour as lower-case ``#rrggbb``, from an SVG colour name or a hex
    code (``#rgb``, ``#rrggbb`` or Qt's ``#aarrggbb``, whose alpha is dropped;
    ``#`` optional). None and ``""``, TiLiA's "no colour", give None; anything
    else comes back stripped and in lower case."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s in CSS_COLORS:
        return "#" + CSS_COLORS[s]
    m = re.fullmatch(r"#?(?:[0-9a-f]{2})?([0-9a-f]{6})", s)
    if m:
        return "#" + m.group(1)
    m = re.fullmatch(r"#?([0-9a-f])([0-9a-f])([0-9a-f])", s)
    if m:
        return "#" + "".join(c * 2 for c in m.groups())
    return s


def field_name(name: str) -> str:
    """``name`` in lower case, with runs of whitespace as ``_``."""
    return re.sub(r"\s+", "_", name.strip().lower())
