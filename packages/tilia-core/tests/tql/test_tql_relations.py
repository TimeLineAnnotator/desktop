"""Relations (tql.md §8) on small fixtures built here: the fifteen relations in
the sentence form and in brackets, negated, with and without ``IN``, children,
nesting, tolerances and what ``Result.sql`` shows."""

from collections import Counter

import fixture_index
import pytest

from tilia_core import tql

FORM = ["Form (X)", "hierarchy"]


def hierarchy(name, units):
    return {"name": name, "kind": "hierarchy", "units": units}


def markers(name, units):
    return {"name": name, "kind": "marker", "units": units}


def fixture(*timelines, length=30):
    return {"length": length, "timelines": list(timelines)}


# Form (X): a b c at level 1, P (a b) and Q (c) at level 2.
FORM_UNITS = [
    ["a", 1, 0, 4],
    ["b", 1, 4, 8],
    ["c", 1, 8, 12],
    ["P", 2, 0, 8],
    ["Q", 2, 8, 12],
]
SPANS = fixture(
    hierarchy("Form (X)", FORM_UNITS),
    hierarchy(
        "Layers",
        [["w", 1, 0, 8], ["x", 1, 2, 6], ["y", 1, 8, 12], ["z", 1, 12, 14]],
    ),
    markers("Marks", [["p", 4], ["q", 9], ["r", 2], ["u", 7]]),
    markers("Other", [["s", 4.05], ["t", 5]]),
)
# The same form under a root R, so that a and b are R's grandchildren.
NESTED = fixture(hierarchy("Form (X)", FORM_UNITS + [["R", 3, 0, 12]]))
# P's children a and b have a 0.5 s hole between them.
HOLED = fixture(
    hierarchy("Form (X)", [["a", 1, 0, 3], ["b", 1, 3.5, 8], ["P", 2, 0, 8]])
)
# v starts 0.05 s before b and ends 0.05 s after it.
TOLERANCE = fixture(
    hierarchy("Form (X)", FORM_UNITS),
    hierarchy("Layers", [["v", 1, 3.95, 8.05]]),
)
# P has exactly a's extent and Q exactly b's: each parent lies in its child in
# time (tql.md §8, Q33), but is not below it in the hierarchy.
SAME_EXTENT = fixture(
    hierarchy("Form (X)", [["a", 1, 0, 4], ["b", 1, 4, 8], ["P", 2, 0, 4], ["Q", 2, 4, 8]])
)
# a starts 0.05 s before P, so the index does not make it P's child, though it
# lies in P within the tolerance; b is P's child.
LOOSE = fixture(
    hierarchy("Form (X)", [["a", 1, 0, 4], ["b", 1, 4, 8], ["P", 2, 0.05, 8]])
)
# Two phrases and three chords; the V begins in the first phrase and rings on
# into the second.
CHORDS = fixture(
    hierarchy("Form (X)", [["first", 1, 0, 8], ["second", 1, 8, 16]]),
    {
        "name": "Harmony",
        "kind": "harmony",
        "keys": [[0, "C", "major"]],
        "chords": [[0, "C", "major"], [6, "G", "major"], [12, "C", "major"]],
    },
    length=16,
)


def run(fix, query):
    return tql.run(fixture_index.build_index(fix), query)


def unit(c):
    return f"{c.label}@{c.start:g}"


def rows(fix, query):
    """The matches of ``query`` as ``"a@0 | b@4"`` strings, one per match."""
    got = run(fix, query)
    return Counter(
        " | ".join(", ".join(unit(c) for c in s) for s in m.slots) for m in got.matches
    )


def lefts(fix, query):
    return sorted(unit(m.slots[0][0]) for m in run(fix, query).matches)


# relation, target, the units of `* IN form` it holds for, on SPANS
TIMING = [
    ("DURING", "w IN Layers", ["P@0", "a@0", "b@4"]),
    ("CONTAINS", "x IN Layers", ["P@0"]),
    ("SAME START", "w IN Layers", ["P@0", "a@0"]),
    ("SAME END", "w IN Layers", ["P@0", "b@4"]),
    ("SAME", "w IN Layers", ["P@0"]),
    ("OVERLAPS", "x IN Layers", ["P@0", "a@0", "b@4"]),
    ("BEFORE", "y IN Layers", ["P@0", "a@0", "b@4"]),
    ("AFTER", "x IN Layers", ["Q@8", "c@8"]),
    ("STARTS BEFORE", "x IN Layers", ["P@0", "a@0"]),
    ("STARTS AFTER", "x IN Layers", ["Q@8", "b@4", "c@8"]),
]
ALL = ["P@0", "Q@8", "a@0", "b@4", "c@8"]


