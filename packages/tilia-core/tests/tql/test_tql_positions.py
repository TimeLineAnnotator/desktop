"""Positions, lengths, distances, percentages, ``WITHIN`` in bars and beats and
the ``bars`` lane (tql.md §4, §6.1, §7.3, §7.4, §8), on the examples.toml
fixtures ``sonata``, ``repeat`` and ``pop`` and on small ones built here."""

import gc
import sqlite3
import weakref

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import sqlfuncs

DATA = examples.load()["fixtures"]
NO_MAP = "1 file without a time map could not answer"


def beats(bars, numbers=None):
    tl = {"name": "Beats", "kind": "beats", "start": 0, "every": 1}
    tl.update({"beats_per_bar": 4, "bars": bars})
    if numbers:
        tl["numbers"] = numbers
    return tl


def hierarchy(name, units):
    return {"name": name, "kind": "hierarchy", "units": units}


def markers(name, units):
    return {"name": name, "kind": "marker", "units": units}


def fixture(*timelines, length=32):
    return {"length": length, "timelines": list(timelines)}


# Eight bars of four beats, a beat a second. Form: v in bars 1-2, c in bar 4-5
# (a hole of one bar before it), d in bars 6-8 (a hole of two beats before it).
GRID = fixture(
    hierarchy("Form (Z)", [["v", 1, 0, 8], ["c", 1, 12, 20], ["d", 1, 22, 30]]),
    markers("Cadences", [["HC", 4], ["PAC", 12], ["PAC", 28]]),
    markers("Notes", [["n1", 12.5], ["n2", 14]]),
    beats(8),
)
# The same without a time map.
UNMAPPED = fixture(*GRID["timelines"][:3])
EXPOSITION = DATA["exposition"]


def index_of(fix):
    return fixture_index.build_index(fix)


def run(fix, query):
    return tql.run(index_of(fix) if isinstance(fix, dict) else fix, query)


def units(fix, query):
    """The units of every match, each as ``label@start``, step by step."""
    got = run(fix, query)
    has_target = tql.parse(query).has_target
    out = []
    for m in got.matches:
        steps = [
            ",".join(
                f"{c.label}@{c.start:g}"
                for k, c in enumerate(slot)
                if not has_target or m.is_target(n, k)
            )
            for n, slot in enumerate(m.slots, 1)
        ]
        out.append("|".join(s for s in steps if s))
    return sorted(out)


def sonata(query):
    return units(DATA["sonata"], query)


# --------------------------------------------------------------------------- #
# Position conditions
# --------------------------------------------------------------------------- #
class TestPositionFields:
    def test_bar_is_the_printed_number_where_the_unit_starts(self):
        assert sonata("PAC[bar = 40] IN cadences") == ["PAC@157"]
        assert sonata("PAC[bar = 16] IN cadences") == ["PAC@60"]
        assert sonata("PAC[bar = 15..16] IN cadences") == ["PAC@60"]
        assert sonata("PAC[bar > 16] IN cadences") == ["PAC@157"]
        assert sonata("PAC[bar != 16] IN cadences") == ["PAC@157"]
        assert sonata("*[bar = 25] IN form") == ["ST@96", "presentation@96"]

    def test_the_fields_in_where_read_the_one_unit(self):
        assert sonata("PAC IN cadences WHERE bar = 40") == ["PAC@157"]
        assert sonata("PAC IN cadences WHERE $1.bar = 40") == ["PAC@157"]
        assert sonata("HC THEN PAC IN cadences WHERE $2.bar = 40") == ["HC@128|PAC@157"]

    def test_beat_is_fractional(self):
        assert sonata("PAC[beat = 2] IN cadences") == ["PAC@157"]
        assert sonata("HC[beat = 1] IN cadences") == ["HC@128", "HC@92"]
        fix = fixture(markers("M", [["a", 2.5], ["b", 5]]), beats(2))
        assert units(fix, "*[beat = 3.5] IN markers") == ["a@2.5"]
        assert units(fix, "*[beat >= 2] IN markers") == ["a@2.5", "b@5"]

    def test_bar_count_label_and_beat_count(self):
        assert sonata("PAC[bar.count = 40] IN cadences") == ["PAC@157"]
        assert sonata("PAC[bar.label = 40] IN cadences") == ["PAC@157"]
        assert sonata('PAC[bar.label = "16"] IN cadences') == ["PAC@60"]
        assert sonata("PAC[bar.beat_count = 4] IN cadences") == ["PAC@157", "PAC@60"]
        assert sonata("PAC[bar.beat_count = 3] IN cadences") == []
        assert sonata(
            "PAC IN cadences WHERE bar.beat_count = 4 AND bar.count = 16"
        ) == ["PAC@60"]

    def test_pass(self):
        assert sonata("PAC[pass = 1] IN cadences") == ["PAC@157", "PAC@60"]
        assert sonata("PAC[pass = 2] IN cadences") == []

    def test_end_bar_excludes_the_end_point(self):
        assert sonata("MT[end_bar = 16] IN form") == ["MT@0"]
        assert sonata("MT[end_bar = 17] IN form") == []
        assert sonata("ST[end_bar = 40] IN form") == ["ST@96"]

    def test_the_end_bar_of_a_point_is_its_bar(self):
        assert sonata("*[end_bar = 16] IN cadences") == ["PAC@60"]
        assert sonata("*[end_bar = 16] IN cadences") == sonata(
            "*[bar = 16] IN cadences"
        )

    def test_a_position_can_be_asked_for_any(self):
        assert len(sonata("*[bar = *] IN cadences")) == 4


