import time
from dataclasses import dataclass

import pytest

from tilia_core import tql
from tilia_core.tql import lanes, sequences
from tilia_core.tql.sequences import Runs, find_runs, slots_of


@dataclass(eq=False)
class FakeUnit:
    label: str
    start: float
    end: float
    level: int | None = 1


def fits(unode, unit):
    term = unode.term
    if term is None:
        return True
    hit = any(
        all(
            lit.kind == "any" or lit.text.lower() == unit.label.lower()
            for lit in alt.lits
        )
        for alt in term.alts
    )
    return not hit if term.negate else hit


def seq_of(text):
    return tql.parse(text).pattern.seq


def spans(*labels, gap=0.0):
    items, t = [], 0.0
    for lab in labels:
        items.append((FakeUnit(lab, t, t + 1), t, t + 1))
        t += 1 + gap
    return items


def points(*pairs):
    return [(FakeUnit(lab, t, t), t, t) for lab, t in pairs]


def run(text, items, mode="any", point=False, **kw):
    return find_runs(seq_of(text), items, mode, point, fits, **kw)


def spans_of(text, items, **kw):
    return [(i, j) for i, j, _, _ in run(text, items, **kw)]


class TestQuantifiers:
    def test_exact_count(self):
        assert spans_of("verse{2}", spans("verse", "verse", "verse")) == [
            (0, 2),
            (1, 3),
        ]

    def test_plus(self):
        assert spans_of("verse+", spans("verse", "verse", "verse")) == [(0, 3)]

    def test_plus_splits_on_other_label(self):
        assert spans_of("verse+", spans("verse", "chorus", "verse", "verse")) == [
            (0, 1),
            (2, 4),
        ]

    def test_optional(self):
        assert spans_of("verse?", spans("verse", "chorus", "verse")) == [
            (0, 1),
            (2, 3),
        ]

    def test_star(self):
        assert spans_of("verse*", spans("verse", "verse", "chorus")) == [(0, 2)]

    def test_at_least(self):
        items = spans("verse", "verse", "verse", "chorus", "verse")
        assert spans_of("verse{2,}", items) == [(0, 3)]

    def test_between(self):
        items = spans("verse", "verse", "verse", "verse")
        assert spans_of("verse{1,2}", items) == [(0, 2), (1, 3), (2, 4)]

    def test_between_min_not_met(self):
        assert spans_of("verse{2,3}", spans("verse", "chorus", "verse")) == []

    def test_no_match(self):
        assert spans_of("bridge", spans("verse", "chorus")) == []

    def test_case_insensitive_and_not(self):
        items = spans("Verse", "chorus", "bridge")
        assert spans_of("verse", items) == [(0, 1)]
        assert spans_of("NOT verse+", items) == [(1, 3)]
        assert spans_of("*", items) == [(0, 1), (1, 2), (2, 3)]


class TestThen:
    def test_then_with_quantifier(self):
        got = run("verse+ THEN chorus", spans("verse", "verse", "chorus", "bridge"))
        assert [(i, j, a) for i, j, a, _ in got] == [(0, 3, [0, 0, 1])]

    def test_longest_run_at_each_start(self):
        items = spans("verse", "verse", "chorus")
        assert spans_of("verse* THEN chorus", items) == [(0, 3)]

    def test_run_inside_longer_one_dropped(self):
        # starting at 1 gives (1, 3), contained in (0, 3)
        items = spans("verse", "verse", "chorus")
        assert spans_of("verse+ THEN chorus", items) == [(0, 3)]

    def test_non_contained_runs_kept(self):
        items = spans("a", "b", "a", "b", "c")
        assert spans_of("a THEN b", items) == [(0, 2), (2, 4)]

    def test_slots_of(self):
        items = spans("verse", "verse", "chorus", "bridge")
        ((i, j, assign, _),) = run("verse+ THEN chorus", items)
        slots = slots_of(items, i, j, assign, 2)
        assert [[it[0].label for it in s] for s in slots] == [
            ["verse", "verse"],
            ["chorus"],
        ]