class TestTimingRelations:
    @pytest.mark.parametrize("rel, target, expected", TIMING)
    def test_sentence_form(self, rel, target, expected):
        got = run(SPANS, f"* IN form {rel} {target}")
        assert sorted(unit(m.slots[0][0]) for m in got.matches) == expected
        assert all(len(m.slots) == 2 and len(m.slots[1]) == 1 for m in got.matches)

    @pytest.mark.parametrize("rel, target, expected", TIMING)
    def test_in_brackets(self, rel, target, expected):
        got = run(SPANS, f"*[{rel} {target}] IN form")
        assert sorted(unit(m.slots[0][0]) for m in got.matches) == expected
        assert all(len(m.slots) == 1 for m in got.matches)

    @pytest.mark.parametrize("rel, target, expected", TIMING)
    def test_negated_sentence_form(self, rel, target, expected):
        got = run(SPANS, f"* IN form NOT {rel} {target}")
        assert sorted(unit(m.slots[0][0]) for m in got.matches) == sorted(
            set(ALL) - set(expected)
        )
        assert all(len(m.slots) == 1 for m in got.matches)

    @pytest.mark.parametrize("rel, target, expected", TIMING)
    def test_negated_in_brackets(self, rel, target, expected):
        got = run(SPANS, f"*[NOT {rel} {target}] IN form")
        assert sorted(unit(m.slots[0][0]) for m in got.matches) == sorted(
            set(ALL) - set(expected)
        )

    def test_the_result_is_the_left_unit_then_the_targets_steps(self):
        got = run(SPANS, "P IN form CONTAINS x IN Layers")
        assert [r["ids"] for r in got.rows] == ["f1:t1:c4"]
        assert got.rows[0]["label"] == "P"
        assert got.rows[0]["$1.label"] == "P"
        assert got.rows[0]["$2.label"] == "x"
        assert got.rows[0]["$2.timeline"] == "Layers · level 1"
        assert got.rows[0]["$1.timeline"] == "Form (X) · level 2"

    def test_a_left_unit_is_listed_once_per_target(self):
        assert rows(SPANS, "w IN Layers CONTAINS * IN form") == Counter(
            ["w@0 | a@0", "w@0 | b@4", "w@0 | P@0"]
        )

    def test_the_left_lane_limits_the_left_units(self):
        assert rows(SPANS, "* IN Marks DURING a IN form") == Counter(
            ["p@4 | a@0", "r@2 | a@0"]
        )
        assert rows(SPANS, "* IN Layers SAME START a IN form") == Counter(["w@0 | a@0"])

    def test_a_unit_is_never_in_a_relation_with_itself(self):
        # the same lane on both sides: a unit has its own start and extent,
        # but is not a match with itself
        assert rows(SPANS, "* IN form SAME * IN form") == Counter(
            ["Q@8 | c@8", "c@8 | Q@8"]
        )
        assert rows(SPANS, "* IN form SAME START * IN form") == Counter(
            ["P@0 | a@0", "a@0 | P@0", "Q@8 | c@8", "c@8 | Q@8"]
        )
        assert not rows(SPANS, "* IN Marks SAME * IN Marks")

    def test_a_lane_that_resolves_to_nothing_finds_nothing(self):
        # a role no timeline has: the lane exists in the language, and is empty
        assert not rows(SPANS, "* IN form DURING * IN cadences")
        assert not rows(SPANS, "*[DURING * IN cadences] IN form")
        assert lefts(SPANS, "* IN form NOT DURING * IN cadences") == ALL
        assert lefts(SPANS, "*[NOT DURING * IN cadences] IN form") == ALL


