"""``derived.hierarchy_structure`` in O(n log n) gives what the O(n²) one gave
(TimeLineAnnotator/project-management#156).

The old function is kept here, word for word, as the reference: the new one
must give the same parents and depths, in the same order, on every hierarchy
timeline of TQL's examples and on made-up timelines with what real files
can hold: ties, spans within a microsecond, overlaps on one level, units of
no length, NaN and infinities, and ids given twice."""

import math
import random

import examples
import pytest

from tilia_core import derived

EPS = 1e-6


def old_hierarchy_structure(units):
    parents = {}
    for uid, level, start, end in units:
        best = None
        for pid, p_level, p_start, p_end in units:
            if pid == uid or p_level <= level:
                continue
            if p_start <= start + EPS and p_end >= end - EPS:
                key = (p_level, p_end - p_start)
                if best is None or key < best[0]:
                    best = (key, pid)
        parents[uid] = best[1] if best else None

    depths = {}

    def depth(uid):
        if uid not in depths:
            parent = parents[uid]
            depths[uid] = 1 if parent is None else depth(parent) + 1
        return depths[uid]

    return {uid: (parents[uid], depth(uid)) for uid in parents}


def same(units):
    try:
        want = old_hierarchy_structure(units)
    except RecursionError:  # ids shared so that parents go round
        with pytest.raises(RecursionError):
            derived.hierarchy_structure(units)
        return
    got = derived.hierarchy_structure(units)
    assert list(got.items()) == list(want.items())


FIXTURES = examples.load()["fixtures"]
TIMELINES = {
    f"{name}/{tl['name']}": tl
    for name, fixture in FIXTURES.items()
    for tl in fixture["timelines"]
    if tl["kind"] == "hierarchy"
}


def test_there_are_hierarchy_timelines_in_the_examples():
    assert len(TIMELINES) >= 10


@pytest.mark.parametrize("name", TIMELINES)
def test_the_examples_hierarchies(name):
    units = [
        (f"u{n}", level, start, end)
        for n, (_, level, start, end, *_) in enumerate(TIMELINES[name]["units"])
    ]
    same(units)
    same(list(reversed(units)))


def made_up(rng: random.Random, n: int) -> list[tuple[str, int, float, float]]:
    """``n`` units on a few levels, on a coarse grid, so that spans tie and
    hold each other, with some moved by about a microsecond."""
    levels = rng.choice([[1, 2, 3], [1, 2, 3, 4, 5], [0, 7], list(range(1, n + 2))])
    nudges = [0, 0, 0, 0.5e-6, -0.5e-6, 1e-6, -1e-6, 1.5e-6, -1.5e-6]
    units = []
    for i in range(n):
        start = rng.randrange(0, 12) / 2
        end = start + rng.randrange(0, 8) / 2
        start += rng.choice(nudges)
        end += rng.choice(nudges)
        units.append((f"u{i}", rng.choice(levels), start, end))
    if rng.random() < 0.2:
        i = rng.randrange(n)
        uid, level, start, end = units[i]
        odd = rng.choice([math.nan, math.inf, -math.inf])
        units[i] = (uid, level, *rng.choice([(odd, end), (start, odd), (odd, odd)]))
    if n > 1 and rng.random() < 0.2:  # a file may give two units one id
        i, j = rng.sample(range(n), 2)
        units[j] = (units[i][0], *units[j][1:])
    return units


@pytest.mark.parametrize("seed", range(300))
def test_made_up_hierarchies(seed):
    rng = random.Random(seed)
    same(made_up(rng, rng.randrange(1, 40)))


def test_a_nested_hierarchy_of_many_units():
    # Six levels, each unit split in two on the level below: 63 units.
    units = []
    spans = [(0.0, 64.0)]
    for level in range(6, 0, -1):
        units += [(f"{level}:{s}", level, s, e) for s, e in spans]
        spans = [
            half for s, e in spans for half in ((s, (s + e) / 2), ((s + e) / 2, e))
        ]
    same(units)
    assert derived.hierarchy_structure(units)["1:0.0"] == ("2:0.0", 6)


def test_a_unit_is_not_held_by_one_with_its_own_id():
    units = [("a", 2, 0, 10), ("b", 3, 0, 20), ("a", 1, 0, 5)]
    same(units)
    assert derived.hierarchy_structure(units)["a"] == ("b", 2)


def test_without_units():
    assert derived.hierarchy_structure([]) == {}