class TestGroups:
    def test_group_repeated_then_step(self):
        items = spans("verse", "chorus", "verse", "chorus", "bridge", "verse")
        got = run("(verse THEN chorus)+ THEN bridge", items)
        assert [(i, j, a) for i, j, a, _ in got] == [(0, 5, [0, 0, 0, 0, 1])]

    def test_or_between_groups(self):
        items = spans("verse", "chorus", "bridge")
        assert spans_of("(chorus THEN bridge) OR (verse THEN chorus)", items) == [
            (0, 2),
            (1, 3),
        ]

    def test_nested_groups(self):
        items = spans("a", "b", "a", "b", "c", "a", "b", "c")
        assert spans_of("((a THEN b)+ THEN c)+", items) == [(0, 8)]

    def test_empty_repetition_does_not_loop(self):
        assert spans_of("(verse?)*", spans("verse", "verse")) == [(0, 2)]

    def test_optional_group(self):
        items = spans("a", "b", "c")
        assert spans_of("(a THEN b)? THEN c", items) == [(0, 3)]


class TestMarks:
    def test_mark_in_sequence(self):
        got = run(
            "* THEN @bridge THEN *",
            spans("verse", "bridge", "chorus"),
            marks=True,
        )
        assert [(i, j, f) for i, j, _, f in got] == [(0, 3, [False, True, False])]

    def test_mark_inside_group(self):
        items = spans("verse", "chorus", "verse", "chorus")
        got = run("(verse THEN @chorus)+", items, marks=True)
        assert [(i, j, f) for i, j, _, f in got] == [(0, 4, [False, True, False, True])]

    def test_mark_on_group_marks_all(self):
        items = spans("verse", "chorus", "bridge")
        got = run("@(verse THEN chorus) THEN bridge", items, marks=True)
        assert [f for *_, f in got] == [[True, True, False]]

    def test_no_flags_without_marks(self):
        got = run("verse", spans("verse"))
        assert got[0][3] is None


class TestHoles:
    def test_gap_breaks_run_between_spans(self):
        items = spans("verse", "chorus", gap=0.5)
        assert spans_of("verse THEN chorus", items) == []

    def test_small_gap_does_not_break(self):
        items = spans("verse", "chorus", gap=0.05)
        assert spans_of("verse THEN chorus", items) == [(0, 2)]

    def test_gap_breaks_quantifier_run(self):
        items = spans("verse", "verse", gap=0.5)
        assert spans_of("verse+", items) == [(0, 1), (1, 2)]

    def test_gap_does_not_break_points(self):
        items = points(("a", 0), ("b", 50))
        assert spans_of("a THEN b", items, point=True) == [(0, 2)]

    def test_joins_crosses_gap(self):
        items = spans("verse", "chorus", gap=2.0)
        got = spans_of("verse THEN chorus", items, joins=lambda end, start: True)
        assert got == [(0, 2)]

    def test_joins_replaces_hole_rule(self):
        items = spans("verse", "chorus", gap=0.0)
        got = spans_of("verse THEN chorus", items, joins=lambda end, start: False)
        assert got == []

    def test_joins_sees_end_and_start(self):
        items = spans("verse", "chorus", "verse", "chorus", gap=2.0)
        items[2:] = [(u, s + 1, e + 1) for u, s, e in items[2:]]
        calls = []

        def joins(end, start):
            calls.append((end, start))
            return start - end <= 2.0

        find_runs(seq_of("verse THEN chorus"), items, "any", False, fits, joins)
        assert calls[0] == (1.0, 3.0)

    def test_blocks(self):
        assert sequences.blocks(spans("a", "b", "c", gap=1), False) == [
            (0, 1),
            (1, 2),
            (2, 3),
        ]
        assert sequences.blocks(spans("a", "b", gap=1), True) == [(0, 2)]
        assert sequences.blocks([], False) == []


class TestPoints:
    MARKERS = points(("HC", 7.5), ("HC", 9.5), ("EC", 17.5), ("PAC", 21.5))

    def test_no_match(self):
        assert spans_of("HC THEN PAC", self.MARKERS, point=True) == []

    def test_match_across_distance(self):
        assert spans_of("EC THEN PAC", self.MARKERS, point=True) == [(2, 4)]

    def test_repeat(self):
        assert spans_of("HC THEN HC", self.MARKERS, point=True) == [(0, 2)]