class TestPoints:
    def test_a_point_on_a_boundary_counts_for_both_units(self):
        assert rows(SPANS, "* IN Marks DURING a IN form") == Counter(
            ["p@4 | a@0", "r@2 | a@0"]
        )
        assert rows(SPANS, "* IN Marks DURING b IN form") == Counter(
            ["p@4 | b@4", "u@7 | b@4"]
        )

    def test_a_span_contains_points(self):
        assert rows(SPANS, "b IN form CONTAINS * IN Marks") == Counter(
            ["b@4 | p@4", "b@4 | u@7"]
        )

    def test_points_overlap_spans_they_lie_in(self):
        assert rows(SPANS, "* IN Marks OVERLAPS x IN Layers") == Counter(
            ["r@2 | x@2", "p@4 | x@2"]
        )
        assert rows(SPANS, "x IN Layers OVERLAPS * IN Marks") == Counter(
            ["x@2 | r@2", "x@2 | p@4"]
        )

    def test_points_overlap_points_within_the_tolerance(self):
        assert rows(SPANS, "* IN Marks OVERLAPS * IN Other") == Counter(
            ["p@4 | s@4.05"]
        )

    def test_points_overlap_in_python_as_in_sql(self):
        # a target with a condition SQL cannot test runs the Python twin of
        # the timing test, which reads points on the edges the same way
        assert lefts(SPANS, "*[OVERLAPS p[NOT AFTER u] IN Marks] IN form") == [
            "P@0",
            "a@0",
            "b@4",
        ]
        assert lefts(SPANS, "*[OVERLAPS a[NOT AFTER b] IN form] IN Marks") == [
            "p@4",
            "r@2",
        ]
        assert lefts(SPANS, "*[OVERLAPS s[NOT AFTER t] IN Other] IN Marks") == ["p@4"]
        assert lefts(SPANS, "*[OVERLAPS t[NOT AFTER s] IN Other] IN Marks") == []

    def test_a_point_starts_and_ends_where_it_is(self):
        assert rows(SPANS, "* IN Marks SAME START b IN form") == Counter(["p@4 | b@4"])
        assert rows(SPANS, "* IN Marks SAME END a IN form") == Counter(["p@4 | a@0"])
        assert rows(SPANS, "* IN Marks SAME * IN Other") == Counter(["p@4 | s@4.05"])

    def test_points_before_and_after_spans(self):
        assert lefts(SPANS, "* IN Marks BEFORE c IN form") == ["p@4", "r@2", "u@7"]
        assert lefts(SPANS, "* IN Marks AFTER b IN form") == ["q@9"]
        # p@4 starts with b, within the tolerance
        assert lefts(SPANS, "* IN Marks STARTS BEFORE b IN form") == ["r@2"]
        assert lefts(SPANS, "* IN Marks STARTS AFTER b IN form") == ["q@9", "u@7"]

    def test_a_span_before_and_after_points(self):
        assert rows(SPANS, "a IN form BEFORE * IN Marks") == Counter(
            ["a@0 | p@4", "a@0 | q@9", "a@0 | u@7"]
        )
        assert rows(SPANS, "c IN form AFTER * IN Marks") == Counter(
            ["c@8 | p@4", "c@8 | r@2", "c@8 | u@7"]
        )


class TestTolerance:
    def test_a_start_within_a_tenth_of_a_second_is_the_same_start(self):
        assert rows(TOLERANCE, "b IN form SAME START v IN Layers") == Counter(
            ["b@4 | v@3.95"]
        )
        assert rows(TOLERANCE, "b IN form SAME END v IN Layers") == Counter(
            ["b@4 | v@3.95"]
        )
        assert rows(TOLERANCE, "b IN form SAME v IN Layers") == Counter(
            ["b@4 | v@3.95"]
        )
        assert not rows(TOLERANCE, "a IN form SAME END v IN Layers")

    def test_touching_is_before_but_not_overlapping(self):
        assert rows(TOLERANCE, "a IN form BEFORE b IN form") == Counter(["a@0 | b@4"])
        assert not rows(TOLERANCE, "a IN form OVERLAPS b IN form")
        # 0.05 s over the boundary is inside the tolerance
        assert rows(TOLERANCE, "a IN form BEFORE v IN Layers") == Counter(
            ["a@0 | v@3.95"]
        )
        assert rows(TOLERANCE, "a IN form OVERLAPS v IN Layers") == Counter()

    def test_within_changes_the_tolerance_in_seconds(self):
        query = "b IN form SAME START v IN Layers WITHIN {}"
        assert not rows(TOLERANCE, query.format("0.01 s"))
        assert rows(TOLERANCE, query.format("0.06 s")) == Counter(["b@4 | v@3.95"])
        assert rows(TOLERANCE, query.format("60 ms")) == Counter(["b@4 | v@3.95"])
        assert not rows(TOLERANCE, query.format("40 ms"))
        assert rows(TOLERANCE, "b IN form SAME START v IN Layers WITHIN 1 s")

    def test_within_widens_a_bracket_relation_too(self):
        assert lefts(TOLERANCE, "*[SAME START v IN Layers WITHIN 60 ms] IN form") == [
            "b@4"
        ]
        assert not lefts(TOLERANCE, "*[SAME START v IN Layers WITHIN 10 ms] IN form")

    def test_within_limits_the_gap_of_before_and_after(self):
        base = "* IN form BEFORE y IN Layers WITHIN {}"
        assert lefts(SPANS, base.format("1 s")) == ["P@0", "b@4"]
        assert lefts(SPANS, base.format("5 s")) == ["P@0", "a@0", "b@4"]
        assert lefts(SPANS, "* IN form AFTER x IN Layers WITHIN 2 s") == ["Q@8", "c@8"]
        assert lefts(SPANS, "* IN form AFTER x IN Layers WITHIN 1 s") == []

    def test_within_limits_the_distance_between_starts(self):
        assert lefts(SPANS, "* IN form STARTS BEFORE x IN Layers WITHIN 3 s") == [
            "P@0",
            "a@0",
        ]
        assert lefts(SPANS, "* IN form STARTS BEFORE x IN Layers WITHIN 1 s") == []
        assert lefts(SPANS, "* IN form STARTS AFTER x IN Layers WITHIN 2 s") == ["b@4"]

    def test_within_limits_the_gap_without_in_too(self):
        # without IN the relation runs in Python, with the same limit
        assert lefts(SPANS, "*[BEFORE c WITHIN 1 s] IN form") == ["P@0", "b@4"]
        assert rows(SPANS, "* IN form BEFORE c WITHIN 1 s") == Counter(
            ["P@0 | c@8", "b@4 | c@8"]
        )
        assert lefts(SPANS, "*[AFTER a WITHIN 1 s] IN form") == ["b@4"]
        assert lefts(SPANS, "*[STARTS BEFORE c WITHIN 5 s] IN form") == ["b@4"]
        assert lefts(SPANS, "*[STARTS AFTER a WITHIN 5 s] IN form") == ["b@4"]

    @pytest.mark.parametrize("unit_", ["bar", "bars", "beat", "beats"])
    def test_within_in_bars_and_beats_needs_a_time_map(self, unit_):
        for query in (
            f"* IN form DURING w IN Layers WITHIN 2 {unit_}",
            f"*[DURING w IN Layers WITHIN 2 {unit_}] IN form",
            f"*[NOT DURING w IN Layers WITHIN 2 {unit_}] IN form",
            f"* IN form NOT DURING w IN Layers WITHIN 2 {unit_}",
            f"* IN form SAME START a WITHIN 2 {unit_}",
        ):
            got = run(SPANS, query)
            assert not got.rows, query
            assert got.warnings == ["1 file without a time map could not answer"]


