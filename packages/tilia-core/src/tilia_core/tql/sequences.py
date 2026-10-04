"""Sequence matching: find the matches of a TQL ``THEN`` sequence in a lane.

A lane is a time-ordered list of ``(unit, start, end)`` items. Units are opaque
here: a ``fits`` callable says whether a unit fits a step's ``Unit`` node. The
matcher is memoised and polynomial, so nested quantifiers never blow up.
"""

from __future__ import annotations

from typing import Any, Callable

from .lanes import GAP_EPS
from .syntax import Group, Seq, Step, Unit, _marked

Fits = Callable[[Unit, Any], bool]
Item = tuple[Any, float, float]
Run = tuple[int, int, list[int], "list[bool] | None"]


class Runs:
    """Matches a :class:`~tilia_core.tql.syntax.Seq` inside one contiguous block
    of items.

    ``ends_steps(steps, si, pos)`` is the set of positions where ``steps[si:]``
    can finish when started at ``pos`` — memoised, so nested quantifiers cost
    polynomial time. Every repetition consumes at least one item, which is what
    keeps ``(verse?)*`` from looping on nothing."""

    def __init__(
        self,
        fits: Fits,
        items: list[Item],
        check: Callable[[], None] | None = None,
    ) -> None:
        self.fits = fits
        self.check = check
        self.items = items
        self.n = len(items)
        self.m_steps: dict[tuple[int, int, int], frozenset[int]] = {}
        self.m_step: dict[tuple[int, int], frozenset[int]] = {}

    def ends_steps(self, steps: list[Step], si: int, pos: int) -> frozenset[int]:
        key = (id(steps), si, pos)
        hit = self.m_steps.get(key)
        if hit is not None:
            return hit
        if si == len(steps):
            out = frozenset((pos,))
        elif si == len(steps) - 1:  # the last step's ends are the pattern's
            out = self.ends_step(steps[si], pos)
        else:
            acc: set[int] = set()
            for p in self.ends_step(steps[si], pos):
                acc |= self.ends_steps(steps, si + 1, p)
            out = frozenset(acc)
        self.m_steps[key] = out
        return out

    def ends_step(self, step: Step, pos: int) -> frozenset[int]:
        key = (id(step), pos)
        hit = self.m_step.get(key)
        if hit is not None:
            return hit
        lo, hi = step.lo, step.hi
        result: set[int] = {pos} if lo == 0 else set()
        frontier, count = {pos}, 0
        reuse = hi is None and lo <= 1  # an unbounded step restarts from any end
        while frontier and (hi is None or count < hi):
            count += 1
            nxt: set[int] = set()
            for p in frontier:
                if reuse and p != pos and (id(step), p) in self.m_step:
                    nxt |= self.m_step[id(step), p]  # later starts come first
                    continue
                nxt |= {e for e in self.ends_item(step.item, p) if e > p}
            if count >= lo:
                fresh = nxt - result
                result |= nxt
                if hi is None:
                    nxt = fresh  # already expanded with an unbounded count
            frontier = nxt
        out = frozenset(result)
        self.m_step[key] = out
        return out

    def ends_item(self, item: Unit | Group, pos: int) -> frozenset[int]:
        if isinstance(item, Group):
            acc: set[int] = set()
            for opt in item.options:
                acc |= self.ends_steps(opt.steps, 0, pos)
            return frozenset(acc)
        if pos < self.n and self.fits(item, self.items[pos][0]):
            return frozenset((pos + 1,))
        return frozenset()

    def assign(
        self, steps: list[Step], si: int, pos: int, end: int
    ) -> list[int] | None:
        """Which top-level step consumed each item of ``[pos, end)`` — greedy:
        earlier steps take as much as the rest of the pattern allows."""
        if si == len(steps):
            return [] if pos == end else None
        for p in sorted(self.ends_step(steps[si], pos), reverse=True):
            if p <= end and end in self.ends_steps(steps, si + 1, p):
                rest = self.assign(steps, si + 1, p, end)
                if rest is not None:
                    return [si] * (p - pos) + rest
        return None

    def marks(
        self, steps: list[Step], si: int, pos: int, end: int
    ) -> list[bool] | None:
        """Per item of ``[pos, end)``, which ``steps[si:]`` take: whether a step
        marked ``@`` took it, the steps inside groups included. The split is
        :meth:`assign`'s, so the flags line up with the slots."""
        if si == len(steps):
            return [] if pos == end else None
        st = steps[si]
        for p in sorted(self.ends_step(st, pos), reverse=True):
            if p <= end and end in self.ends_steps(steps, si + 1, p):
                here = self.step_marks(st, pos, p)
                after = self.marks(steps, si + 1, p, end) if here is not None else None
                if after is not None:
                    return here + after
        return None

    def step_marks(self, st: Step, pos: int, end: int) -> list[bool] | None:
        """:meth:`marks` for the repetitions of one step, which take exactly
        ``[pos, end)``. A group with marks inside is split into repetitions
        (each as long as the rest allows), and each into its option's steps."""
        item = st.item
        if (
            st.target
            or not isinstance(item, Group)
            or not any(True for o in item.options for _ in _marked(o))
        ):
            return [st.target] * (end - pos)
        memo: dict[tuple[int, int], list[int] | None] = {}

        def reps(p: int, k: int) -> list[int] | None:  # repetition ends from p on
            if (p, k) in memo:
                return memo[p, k]
            out: list[int] | None = None
            if p == end:
                out = [] if k >= st.lo else None
            elif st.hi is None or k < st.hi:
                for q in sorted(
                    (e for e in self.ends_item(item, p) if p < e <= end),
                    reverse=True,
                ):
                    more = reps(q, k + 1)
                    if more is not None:
                        out = [q] + more
                        break
            memo[p, k] = out
            return out

        bounds = reps(pos, 0)
        if bounds is None:
            return None
        flags: list[bool] = []
        p = pos
        for q in bounds:
            for o in item.options:
                got = (
                    self.marks(o.steps, 0, p, q)
                    if q in self.ends_steps(o.steps, 0, p)
                    else None
                )
                if got is not None:
                    flags += got
                    break
            else:
                return None
            p = q
        return flags


