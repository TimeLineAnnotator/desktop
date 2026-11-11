"""``Scope.inside_items``, which the order relations and ``STARTS``/``ENDS``
read a unit's inside with: the same items, in the same order, as a test of every
item of the lane, without testing every item (research R20)."""

import random

import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import relations, showsql, sqlfuncs


def brute_force(scope, items, outer, metric, own):
    """The relation as a loop over every item of the lane."""
    out = []
    for it in items:
        u = it[0]
        if u.id == outer.id:
            continue
        if own and u.timeline_id == outer.timeline_id and u.kind == "hierarchy":
            if scope.is_descendant(u, outer):
                out.append(it)
        elif metric.inside(u, outer):
            out.append(it)
    return out


def _tree(rng, start, end, level, units):
    """A unit at ``level`` over about ``[start, end]`` and, below it, units that
    tile it, some overhanging it or leaving holes by a tolerance or so."""
    units.append([rng.choice("abcdeST"), level, start, end])
    if level == 1 or end - start < 0.4:
        return
    cuts = sorted(
        round(rng.uniform(start, end) / 0.05) * 0.05 for _ in range(rng.randint(1, 4))
    )
    bounds = [start, *cuts, end]
    for a, b in zip(bounds, bounds[1:], strict=False):
        jitter = rng.choice([0, 0, 0.05, 0.1, -0.1, 0.1 + 1e-12, 0.3])
        a2, b2 = a + rng.choice([0, jitter]), b - rng.choice([0, jitter])
        if b2 - a2 > 0.05:
            _tree(rng, a2, b2, level - 1, units)


def generated(seed):
    """A file of hierarchies, markers, ranges, harmony and beats at times on a
    grid of 0.05 s, where tolerances meet the edges often."""
    rng = random.Random(seed)
    length = 40
    form = []
    t = 0.0
    while t < length - 2:
        end = min(length, t + rng.choice([4, 6, 8.05, 10]))
        _tree(rng, t, end, 4, form)
        t = end + rng.choice([0, 0, 0.05, 0.5])
    other = []
    _tree(rng, 0.0, 20.0, 3, other)
    _tree(rng, 20.1, 39.9, 2, other)
    marks = [
        [rng.choice("pqr"), round(rng.uniform(0, length) / 0.05) * 0.05]
        for _ in range(60)
    ]
    marks += [[m[0], m[1]] for m in marks[:5]]  # several at one time
    rows = ["one", "two"]
    spans = []
    for _ in range(25):
        a = round(rng.uniform(0, length - 1) / 0.05) * 0.05
        spans.append([rng.choice(rows), "s", a, a + rng.choice([0.5, 1, 3.05])])
    chords = sorted(
        [round(rng.uniform(0, length) / 0.05) * 0.05, rng.choice("CDEFGAB"), "major"]
        for _ in range(30)
    )
    return {
        "length": length,
        "timelines": [
            {"name": "Form (X)", "kind": "hierarchy", "units": form},
            {"name": "Layers", "kind": "hierarchy", "units": other},
            {"name": "Marks", "kind": "marker", "units": marks},
            {"name": "Spans", "kind": "range", "rows": rows, "units": spans},
            {
                "name": "Harmony",
                "kind": "harmony",
                "keys": [[0, "C", "major"], [17.5, "G", "major"]],
                "chords": chords,
            },
            {
                "name": "Beats",
                "kind": "beats",
                "start": 0.5,
                "every": 0.5,
                "beats_per_bar": 4,
                "bars": 19,
            },
        ],
    }


def scope_of(index):
    con = index.connection()
    sqlfuncs.register(con, index)
    (file_id,) = con.execute("SELECT id FROM files").fetchone()
    return relations.Scope(showsql.Recorder(con), file_id, index.time_map(file_id))


METRICS = [
    relations.Metric(),
    relations.Metric(0.0),
    relations.Metric(0.5),
    relations.Metric(void=True),
]