class TestDownbeat:
    def test_downbeat(self):
        assert sonata("*[downbeat] IN cadences") == ["HC@128", "HC@92", "PAC@60"]
        assert sonata("* IN cadences WHERE downbeat") == ["HC@128", "HC@92", "PAC@60"]

    def test_not_downbeat(self):
        assert sonata("*[NOT downbeat] IN cadences") == ["PAC@157"]
        assert sonata("* IN cadences WHERE NOT downbeat") == ["PAC@157"]


class TestRepeats:
    def run(self, query):
        return units(DATA["repeat"], query)

    def test_a_bar_matches_every_pass(self):
        assert self.run("*[bar = 12] IN form") == ["b2@44", "b2@76"]

    def test_pass_picks_one(self):
        assert self.run("*[bar = 12 AND pass = 2] IN form") == ["b2@76"]
        assert self.run("*[bar = 12 AND pass = 1] IN form") == ["b2@44"]
        assert self.run("*[pass = 2] IN form") == ["B@64", "b1@64", "b2@76"]

    def test_bar_count_counts_in_playing_order(self):
        assert self.run("*[bar.count = 20] IN form") == ["b2@76"]
        assert self.run("*[bar.count = 12] IN form") == ["b2@44"]


class TestWithoutATimeMap:
    @pytest.mark.parametrize(
        "query",
        [
            "*[bar = 1] IN form",
            "*[NOT bar = 1] IN form",
            "*[bar != 1] IN form",
            "*[bar.label = 1] IN form",
            "*[NOT bar.label = 1] IN form",
            "*[pass = 1..2] IN form",
            "*[NOT pass = 1..2] IN form",
            "*[downbeat] IN form",
            "*[NOT downbeat] IN form",
            "* IN form WHERE bar = 1",
            "* IN form WHERE NOT bar = 1",
            "* IN form WHERE NOT downbeat",
            "ST THEN * IN form WHERE $1.bar != $2.bar",
        ],
    )
    def test_a_file_without_one_never_matches_and_warns(self, query):
        got = run(EXPOSITION, query)
        assert got.rows == []
        assert got.warnings == [NO_MAP]

    def test_the_warning_counts_the_files(self):
        index = fixture_index.build_index(EXPOSITION, UNMAPPED, DATA["sonata"])
        got = tql.run(index, "*[bar = 25] IN form")
        assert {r["file"] for r in got.rows} == {"f3"}
        assert got.warnings == ["2 files without a time map could not answer"]

    def test_a_file_with_one_does_not_warn(self):
        assert run(DATA["sonata"], "*[bar = 25] IN form").warnings == []

    def test_a_query_that_needs_no_map_does_not_warn(self):
        assert run(EXPOSITION, "*[start >= 10] IN form").warnings == []

    def test_a_time_off_the_map_never_matches(self):
        fix = fixture(markers("M", [["a", 1], ["off", 100]]), beats(2), length=200)
        assert units(fix, "*[bar = 1] IN markers") == ["a@1"]
        assert units(fix, "*[NOT bar = 1] IN markers") == []
        assert units(fix, "*[NOT downbeat] IN markers") == ["a@1"]