def drop_contained(runs: list[Run]) -> list[Run]:
    """Drop every run that lies inside another one — "the same musical fact read
    short". One sweep in start order: a run is inside an earlier-starting (or
    same-start, longer) one iff some such run reaches at least as far."""
    order = sorted(range(len(runs)), key=lambda k: (runs[k][0], -runs[k][1]))
    keep: set[int] = set()
    reach = -1
    for k in order:
        b = runs[k][1]
        if reach >= b:
            continue
        keep.add(k)
        reach = b
    return [r for k, r in enumerate(runs) if k in keep]


def blocks(
    items: list[Item],
    point: bool,
    joins: Callable[[float, float], bool] | None = None,
) -> list[tuple[int, int]]:
    """Split a lane into runs of time-contiguous items: ``THEN`` means
    "immediately follows", so a hole breaks it. Point lanes never break.
    ``joins(end, start)``, from ``THEN … WITHIN``, replaces that rule: two
    neighbours stay in one run when it says the gap between them is crossed."""
    if not items:
        return []
    out: list[tuple[int, int]] = []
    b0 = 0
    for k in range(1, len(items)):
        if joins is not None:
            brk = not joins(items[k - 1][2], items[k][1])
        else:
            brk = not point and items[k][1] - items[k - 1][2] > GAP_EPS
        if brk:
            out.append((b0, k))
            b0 = k
    out.append((b0, len(items)))
    return out


def find_runs(
    seq: Seq,
    items: list[Item],
    mode: str,
    point: bool,
    fits: Fits,
    joins: Callable[[float, float], bool] | None = None,
    marks: bool = False,
    check: Callable[[], None] | None = None,
) -> list[Run]:
    """``[(i, j, assign, flags)]`` matches of ``seq`` in ``items``. ``mode``:
    any (unanchored), start, end, full. ``joins``: see :func:`blocks`.
    ``flags``, with ``marks`` (a query with ``@``): per item of the run,
    whether a marked step took it; None otherwise, when the whole run is the
    target. ``check``, if given, is called first and may raise to stop a query
    that runs too long."""
    if check is not None:
        check()
    bl = blocks(items, point, joins)
    st = seq.steps[0]
    if mode == "any" and len(seq.steps) == 1 and isinstance(st.item, Unit):
        return _unit_runs(st, items, bl, fits)
    out: list[Run] = []
    for b0, b1 in bl:
        if mode in ("start", "full") and b0 != 0:
            continue
        if mode in ("end", "full") and b1 != len(items):
            continue
        block = items[b0:b1]
        r = Runs(fits, block, check)
        # Last start first: each start then reuses the memo of the later ones.
        starts = [0] if mode in ("start", "full") else range(len(block) - 1, -1, -1)
        found: list[Run] = []
        for i in starts:
            ends = [e for e in r.ends_steps(seq.steps, 0, i) if e > i]
            if mode in ("end", "full"):
                ends = [e for e in ends if e == len(block)]
            if not ends:
                continue
            j = max(ends)
            assign = r.assign(seq.steps, 0, i, j)
            found.append(
                (
                    b0 + i,
                    b0 + j,
                    assign if assign is not None else [],
                    r.marks(seq.steps, 0, i, j) if marks else None,
                )
            )
        out += reversed(found)
    return drop_contained(out) if mode in ("any", "end") else out


def _unit_runs(
    step: Step, items: list[Item], bl: list[tuple[int, int]], fits: Fits
) -> list[Run]:
    """The same answer as the general matcher for a one-step pattern
    (``verse+``, ``*``, ``x{2}``), in linear time: on a lane of 400 beats the
    general one is quadratic."""
    lo, hi = max(step.lo, 1), step.hi
    unit = step.item
    assert isinstance(unit, Unit)
    out: list[Run] = []
    for b0, b1 in bl:
        k = b0
        while k < b1:
            if not fits(unit, items[k][0]):
                k += 1
                continue
            a = k
            while k < b1 and fits(unit, items[k][0]):
                k += 1
            if hi is None:  # one maximal run
                if k - a >= lo:
                    out.append((a, k, [0] * (k - a), None))
                continue
            for i in range(a, k):  # longest window per start
                j = min(i + hi, k)
                if j - i >= lo:
                    out.append((i, j, [0] * (j - i), None))
    return drop_contained(out)


def slots_of(
    items: list[Item], i: int, j: int, assign: list[int], n_steps: int
) -> list[list[Item]]:
    """The items of ``items[i:j]`` grouped by the top-level step that took them."""
    slots: list[list[Item]] = [[] for _ in range(n_steps)]
    for k, si in zip(range(i, j), assign, strict=True):
        slots[si].append(items[k])
    return slots