@pytest.mark.parametrize("seed", range(4))
def test_the_items_inside_a_unit_are_those_a_test_of_every_item_finds(seed):
    index = fixture_index.build_index(generated(seed))
    scope = scope_of(index)
    con = index.connection()
    timelines = [r[0] for r in con.execute("SELECT id FROM timelines ORDER BY id")]
    lanes = [spec for tid in timelines for spec in scope.own_lanes(tid)]
    outers = []
    for tid in timelines:
        outers.extend(scope.timeline(tid))
    checked = found = 0
    for spec in lanes:
        items = scope.lane_items(spec)
        assert items
        for outer in outers:
            for metric in METRICS:
                for own in (True, False):
                    want = brute_force(scope, items, outer, metric, own)
                    got = scope.inside_items(items, outer, metric, own)
                    assert got == want, (spec, outer, metric, own)
                    checked += 1
                    found += bool(want)
    assert checked > 5000 and found > 1000


def test_a_lane_out_of_time_order_is_read_whole():
    index = fixture_index.build_index(generated(7))
    scope = scope_of(index)
    con = index.connection()
    (tid,) = con.execute("SELECT id FROM timelines WHERE name = 'Marks'").fetchone()
    (spec,) = scope.own_lanes(tid)
    items = list(reversed(scope.lane_items(spec)))
    for outer in scope.timeline(tid)[:20]:
        for metric in METRICS:
            want = brute_force(scope, items, outer, metric, False)
            assert scope.inside_items(items, outer, metric, False) == want


def test_a_unit_reads_the_items_near_it_not_the_whole_lane(monkeypatch):
    """A complexity guard: on a lane of 2,000 markers, the inside of a unit two
    seconds long tests a handful of them."""
    marks = [["m", i * 0.5] for i in range(2000)]
    fix = {
        "length": 1001,
        "timelines": [
            {"name": "Form (X)", "kind": "hierarchy", "units": [["a", 1, 100, 102]]},
            {"name": "Marks", "kind": "marker", "units": marks},
        ],
    }
    index = fixture_index.build_index(fix)
    scope = scope_of(index)
    con = index.connection()
    form, marks_tl = (
        r[0]
        for r in con.execute(
            "SELECT id FROM timelines ORDER BY name"
        )  # "Form (X)", "Marks"
    )
    (outer,) = scope.timeline(form)
    (spec,) = scope.own_lanes(marks_tl)
    items = scope.lane_items(spec)
    calls = []
    inside = relations.Metric.inside
    monkeypatch.setattr(
        relations.Metric,
        "inside",
        lambda self, a, b: calls.append(1) or inside(self, a, b),
    )
    got = scope.inside_items(items, outer, relations.Metric(), False)
    assert [it[1] for it in got] == [100, 100.5, 101, 101.5, 102]
    assert len(calls) < 20


def test_contains_a_child_with_an_order_relation_on_every_unit_of_a_long_lane():
    """``*[CONTAINS x[ENDS WITH y]]`` asks every unit of the file, the beats
    included, what lies inside it: the answer is the same as before, the
    descendants of the hierarchy's units."""
    fix = {
        "length": 60,
        "timelines": [
            {
                "name": "Form (X)",
                "kind": "hierarchy",
                "units": [
                    ["S", 3, 0, 16],
                    ["cont", 2, 0, 8],
                    ["x", 1, 0, 4],
                    ["cad", 1, 4, 8],
                    ["cont", 2, 8, 16],
                    ["cad", 1, 8, 12],
                    ["x", 1, 12, 16],
                ],
            },
            {
                "name": "Beats",
                "kind": "beats",
                "start": 0,
                "every": 0.25,
                "beats_per_bar": 4,
                "bars": 60,
            },
        ],
    }
    got = tql.run(
        fixture_index.build_index(fix), "*[CONTAINS cont[ENDS WITH cad]] IN form"
    )
    assert [(c.label, c.start) for m in got.matches for s in m.slots for c in s] == [
        ("S", 0)
    ]