# --------------------------------------------------------------------------- #
# Percentages of the piece
# --------------------------------------------------------------------------- #
class TestPercentages:
    def test_start_end_and_time(self):
        pop = DATA["pop"]  # 128 s
        got = units(pop, '*[start >= 50%] IN "Form (A)"')
        assert "chorus@72" in got and "chorus@40" not in got
        assert units(pop, '*[end <= 25%] IN "Form (A)"') == ["intro@0", "verse@8"]
        assert units(pop, '*[end <= 6%] IN "Form (A)"') == []
        assert units(pop, '*[start = 0%..10%] IN "Form (A)"') == [
            "A@8",
            "intro@0",
            "verse@8",
        ]
        assert units(pop, '*[start != 0%..10%] IN "Form (A)"') == units(
            pop, '*[start > 10%] IN "Form (A)"'
        )
        assert units(pop, '* IN "Form (A)" WHERE start >= 90%') == ["outro@120"]
        fix = fixture(markers("M", [["a", 3], ["b", 20]]), length=40)
        assert units(fix, "*[time >= 25%] IN markers") == ["b@20"]
        assert units(fix, "*[time < 25%] IN markers") == ["a@3"]

    def test_the_middle_third(self):
        assert units(DATA["pop"], "*[start >= 33% AND end <= 67%] IN form") == [
            "verse@56",
            "verse@56",
        ]

    def test_a_file_without_a_length_never_matches_and_warns(self):
        fix = fixture(hierarchy("Form (Z)", [["v", 1, 0, 8]]), length=None)
        for query in (
            "*[start >= 0%] IN form",
            "*[NOT start >= 0%] IN form",
            "* IN form WHERE start >= 0%",
            "* IN form WHERE NOT start >= 0%",
        ):
            got = run(fix, query)
            assert got.rows == [], query
            assert got.warnings == ["1 file without a media length could not answer"]

    def test_a_file_with_a_length_does_not_warn(self):
        assert run(DATA["pop"], "*[start >= 50%] IN form").warnings == []


# --------------------------------------------------------------------------- #
# Lengths
# --------------------------------------------------------------------------- #
class TestLengths:
    def test_bars_and_beats(self):
        assert sonata("*[duration = 8 bars] IN form") == [
            "Transition@64",
            "continuation@32",
            "presentation@0",
        ]
        assert sonata("Transition[duration = 32 beats] IN form") == ["Transition@64"]
        assert sonata("Transition[duration = 7..9 bars] IN form") == ["Transition@64"]
        assert sonata("Transition[duration = 9 bars] IN form") == []
        assert sonata("Transition[duration > 7 bars] IN form") == ["Transition@64"]
        assert sonata("Transition[duration < 8 bars] IN form") == []
        assert sonata("Transition[duration = 8bars] IN form") == ["Transition@64"]

    def test_a_length_in_where(self):
        assert sonata("Transition IN form WHERE duration = 8 bars") == ["Transition@64"]
        assert sonata("MT THEN Transition IN form WHERE $2.duration = 8 bars") == [
            "MT@0|Transition@64"
        ]
        assert sonata("MT THEN Transition IN form WHERE $1.duration = 8 bars") == []
        assert sonata("MT THEN Transition IN form WHERE $0.duration = 8 bars") == [
            "MT@0|Transition@64"
        ]

    def test_without_a_unit_it_is_seconds(self):
        assert sonata("Transition[duration = 32] IN form") == ["Transition@64"]
        assert sonata("Transition[duration = 8] IN form") == []

    def test_not(self):
        assert sonata("Transition[NOT duration = 9 bars] IN form") == ["Transition@64"]
        assert sonata("Transition[NOT duration = 8 bars] IN form") == []

    def test_a_length_is_asked_of_the_time_map(self):
        got = run(DATA["sonata"], "Transition[duration = 8 bars] IN form")
        assert "tql_length" in got.sql

    @pytest.mark.parametrize(
        "query",
        [
            "*[duration = 8 bars] IN form",
            "*[NOT duration = 8 bars] IN form",
            "* IN form WHERE duration = 8 bars",
            "* IN form WHERE NOT duration = 8 bars",
        ],
    )
    def test_without_a_time_map_no_match_and_a_warning(self, query):
        got = run(EXPOSITION, query)
        assert got.rows == [] and got.warnings == [NO_MAP]