class TestSql:
    def test_the_sentence_form_joins_the_two_sides_with_the_tolerance(self):
        got = run(SPANS, "* IN form DURING w IN Layers")
        assert "FROM components a JOIN components b ON" in got.sql
        assert "0.1" in got.sql
        assert "?" not in got.sql
        assert "'f1:t1'" in got.sql and "'f1:t2'" in got.sql

    def test_the_bracket_form_is_an_exists(self):
        got = run(SPANS, "*[DURING w IN Layers] IN form")
        assert "EXISTS (SELECT 1 FROM components" in got.sql
        assert "NOT EXISTS" not in got.sql
        assert "0.1" in got.sql

    def test_a_negation_is_a_not_exists(self):
        for query in (
            "*[NOT DURING w IN Layers] IN form",
            "* IN form NOT DURING w IN Layers",
        ):
            got = run(SPANS, query)
            assert "NOT EXISTS" in got.sql and "0.1" in got.sql

    def test_within_is_written_in_seconds(self):
        assert "0.06" in run(SPANS, "* IN form SAME START w IN Layers WITHIN 60 ms").sql
        assert "2.0" in run(SPANS, "* IN form SAME START w IN Layers WITHIN 2 s").sql
        assert (
            "<= 0.1"
            not in run(SPANS, "* IN form SAME START w IN Layers WITHIN 2 s").sql
        )

    def test_every_relation_runs_sql(self):
        for rel, target, _ in TIMING:
            got = run(SPANS, f"* IN form {rel} {target}")
            assert "JOIN components b ON" in got.sql and "0.1" in got.sql

    def test_the_order_relations_run_python_and_read_the_lanes(self):
        got = run(SPANS, "*[STARTS WITH a] IN form")
        assert "JOIN components b" not in got.sql
        assert "EXISTS (SELECT 1 FROM components" not in got.sql

    def test_run_writes_nothing(self):
        index = fixture_index.build_index(SPANS)
        con = index.connection()
        changes = con.total_changes
        master = con.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
        for query in (
            "* IN form DURING w IN Layers",
            "*[CONSISTS OF a THEN b] IN form",
            "* IN Marks ENDS b IN form",
        ):
            tql.run(index, query)
        assert con.total_changes == changes
        assert (
            con.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
            == master
        )


