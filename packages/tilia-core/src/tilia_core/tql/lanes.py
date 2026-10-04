"""Lanes: the time-ordered ``(unit, start, end)`` items a TQL query runs over.

A lane comes from one timeline (one level of a hierarchy, one row of a range
timeline, a marker timeline, chords, keys, beats). This module holds the
constants that decide when two items touch and builds a hierarchy level's lane.
"""

from __future__ import annotations

from typing import Any, Sequence, TypeVar

GAP_EPS: float = 0.1  # s: a gap above this breaks a THEN run between spans
LEAF_EPS: float = 1e-6  # s: containment inside one hierarchy (float noise only)

U = TypeVar("U")


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