# --------------------------------------------------------------------------- #
# Distances
# --------------------------------------------------------------------------- #
class TestDistances:
    BASE = "ST IN form STARTS AFTER MT IN form WHERE $1.start "

    def test_in_bars(self):
        assert sonata(self.BASE + ">= $2.start + 24 bars") == ["ST@96|MT@0"]
        assert sonata(self.BASE + ">= $2.start + 24.5 bars") == []
        assert sonata(self.BASE + "= $2.start + 24 bars") == ["ST@96|MT@0"]
        assert sonata(self.BASE + "> $2.start + 24 bars") == []
        assert sonata(self.BASE + "<= $2.start + 24 bars") == ["ST@96|MT@0"]
        assert sonata(self.BASE + "!= $2.start + 24 bars") == []
        assert sonata(self.BASE + ">= $2.start + 1 bar") == ["ST@96|MT@0"]

    def test_in_beats(self):
        assert sonata(self.BASE + ">= $2.start + 96 beats") == ["ST@96|MT@0"]
        assert sonata(self.BASE + ">= $2.start + 97 beats") == []
        assert sonata(self.BASE + "= $2.start + 96beats") == ["ST@96|MT@0"]

    def test_a_negative_distance(self):
        assert sonata(self.BASE + "<= $2.start - 1 bar") == []
        assert sonata(self.BASE + ">= $2.start - 1 bar") == ["ST@96|MT@0"]

    def test_in_seconds(self):
        assert sonata(self.BASE + ">= $2.start + 96 s") == ["ST@96|MT@0"]
        assert sonata(self.BASE + ">= $2.start + 97 s") == []
        assert sonata(self.BASE + ">= $2.start + 1:30") == ["ST@96|MT@0"]
        assert sonata(self.BASE + ">= $2.start + 1:40") == []
        assert sonata(self.BASE + ">= $2.start + 90") == ["ST@96|MT@0"]
        assert sonata(self.BASE + ">= $2.start - 1:30") == ["ST@96|MT@0"]

    def test_in_percent_of_the_piece(self):
        assert sonata(self.BASE + ">= $2.start + 60%") == ["ST@96|MT@0"]
        assert sonata(self.BASE + ">= $2.start + 61%") == []
        assert sonata(self.BASE + "<= $2.start + 10%") == []

    def test_not(self):
        base = "ST IN form STARTS AFTER MT IN form WHERE NOT $1.start "
        assert sonata(base + ">= $2.start + 25 bars") == ["ST@96|MT@0"]
        assert sonata(base + ">= $2.start + 24 bars") == []

    def test_end_and_time(self):
        assert sonata("MT THEN Transition IN form WHERE $1.end = $2.start") == [
            "MT@0|Transition@64"
        ]
        assert sonata("MT THEN Transition IN form WHERE $2.end = $1.end + 8 bars") == [
            "MT@0|Transition@64"
        ]
        assert sonata(
            "HC IN cadences BEFORE PAC IN cadences WHERE $2.time >= $1.time + 7 bars"
        ) == ["HC@128|PAC@157", "HC@92|PAC@157"]

    def test_the_documented_examples(self):
        assert sonata(
            "PAC IN cadences DURING ST IN form WHERE $1.start >= $2.start + 4 bars"
        ) == ["PAC@157|ST@96"]

    @pytest.mark.parametrize("distance", ["1 bar", "2 beats"])
    def test_without_a_time_map_a_distance_in_bars_never_matches(self, distance):
        base = "ST IN form STARTS AFTER MT IN form WHERE "
        for cond in (
            f"$1.start >= $2.start + {distance}",
            f"NOT $1.start >= $2.start + {distance}",
        ):
            got = run(EXPOSITION, base + cond)
            assert got.rows == [], cond
            assert got.warnings == [NO_MAP]

    def test_a_percentage_distance_needs_no_map(self):
        got = run(
            EXPOSITION,
            "ST IN form STARTS AFTER MT IN form WHERE $1.start >= $2.start + 10%",
        )
        assert got.rows and got.warnings == []

    def test_a_distance_in_seconds_needs_no_map(self):
        got = run(
            EXPOSITION,
            "ST IN form STARTS AFTER MT IN form WHERE $1.start >= $2.start + 10 s",
        )
        assert got.rows and got.warnings == []

    def test_a_percentage_distance_without_a_length_never_matches(self):
        fix = fixture(
            hierarchy("Form (Z)", [["a", 1, 0, 4], ["b", 1, 4, 8]]), length=None
        )
        base = "a THEN b IN form WHERE "
        for cond in ("$2.start >= $1.start + 1%", "NOT $2.start >= $1.start + 1%"):
            got = run(fix, base + cond)
            assert got.rows == []
            assert got.warnings == ["1 file without a media length could not answer"]