class TestOrderRelations:
    def test_starts_with(self):
        assert rows(SPANS, "* IN form STARTS WITH a") == Counter(["P@0 | a@0"])
        assert lefts(SPANS, "*[STARTS WITH a] IN form") == ["P@0"]
        assert lefts(SPANS, "*[STARTS WITH b] IN form") == []

    def test_ends_with(self):
        assert rows(SPANS, "* IN form ENDS WITH b") == Counter(["P@0 | b@4"])
        assert lefts(SPANS, "*[ENDS WITH b] IN form") == ["P@0"]
        assert lefts(SPANS, "*[ENDS WITH a] IN form") == []

    def test_consists_of_takes_every_unit_in_order(self):
        assert rows(SPANS, "P IN form CONSISTS OF a THEN b") == Counter(
            ["P@0 | a@0 | b@4"]
        )
        assert lefts(SPANS, "*[CONSISTS OF a THEN b] IN form") == ["P@0"]
        assert lefts(SPANS, "*[CONSISTS OF a] IN form") == []
        assert lefts(SPANS, "*[CONSISTS OF b THEN a] IN form") == []
        assert lefts(SPANS, "*[CONSISTS OF c] IN form") == ["Q@8"]

    def test_a_target_sequence_gets_one_slot_per_step(self):
        got = run(NESTED, "R IN form CONTAINS P THEN Q")
        assert [[c.label for c in s] for s in got.matches[0].slots] == [
            ["R"],
            ["P"],
            ["Q"],
        ]
        assert got.rows[0]["$3.label"] == "Q"

    def test_a_quantified_target_fills_one_slot(self):
        got = run(SPANS, "P IN form CONSISTS OF (a OR b){2}")
        assert [[c.label for c in s] for s in got.matches[0].slots] == [
            ["P"],
            ["a", "b"],
        ]

    def test_with_in_the_target_is_looked_for_by_time_in_that_lane(self):
        assert lefts(SPANS, "*[STARTS WITH r IN Marks] IN form") == ["P@0", "a@0"]
        assert lefts(SPANS, "*[ENDS WITH p IN Marks] IN form") == ["a@0"]
        assert lefts(SPANS, "*[ENDS WITH u IN Marks] IN form") == ["P@0", "b@4"]
        assert lefts(SPANS, "b[STARTS WITH p THEN u IN Marks] IN form") == ["b@4"]
        assert lefts(SPANS, "b[CONSISTS OF p THEN u IN Marks] IN form") == ["b@4"]
        assert lefts(SPANS, "b[CONSISTS OF p IN Marks] IN form") == []
        assert lefts(SPANS, "b[ENDS WITH p IN Marks] IN form") == []

    def test_starts_and_ends_read_the_left_units_own_lane(self):
        assert rows(SPANS, "* IN Marks STARTS a IN form") == Counter(["r@2 | a@0"])
        assert rows(SPANS, "* IN Marks ENDS a IN form") == Counter(["p@4 | a@0"])
        assert rows(SPANS, "* IN Marks STARTS b IN form") == Counter(["p@4 | b@4"])
        assert rows(SPANS, "* IN Marks ENDS b IN form") == Counter(["u@7 | b@4"])

    def test_starts_and_ends_without_in_read_the_descendants(self):
        assert rows(SPANS, "* IN form STARTS P") == Counter(["a@0 | P@0"])
        assert rows(SPANS, "* IN form ENDS P") == Counter(["b@4 | P@0"])
        assert rows(SPANS, "b IN form STARTS P") == Counter()

    def test_starts_and_ends_with_in_mirror_starts_with_and_ends_with(self):
        # tql.md §8: A STARTS B is B STARTS WITH A, and with IN a unit of the
        # same extent lies inside the other in time (Q33), whichever is the
        # parent; without IN the target's lane is read through the hierarchy
        assert rows(SAME_EXTENT, "P IN form STARTS WITH a IN form") == Counter(
            ["P@0 | a@0"]
        )
        assert rows(SAME_EXTENT, "a IN form STARTS P IN form") == Counter(
            ["a@0 | P@0"]
        )
        assert rows(SAME_EXTENT, "a IN form STARTS WITH P IN form") == Counter(
            ["a@0 | P@0"]
        )
        assert rows(SAME_EXTENT, "P IN form STARTS a IN form") == Counter(
            ["P@0 | a@0"]
        )
        assert rows(SAME_EXTENT, "Q IN form ENDS WITH b IN form") == Counter(
            ["Q@4 | b@4"]
        )
        assert rows(SAME_EXTENT, "b IN form ENDS Q IN form") == Counter(
            ["b@4 | Q@4"]
        )
        assert rows(SAME_EXTENT, "b IN form ENDS WITH Q IN form") == Counter(
            ["b@4 | Q@4"]
        )
        assert rows(SAME_EXTENT, "Q IN form ENDS b IN form") == Counter(
            ["Q@4 | b@4"]
        )
        assert lefts(SAME_EXTENT, "*[STARTS a IN form] IN form") == ["P@0"]
        assert lefts(SAME_EXTENT, "*[ENDS b IN form] IN form") == ["Q@4"]
        assert not rows(SAME_EXTENT, "P IN form STARTS a")
        assert not rows(SAME_EXTENT, "Q IN form ENDS b")

    def test_negated_order_relations_have_no_second_unit(self):
        got = run(SPANS, "* IN form NOT STARTS WITH a")
        assert sorted(unit(m.slots[0][0]) for m in got.matches) == [
            "Q@8",
            "a@0",
            "b@4",
            "c@8",
        ]
        assert all(len(m.slots) == 1 for m in got.matches)
        assert lefts(SPANS, "*[NOT ENDS WITH b] IN form") == [
            "Q@8",
            "a@0",
            "b@4",
            "c@8",
        ]
        assert rows(SPANS, "Q IN form NOT CONSISTS OF a THEN b") == Counter(["Q@8"])
        assert not rows(SPANS, "P IN form NOT CONSISTS OF a THEN b")

    def test_in_brackets_the_inner_units_are_tests_only(self):
        got = run(SPANS, "*[CONSISTS OF a THEN b] IN form")
        assert [[c.label for c in s] for s in got.matches[0].slots] == [["P"]]
        assert got.rows[0]["label"] == "P"


