"""Lanes: the time-ordered ``(unit, start, end)`` items a TQL query runs over.

A lane comes from one timeline (one level of a hierarchy, one row of a range
timeline, a marker timeline, chords, keys, beats), or, for bars, from the
measures of a file's time map. This module holds the constants that decide when
two items touch, the names of the bars lane's units, and builds a hierarchy
level's lane.
"""

from __future__ import annotations

from typing import Any, Sequence, TypeVar

BAR_KIND = "bar"  # the kind of the units of the bars lane

GAP_EPS: float = 0.1  # s: a gap above this breaks a THEN run between spans
LEAF_EPS: float = 1e-6  # s: containment inside one hierarchy (float noise only)

U = TypeVar("U")


def bar_id(file_id: str, count: int) -> str:
    """The id of the unit of the bars lane that is bar ``count`` (from 1, in
    playing order) of a file. No file stores it: it names a row of ``measures``."""
    return f"{file_id}:bar:{count}"


def pass_numbers(numbers: Sequence[Any]) -> list[int]:
    """For each bar in playing order, which time through its printed number it
    is: 1 for the first, 2 for the second (a repeat), and so on."""
    seen: dict[Any, int] = {}
    out: list[int] = []
    for n in numbers:
        seen[n] = seen.get(n, 0) + 1
        out.append(seen[n])
    return out


def project(units: Sequence[U], level: int) -> list[tuple[U, float, float]]:
    """Project a hierarchy onto one level: tile the covered time with
    ``(unit, start, end)`` segments, each the deepest unit whose level is at
    least ``level`` (ties: the shorter one). Neighbouring segments of the same
    unit are merged.

    A unit is any object with the attributes ``level`` (an int or None),
    ``start`` and ``end``; units without a level are ignored."""
    us: list[Any] = [u for u in units if u.level is not None and u.level >= level]
    pts = sorted({u.start for u in us} | {u.end for u in us})
    segs: list[list[Any]] = []
    for a, b in zip(pts, pts[1:], strict=False):
        if b - a <= LEAF_EPS:
            continue
        mid = (a + b) / 2
        rep = None
        for u in us:
            if u.start <= mid <= u.end and (
                rep is None
                or u.level < rep.level
                or (u.level == rep.level and u.end - u.start < rep.end - rep.start)
            ):
                rep = u
        if rep is None:
            continue
        if segs and segs[-1][0] is rep and abs(segs[-1][2] - a) <= LEAF_EPS:
            segs[-1][2] = b
        else:
            segs.append([rep, a, b])
    return [(s[0], s[1], s[2]) for s in segs]