# --------------------------------------------------------------------------- #
# THEN ... WITHIN
# --------------------------------------------------------------------------- #
class TestSequenceWithin:
    def test_without_within_a_hole_breaks_the_run(self):
        assert units(GRID, "v THEN c IN form") == []

    def test_a_hole_of_a_bar_is_crossed_by_a_bar(self):
        assert units(GRID, "v THEN c IN form WITHIN 1 bar") == ["v@0|c@12"]
        assert units(GRID, "v THEN c IN form WITHIN 1.5 bars") == ["v@0|c@12"]

    def test_and_not_by_three_beats(self):
        assert units(GRID, "v THEN c IN form WITHIN 3 beats") == []
        assert units(GRID, "v THEN c IN form WITHIN 0.5 bars") == []
        assert units(GRID, "v THEN c IN form WITHIN 4 beats") == ["v@0|c@12"]

    def test_a_hole_of_two_beats(self):
        assert units(GRID, "c THEN d IN form WITHIN 1 bar") == ["c@12|d@22"]
        assert units(GRID, "c THEN d IN form WITHIN 2 beats") == ["c@12|d@22"]
        assert units(GRID, "c THEN d IN form WITHIN 1 beat") == []

    def test_every_then_of_the_run_crosses(self):
        assert units(GRID, "v THEN c THEN d IN form WITHIN 1 bar") == ["v@0|c@12|d@22"]
        assert units(GRID, "v THEN c THEN d IN form WITHIN 3 beats") == []

    def test_a_repetition_crosses_too(self):
        assert units(GRID, "*+ IN form WITHIN 1 bar") == ["v@0,c@12,d@22"]
        assert units(GRID, "*+ IN form WITHIN 1 beat") == ["c@12", "d@22", "v@0"]

    def test_in_seconds(self):
        assert units(GRID, "v THEN c IN form WITHIN 4 s") == ["v@0|c@12"]
        assert units(GRID, "v THEN c IN form WITHIN 3 s") == []
        assert units(GRID, "v THEN c IN form WITHIN 4000 ms") == ["v@0|c@12"]

    def test_on_markers_it_limits_the_distance_to_the_next(self):
        assert units(GRID, "HC THEN PAC IN cadences") == ["HC@4|PAC@12"]
        assert units(GRID, "HC THEN PAC IN cadences WITHIN 2 bars") == ["HC@4|PAC@12"]
        assert units(GRID, "HC THEN PAC IN cadences WITHIN 1 bar") == []
        assert units(GRID, "HC THEN PAC IN cadences WITHIN 7 beats") == []
        assert units(GRID, "HC THEN PAC IN cadences WITHIN 8 beats") == ["HC@4|PAC@12"]

    def test_within_crosses_holes_never_units(self):
        assert units(GRID, "v THEN d IN form WITHIN 10 bars") == []

    def test_a_whole_lane_form(self):
        assert units(GRID, "CONSISTS OF v THEN c THEN d IN form WITHIN 1 bar") == [
            "v@0|c@12|d@22"
        ]
        assert units(GRID, "CONSISTS OF v THEN c THEN d IN form") == []

    def test_without_a_time_map_nothing_crosses_and_it_warns(self):
        got = run(UNMAPPED, "v THEN c IN form WITHIN 1 bar")
        assert got.rows == [] and got.warnings == [NO_MAP]
        got = run(UNMAPPED, "v THEN c IN form WITHIN 4 s")
        assert got.rows and got.warnings == []

    def test_a_gap_of_a_tenth_of_a_second_is_no_hole_without_a_map(self):
        fix = fixture(hierarchy("Form (Z)", [["a", 1, 0, 4], ["b", 1, 4.05, 8]]))
        assert units(fix, "a THEN b IN form") == ["a@0|b@4.05"]
        assert units(fix, "a THEN b IN form WITHIN 1 bar") == ["a@0|b@4.05"]