class TestWithoutIn:
    def test_during_looks_at_the_ancestors(self):
        assert rows(SPANS, "a IN form DURING P") == Counter(["a@0 | P@0"])
        assert not rows(SPANS, "c IN form DURING P")
        assert lefts(SPANS, "*[DURING P] IN form") == ["a@0", "b@4"]
        assert lefts(SPANS, "*[NOT DURING P] IN form") == ["P@0", "Q@8", "c@8"]
        assert lefts(NESTED, "*[DURING R] IN form") == [
            "P@0",
            "Q@8",
            "a@0",
            "b@4",
            "c@8",
        ]

    def test_during_without_in_reads_the_ancestors_not_the_time(self):
        # a lies in P within the tolerance, but P is not its parent
        assert rows(LOOSE, "b IN form DURING P") == Counter(["b@4 | P@0.05"])
        assert not rows(LOOSE, "a IN form DURING P")
        assert lefts(LOOSE, "*[DURING P] IN form") == ["b@4"]
        assert lefts(LOOSE, "*[NOT DURING P] IN form") == ["P@0.05", "a@0"]
        # with IN, time decides
        assert lefts(LOOSE, "*[DURING P IN form] IN form") == ["a@0", "b@4"]

    def test_the_order_relations_without_in_read_the_descendants_not_the_time(self):
        assert lefts(LOOSE, "*[CONTAINS a] IN form") == []
        assert lefts(LOOSE, "*[CONTAINS b] IN form") == ["P@0.05"]
        assert lefts(LOOSE, "*[STARTS WITH a] IN form") == []
        assert lefts(LOOSE, "*[STARTS WITH b] IN form") == ["P@0.05"]
        assert not rows(LOOSE, "P IN form CONSISTS OF a THEN b")
        assert rows(LOOSE, "P IN form CONSISTS OF b") == Counter(["P@0.05 | b@4"])
        assert rows(LOOSE, "* IN form STARTS P") == Counter(["b@4 | P@0.05"])
        # with IN, time decides
        assert lefts(LOOSE, "*[CONTAINS a IN form] IN form") == ["P@0.05"]
        assert lefts(LOOSE, "*[STARTS WITH a IN form] IN form") == ["P@0.05"]

    def test_contains_looks_at_the_descendants(self):
        assert rows(SPANS, "P IN form CONTAINS b") == Counter(["P@0 | b@4"])
        assert not rows(SPANS, "P IN form CONTAINS c")
        assert lefts(NESTED, "*[CONTAINS a] IN form") == ["P@0", "R@0"]
        assert lefts(NESTED, "*[CONTAINS a THEN b] IN form") == ["P@0", "R@0"]
        assert lefts(NESTED, "*[CONTAINS b THEN c] IN form") == ["R@0"]

    def test_the_timing_relations_look_at_every_level_of_the_timeline(self):
        assert rows(SPANS, "* IN form SAME START a") == Counter(["P@0 | a@0"])
        assert rows(SPANS, "* IN form SAME END b") == Counter(["P@0 | b@4"])
        assert rows(SPANS, "P IN form SAME END b") == Counter(["P@0 | b@4"])
        assert lefts(SPANS, "* IN form BEFORE c") == ["P@0", "a@0", "b@4"]
        assert lefts(SPANS, "*[AFTER a] IN form") == ["Q@8", "b@4", "c@8"]
        assert lefts(SPANS, "*[STARTS AFTER a] IN form") == ["Q@8", "b@4", "c@8"]
        assert lefts(SPANS, "*[SAME P] IN form") == []
        assert lefts(NESTED, "*[OVERLAPS Q] IN form") == ["R@0", "c@8"]

    def test_the_timing_relations_are_the_same_with_and_without_in(self):
        for rel, _, _ in TIMING:
            for target in ("a", "b", "P", "Q"):
                with_in = lefts(SPANS, f"*[{rel} {target} IN form] IN form")
                without = lefts(SPANS, f"*[{rel} {target}] IN form")
                if rel in ("DURING", "CONTAINS"):
                    continue  # ancestors and descendants, not time alone
                assert with_in == without, (rel, target)

    def test_the_target_is_in_the_left_units_own_timeline(self):
        assert not lefts(SPANS, "*[SAME START w] IN form")
        assert lefts(SPANS, "*[SAME START w IN Layers] IN form") == ["P@0", "a@0"]