class TestModes:
    ITEMS = spans("verse", "chorus", "verse", "chorus")

    def test_start(self):
        assert spans_of("verse THEN chorus", self.ITEMS, mode="start") == [(0, 2)]
        assert spans_of("chorus", self.ITEMS, mode="start") == []

    def test_end(self):
        assert spans_of("verse THEN chorus", self.ITEMS, mode="end") == [(2, 4)]
        assert spans_of("verse", self.ITEMS, mode="end") == []

    def test_full(self):
        assert spans_of("(verse THEN chorus)+", self.ITEMS, mode="full") == [(0, 4)]
        assert spans_of("verse THEN chorus", self.ITEMS, mode="full") == []

    def test_full_needs_single_block(self):
        items = spans("verse", "chorus", gap=1)
        assert spans_of("verse THEN chorus", items, mode="full") == []

    def test_start_anchored_at_block_zero_only(self):
        items = spans("verse", "x", "verse", gap=0.0)
        items[2:] = [(u, s + 1, e + 1) for u, s, e in items[2:]]
        assert spans_of("verse", items, mode="start") == [(0, 1)]


class TestProject:
    def test_level_one(self):
        a1 = FakeUnit("a1", 0, 5, 1)
        big = FakeUnit("A", 0, 10, 2)
        assert lanes.project([a1, big], 1) == [(a1, 0, 5), (big, 5, 10)]

    def test_level_two(self):
        a1 = FakeUnit("a1", 0, 5, 1)
        big = FakeUnit("A", 0, 10, 2)
        assert lanes.project([a1, big], 2) == [(big, 0, 10)]

    def test_merges_neighbouring_segments_of_same_unit(self):
        a = FakeUnit("a", 0, 4, 1)
        b = FakeUnit("b", 0, 2, 2)
        c = FakeUnit("c", 2, 4, 2)
        # at level 2 only b and c remain; at level 1, a is cut by nothing
        assert lanes.project([a, b, c], 2) == [(b, 0, 2), (c, 2, 4)]
        assert lanes.project([a, b, c], 1) == [(a, 0, 4)]

    def test_levelless_units_ignored(self):
        a = FakeUnit("a", 0, 4, 1)
        n = FakeUnit("n", 0, 4, None)
        assert lanes.project([a, n], 1) == [(a, 0, 4)]

    def test_tie_takes_shorter(self):
        long = FakeUnit("long", 0, 10, 1)
        short = FakeUnit("short", 2, 4, 1)
        assert lanes.project([long, short], 1) == [
            (long, 0, 2),
            (short, 2, 4),
            (long, 4, 10),
        ]

    def test_empty(self):
        assert lanes.project([], 1) == []


class TestFastPath:
    @pytest.mark.parametrize("q", ["verse+", "verse{2}", "verse{1,2}", "verse*", "*"])
    @pytest.mark.parametrize("gap", [0.0, 0.5])
    def test_agrees_with_general_matcher(self, q, gap):
        items = spans(
            "verse", "verse", "verse", "chorus", "verse", "verse", "bridge", gap=gap
        )
        seq = seq_of(q)
        fast = find_runs(seq, items, "any", False, fits)
        general = []
        for b0, b1 in sequences.blocks(items, False):
            block = items[b0:b1]
            r = Runs(fits, block)
            for i in range(len(block)):
                ends = [e for e in r.ends_steps(seq.steps, 0, i) if e > i]
                if ends:
                    j = max(ends)
                    general.append((b0 + i, b0 + j, r.assign(seq.steps, 0, i, j), None))
        assert fast == sequences.drop_contained(general)

    def test_agrees_with_two_step_pattern(self):
        items = spans("verse", "verse", "chorus", "verse")
        one = spans_of("verse+", items)
        two = spans_of("verse+ THEN verse?", items)
        assert one == two


class TestCheck:
    def test_called(self):
        calls = []
        run("verse", spans("verse"), check=lambda: calls.append(1))
        run("verse THEN verse", spans("verse", "verse"), check=lambda: calls.append(1))
        assert len(calls) == 2

    def test_exception_propagates(self):
        def check():
            raise TimeoutError("too slow")

        with pytest.raises(TimeoutError):
            run("verse", spans("verse"), check=check)
        with pytest.raises(TimeoutError):
            run("verse THEN verse", spans("verse", "verse"), check=check)


class TestPerformance:
    def test_long_lane_time(self):
        items = spans(*(["verse", "chorus"] * 200))
        t = time.perf_counter()
        run("verse+", items)
        run("(verse THEN chorus)+", items)
        assert time.perf_counter() - t < 1.0

    def test_long_lane_results(self):
        items = spans(*(["verse"] * 400))
        assert spans_of("verse+", items) == [(0, 400)]
        items = spans(*(["verse", "chorus"] * 200))
        assert spans_of("(verse THEN chorus)+", items) == [(0, 400)]