# --------------------------------------------------------------------------- #
# Relations' WITHIN
# --------------------------------------------------------------------------- #
class TestRelationWithin:
    def test_before_limits_the_gap_in_bars(self):
        assert units(GRID, "v IN form BEFORE c IN form WITHIN 1 bar") == ["v@0|c@12"]
        assert units(GRID, "v IN form BEFORE c IN form WITHIN 3 beats") == []
        assert units(GRID, "v IN form BEFORE c IN form WITHIN 4 beats") == ["v@0|c@12"]
        assert units(GRID, "v IN form BEFORE c IN form") == ["v@0|c@12"]

    def test_before_counts_the_gap_from_the_end(self):
        # v ends at 8 and d starts at 22: three and a half bars, not 5.5
        assert units(GRID, "v IN form BEFORE d IN form WITHIN 3 bars") == []
        assert units(GRID, "v IN form BEFORE d IN form WITHIN 3.5 bars") == ["v@0|d@22"]

    def test_after_limits_the_gap_in_beats(self):
        assert units(GRID, "c IN form AFTER v IN form WITHIN 4 beats") == ["c@12|v@0"]
        assert units(GRID, "c IN form AFTER v IN form WITHIN 3 beats") == []
        assert units(GRID, "d IN form AFTER c IN form WITHIN 2 beats") == ["d@22|c@12"]
        assert units(GRID, "d IN form AFTER c IN form WITHIN 1 beat") == []

    def test_starts_limit_the_distance_between_the_starts(self):
        assert units(GRID, "c IN form STARTS AFTER v IN form WITHIN 3 bars") == [
            "c@12|v@0"
        ]
        assert units(GRID, "c IN form STARTS AFTER v IN form WITHIN 2 bars") == []
        assert units(GRID, "v IN form STARTS BEFORE c IN form WITHIN 12 beats") == [
            "v@0|c@12"
        ]
        assert units(GRID, "v IN form STARTS BEFORE c IN form WITHIN 11 beats") == []

    def test_in_brackets(self):
        assert units(GRID, "*[BEFORE c IN form WITHIN 1 bar] IN form") == ["v@0"]
        assert units(GRID, "*[BEFORE c IN form WITHIN 3 beats] IN form") == []
        assert units(GRID, "*[NOT BEFORE c IN form WITHIN 3 beats] IN form") == [
            "c@12",
            "d@22",
            "v@0",
        ]

    def test_negated(self):
        assert units(GRID, "v IN form NOT BEFORE c IN form WITHIN 3 beats") == ["v@0"]
        assert units(GRID, "v IN form NOT BEFORE c IN form WITHIN 1 bar") == []

    def test_timing_relations_use_the_length_of_the_beat_or_the_bar(self):
        # c starts at 12; n1 at 12.5 and n2 at 14
        assert units(GRID, "* IN notes SAME START c IN form") == []
        assert units(GRID, "* IN notes SAME START c IN form WITHIN 1 beat") == [
            "n1@12.5|c@12"
        ]
        assert units(GRID, "* IN notes SAME START c IN form WITHIN 0.4 beats") == []
        assert units(GRID, "* IN notes SAME START c IN form WITHIN 1 bar") == [
            "n1@12.5|c@12",
            "n2@14|c@12",
        ]
        assert units(GRID, "*[SAME START c IN form WITHIN 1 beat] IN notes") == [
            "n1@12.5"
        ]

    def test_within_measures_with_the_unit_at_the_left_units_start(self):
        assert units(GRID, "*[SAME START c IN form WITHIN 0.5 bars] IN notes") == [
            "n1@12.5",
            "n2@14",
        ]
        assert units(GRID, "*[SAME START c IN form WITHIN 0.25 bars] IN notes") == [
            "n1@12.5"
        ]

    def test_a_relation_without_in_uses_the_tolerance_too(self):
        assert units(GRID, "c[DURING v WITHIN 1 bar] IN form") == []

    def test_the_sql_asks_the_time_map(self):
        got = run(GRID, "* IN notes SAME START c IN form WITHIN 1 beat")
        assert "tql_unit_seconds" in got.sql
        got = run(GRID, "v IN form BEFORE c IN form WITHIN 1 bar")
        assert "tql_position" in got.sql

    def test_the_examples_of_the_language(self):
        assert sonata("HC IN cadences BEFORE PAC IN cadences WITHIN 8 bars") == [
            "HC@128|PAC@157"
        ]
        assert sonata("HC IN cadences BEFORE PAC IN cadences WITHIN 7 bars") == []

    def test_seconds_still_work(self):
        assert units(GRID, "v IN form BEFORE c IN form WITHIN 4 s") == ["v@0|c@12"]
        assert units(GRID, "v IN form BEFORE c IN form WITHIN 3 s") == []