class TestChildren:
    def test_children_in_a_row(self):
        assert lefts(NESTED, "P[a THEN b] IN form") == ["P@0"]
        assert lefts(NESTED, "*[a] IN form") == ["P@0"]
        assert lefts(NESTED, "*[b] IN form") == ["P@0"]
        assert lefts(NESTED, "*[a THEN c] IN form") == []
        assert lefts(NESTED, "*[P THEN Q] IN form") == ["R@0"]

    def test_a_count_is_a_row_of_children(self):
        assert lefts(NESTED, "*[a{2}] IN form") == []
        assert lefts(SPANS, "*[*{2}] IN form") == ["P@0"]
        assert lefts(SPANS, "*[*{3}] IN form") == []

    def test_grandchildren_are_not_children(self):
        assert lefts(NESTED, "R[a] IN form") == []
        assert lefts(NESTED, "R[P] IN form") == ["R@0"]
        assert lefts(NESTED, "R[CONTAINS a] IN form") == ["R@0"]

    def test_a_leaf_has_no_children(self):
        assert lefts(NESTED, "a[*] IN form") == []
        assert lefts(NESTED, "a[NOT *] IN form") == ["a@0"]

    def test_negated_children(self):
        assert lefts(NESTED, "*[NOT a] IN form") == ["Q@8", "R@0", "a@0", "b@4", "c@8"]
        assert lefts(NESTED, "P[NOT c] IN form") == ["P@0"]
        assert lefts(NESTED, "P[NOT a] IN form") == []

    def test_children_and_relations_join_with_and(self):
        assert lefts(SPANS, "*[a AND CONTAINS x IN Layers] IN form") == ["P@0"]
        assert lefts(SPANS, "*[a AND NOT CONTAINS x IN Layers] IN form") == []
        assert lefts(SPANS, "*[c AND CONTAINS x IN Layers] IN form") == []

    def test_children_in_a_sequence(self):
        assert rows(NESTED, "P THEN Q[c] IN form") == Counter(["P@0 | Q@8"])
        assert not rows(NESTED, "P THEN Q[a] IN form")

    def test_children_ignore_the_gaps_between_them(self):
        assert lefts(HOLED, "P[a THEN b] IN form") == ["P@0"]
        assert lefts(HOLED, "P[*{2}] IN form") == ["P@0"]
        assert lefts(HOLED, "P[a THEN b]") == ["P@0"]
        assert lefts(HOLED, "*[NOT a THEN b] IN form") == ["a@0", "b@3.5"]
        # outside brackets, the lane keeps its hole
        assert not rows(HOLED, "a THEN b IN form")

    def test_children_without_in_look_through_every_lane(self):
        assert lefts(NESTED, "P[a THEN b]") == ["P@0"]


class TestNesting:
    def test_a_relation_inside_a_relation(self):
        assert lefts(NESTED, "*[CONTAINS P[ENDS WITH b]] IN form") == ["R@0"]
        assert lefts(NESTED, "*[CONTAINS Q[ENDS WITH b]] IN form") == []
        assert lefts(NESTED, "*[CONTAINS Q[ENDS WITH c]] IN form") == ["R@0"]

    def test_a_nested_relation_in_sql(self):
        query = "*[CONTAINS r[DURING a IN form] IN Marks] IN form"
        got = run(SPANS, query)
        assert sorted(unit(m.slots[0][0]) for m in got.matches) == ["P@0", "a@0"]
        assert got.sql.count("EXISTS (SELECT 1 FROM components") == 2

    def test_a_target_with_order_conditions_goes_to_python_inside_brackets(self):
        assert lefts(NESTED, "R[CONTAINS P[ENDS WITH b] IN form] IN form") == ["R@0"]
        assert lefts(NESTED, "R[CONTAINS Q[ENDS WITH b] IN form] IN form") == []
        assert lefts(NESTED, "R[NOT CONTAINS Q[ENDS WITH b] IN form] IN form") == [
            "R@0"
        ]

    def test_a_target_with_order_conditions_in_the_sentence_form(self):
        assert rows(NESTED, "R IN form CONTAINS P[ENDS WITH b] IN form") == Counter(
            ["R@0 | P@0"]
        )
        assert not rows(NESTED, "R IN form CONTAINS Q[ENDS WITH b] IN form")
        assert rows(NESTED, "R IN form NOT CONTAINS Q[ENDS WITH b] IN form") == Counter(
            ["R@0"]
        )

    def test_the_left_unit_of_the_sentence_form_can_have_conditions(self):
        assert rows(SPANS, "*[a] IN form CONTAINS x IN Layers") == Counter(
            ["P@0 | x@2"]
        )
        assert rows(
            SPANS, "*[CONSISTS OF a THEN b] IN form SAME w IN Layers"
        ) == Counter(["P@0 | w@0"])

    def test_a_unit_with_only_conditions(self):
        assert lefts(SPANS, "[CONSISTS OF a THEN b] IN form") == ["P@0"]
        assert lefts(SPANS, "[DURING w IN Layers] IN form") == ["P@0", "a@0", "b@4"]


class TestLabelsAndMatches:
    def test_the_label_and_the_relation_both_hold(self):
        assert lefts(SPANS, "a[DURING w IN Layers] IN form") == ["a@0"]
        assert lefts(SPANS, "c[DURING w IN Layers] IN form") == []
        assert lefts(SPANS, "NOT a[DURING w IN Layers] IN form") == ["P@0", "b@4"]

    def test_a_relation_inside_a_sequence(self):
        assert rows(SPANS, "a[DURING w IN Layers] THEN b IN form") == Counter(
            ["a@0 | b@4"]
        )
        assert not rows(SPANS, "a THEN b[DURING y IN Layers] IN form")

    def test_a_match_found_in_several_lanes_is_reported_once(self):
        got = run(NESTED, "a[DURING P] IN form")
        assert len(got.matches) == 1
        assert len(run(NESTED, "*[CONTAINS a] IN form").matches) == 2

    def test_max_matches_stops_a_relation_query(self):
        got = run(SPANS, "* IN form DURING w IN Layers")
        assert len(got.matches) == 3
        index = fixture_index.build_index(SPANS)
        capped = tql.run(index, "* IN form DURING w IN Layers", max_matches=2)
        assert len(capped.matches) == 2 and capped.stopped == "max_matches"

    def test_more_than_one_file(self):
        index = fixture_index.build_index(SPANS, NESTED)
        got = tql.run(index, "*[CONTAINS a] IN form")
        assert sorted(m.slots[0][0].file_id for m in got.matches) == ["f1", "f2", "f2"]

    @pytest.mark.parametrize(
        "query, expected",
        [
            ("p OR q IN Marks DURING a IN form", ["p@2 | a@0", "q@2 | a@0"]),
            ("p IN Marks DURING a OR b IN form", ["p@2 | a@0", "p@6 | b@4"]),
            (
                "p OR q IN Marks DURING a OR b IN form",
                ["p@2 | a@0", "q@6 | b@4", "q@2 | a@0", "p@6 | b@4"],
            ),
            (
                "a OR b IN form CONTAINS p OR q IN Marks",
                ["a@0 | p@2", "b@4 | q@6", "a@0 | q@2", "b@4 | p@6"],
            ),
            ("*[DURING a OR b IN form] IN Marks", ["p@2", "q@6", "q@2", "p@6"]),
        ],
    )
    def test_an_or_keeps_its_file_lane_and_timing_tests(self, query, expected):
        # The two files swap p and q, and r lies in neither a nor b.
        one = fixture(
            hierarchy("Form (X)", [["a", 1, 0, 4], ["b", 1, 4, 8]]),
            markers("Marks", [["p", 2], ["q", 6], ["r", 20]]),
        )
        two = fixture(
            hierarchy("Form (X)", [["a", 1, 0, 4], ["b", 1, 4, 8]]),
            markers("Marks", [["q", 2], ["p", 6], ["r", 20]]),
        )
        got = tql.run(fixture_index.build_index(one, two), query)
        for m in got.matches:
            assert len({c.file_id for s in m.slots for c in s}) == 1
        assert Counter(
            " | ".join(", ".join(unit(c) for c in s) for s in m.slots)
            for m in got.matches
        ) == Counter(expected)

    def test_chords_in_a_relation_target(self):
        harmony = fixture(
            hierarchy("Form (X)", [["phrase", 1, 0, 8]]),
            {
                "name": "Harmony",
                "kind": "harmony",
                "keys": [[0, "C", "major"]],
                "chords": [[0, "C", "major"], [4, "G", "major"]],
            },
        )
        assert lefts(harmony, "phrase[ENDS WITH V IN harmony] IN form") == ["phrase@0"]
        assert lefts(harmony, "phrase[ENDS WITH I IN harmony] IN form") == []
        assert lefts(harmony, "phrase[CONTAINS V IN harmony] IN form") == ["phrase@0"]
        assert lefts(harmony, "phrase IN form CONTAINS I IN harmony") == ["phrase@0"]
        assert lefts(harmony, "phrase[CONTAINS * IN harmony] IN form") == ["phrase@0"]
        assert lefts(harmony, "* IN harmony DURING phrase IN form") == ["C@0", "G@4"]

    def test_a_chord_counts_where_it_begins(self):
        # tql.md §8: inside a unit, chords and keys count where they begin, so
        # the V that begins in the first phrase and rings on into the second
        # is in the first; SQL (the join, EXISTS) and Python read it alike
        assert rows(CHORDS, "* IN form CONTAINS * IN harmony") == Counter(
            ["first@0 | C@0", "first@0 | G@6", "second@8 | C@12"]
        )
        assert lefts(CHORDS, "*[DURING first IN form] IN harmony") == ["C@0", "G@6"]
        assert lefts(CHORDS, "*[CONSISTS OF *{2} IN harmony] IN form") == ["first@0"]
        # a target with a condition SQL cannot test runs the Python twin
        assert lefts(CHORDS, "*[DURING first[NOT zzz] IN form] IN harmony") == [
            "C@0",
            "G@6",
        ]