# --------------------------------------------------------------------------- #
# The bars lane
# --------------------------------------------------------------------------- #
class TestBarsLane:
    @pytest.mark.parametrize("word", ["bars", "bar", "measures", "measure", "BARS"])
    def test_one_unit_per_measure(self, word):
        got = units(GRID, f"* IN {word}")
        assert got == [f"{n}@{(n - 1) * 4}" for n in range(1, 9)]

    def test_a_bar_is_a_read_only_unit_from_its_downbeat_to_the_next(self):
        got = run(GRID, "* IN bars")
        bar = got.matches[1].slots[0][0]
        assert (bar.kind, bar.label, bar.start, bar.end) == ("bar", "2", 4, 8)
        assert got.matches[1].lane == "Beats · bars"
        row = got.rows[1]
        assert (row["label"], row["start"], row["end"], row["bar"]) == ("2", 4, 8, 2)
        assert row["timeline"] == "Beats"

    def test_a_bar_is_found_by_its_number(self):
        assert units(GRID, "3 IN bars") == ["3@8"]
        assert units(GRID, '"3" IN measures') == ["3@8"]
        assert units(GRID, "9 IN bars") == []
        assert len(units(GRID, "NOT 3 IN bars")) == 7
        assert units(GRID, "/^[78]$/ IN bars") == ["7@24", "8@28"]

    def test_the_bars_of_a_repeat_come_in_playing_order(self):
        got = units(DATA["repeat"], "12 IN bars")
        assert got == ["12@44", "12@76"]
        assert len(units(DATA["repeat"], "* IN bars")) == 24

    def test_positions_of_a_bar(self):
        sonata_bars = lambda q: units(DATA["sonata"], q)  # noqa: E731
        assert sonata_bars("*[bar = 25] IN bars") == ["25@96"]
        assert sonata_bars("*[bar.count = 25] IN bars") == ["25@96"]
        assert sonata_bars("*[bar.beat_count = 4 AND bar = 1] IN bars") == ["1@0"]
        assert len(sonata_bars("*[downbeat] IN bars")) == 40
        assert sonata_bars("*[NOT downbeat] IN bars") == []
        assert sonata_bars("*[beat = 1 AND bar = 40] IN bars") == ["40@156"]
        assert units(DATA["repeat"], "*[bar = 12 AND pass = 2] IN bars") == ["12@76"]

    def test_a_sequence_of_bars(self):
        assert units(GRID, "3 THEN 4 IN bars") == ["3@8|4@12"]
        assert units(GRID, "* THEN * IN bars WHERE $1.bar = 7") == ["7@24|8@28"]
        assert units(GRID, "*{7} IN bars") == [
            "1@0,2@4,3@8,4@12,5@16,6@20,7@24",
            "2@4,3@8,4@12,5@16,6@20,7@24,8@28",
        ]

    def test_relations_to_bars(self):
        sonata_bars = lambda q: units(DATA["sonata"], q)  # noqa: E731
        assert sonata_bars(
            "* IN bars CONTAINS PAC IN cadences WHERE $2.start = 157"
        ) == ["40@156|PAC@157"]
        assert sonata_bars("ST IN form SAME START * IN bars") == ["ST@96|25@96"]
        assert sonata_bars("*[SAME START ST IN form] IN bars") == ["25@96"]
        assert sonata_bars("PAC[DURING * IN bars] IN cadences")
        assert sonata_bars("*[NOT CONTAINS * IN cadences] IN bars") != []
        assert sonata_bars("MT IN form CONTAINS 3 IN bars") == ["MT@0|3@8"]

    def test_a_query_without_in_leaves_the_bars_out(self):
        assert units(GRID, "3") == []
        assert units(GRID, '"3"') == []
        got = run(GRID, "*")
        assert all(c.kind != "bar" for m in got.matches for s in m.slots for c in s)
        got = run(GRID, "* WHERE bar = 1")
        assert all(c.kind != "bar" for m in got.matches for s in m.slots for c in s)

    def test_a_file_without_a_time_map_has_no_bars(self):
        got = run(UNMAPPED, "* IN bars")
        assert got.rows == [] and got.warnings == []

    def test_the_bars_of_each_file(self):
        index = fixture_index.build_index(GRID, DATA["sonata"])
        got = tql.run(index, "* IN bars")
        assert len(got.rows) == 8 + 40


# --------------------------------------------------------------------------- #
# The SQL functions
# --------------------------------------------------------------------------- #
class TestSqlFunctions:
    def call(self, index, sql):
        sqlfuncs.register(index.connection(), index)
        return index.connection().execute(sql).fetchone()[0]

    def test_position(self):
        index = index_of(DATA["sonata"])
        assert self.call(index, "SELECT tql_position('f1', 8, 'bar')") == 2.0
        assert self.call(index, "SELECT tql_position('f1', 8, 'beat')") == 8.0
        assert self.call(index, "SELECT tql_position('f1', 10, 'bar')") == 2.5

    def test_length(self):
        index = index_of(DATA["sonata"])
        assert self.call(index, "SELECT tql_length('f1', 0, 64, 'bar')") == 16.0
        assert self.call(index, "SELECT tql_length('f1', 0, 64, 'beat')") == 64.0

    def test_unit_seconds(self):
        index = index_of(DATA["sonata"])
        assert self.call(index, "SELECT tql_unit_seconds('f1', 5, 'bar')") == 4.0
        assert self.call(index, "SELECT tql_unit_seconds('f1', 5, 'beat')") == 1.0

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT tql_position('f1', 5000, 'bar')",
            "SELECT tql_position('f1', NULL, 'bar')",
            "SELECT tql_position('nope', 5, 'bar')",
            "SELECT tql_length('f1', 0, 5000, 'bar')",
            "SELECT tql_length('f1', NULL, 5, 'bar')",
            "SELECT tql_unit_seconds('f1', 5000, 'bar')",
            "SELECT tql_unit_seconds('nope', 5, 'beat')",
        ],
    )
    def test_null_off_the_map(self, sql):
        assert self.call(index_of(DATA["sonata"]), sql) is None

    def test_null_for_a_file_without_a_time_map(self):
        index = index_of(EXPOSITION)
        assert self.call(index, "SELECT tql_position('f1', 5, 'bar')") is None
        assert self.call(index, "SELECT tql_length('f1', 0, 5, 'bar')") is None
        assert self.call(index, "SELECT tql_unit_seconds('f1', 5, 'bar')") is None

    def test_register_without_an_index_still_works(self):
        index = index_of(DATA["sonata"])
        con = index.connection()
        sqlfuncs.register(con)
        sqlfuncs.register(con)
        assert con.execute("SELECT tql_position('f1', 8, 'bar')").fetchone()[0] is None
        assert con.execute("SELECT tql_color('red')").fetchone()[0] == "#ff0000"
        sqlfuncs.register(con, index)
        assert con.execute("SELECT tql_position('f1', 8, 'bar')").fetchone()[0] == 2.0

    def test_a_dropped_index_frees_its_connection(self):
        # The functions on the connection ask the index, which holds the
        # connection, and SQLite's references to them are hidden from the
        # garbage collector.
        class Connection(sqlite3.Connection):  # sqlite3's own takes no weakref
            pass

        built = index_of(DATA["sonata"])
        con = sqlite3.connect(":memory:", factory=Connection)
        built.connection().backup(con)
        index = fixture_index.FixtureIndex(con, built._maps)
        assert self.call(index, "SELECT tql_position('f1', 8, 'bar')") == 2.0
        assert tql.run(index, "*[bar = 1] IN form").matches
        freed = weakref.ref(con)
        del index, con
        gc.collect()
        assert freed() is None


class TestReadOnly:
    def test_run_creates_nothing(self):
        index = index_of(DATA["sonata"])
        con = index.connection()
        before = con.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
        for query in (
            "* IN bars",
            "*[bar = 1] IN form",
            "ST IN form STARTS AFTER MT IN form WHERE $1.start >= $2.start + 4 bars",
            "v THEN c IN form WITHIN 1 bar",
        ):
            tql.run(index, query)
        after = con.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
        assert before == after
        assert not con.in_transaction
