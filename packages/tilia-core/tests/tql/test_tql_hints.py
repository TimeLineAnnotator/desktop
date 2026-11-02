"""An empty result says why, where the engine can know (tql.md §10, R4): the
messages beside the rows, never instead of them."""

import examples
import fixture_index

from tilia_core import tql

FIXTURES = examples.load()["fixtures"]

# phrases with a second's gap between each two: no THEN joins them
GAPPY = {
    "name": "gappy",
    "length": 40,
    "timelines": [
        {
            "name": "Phrases",
            "kind": "hierarchy",
            "units": [
                ["a", 1, 0, 9],
                ["b", 1, 10, 19],
                ["c", 1, 20, 29],
                ["d", 1, 30, 40],
            ],
        }
    ],
}
HELD_BY_NONE = (
    "is a field of chords and keys, and the lanes searched (IN form) hold none "
    "- try IN harmony"
)
GAPS = "3 of 3 neighbouring pairs are further apart than 0.1 s; try THEN … WITHIN"


def run(query, *fixtures):
    return tql.run(fixture_index.build_index(*fixtures), query)


class TestGaps:
    def test_a_run_over_lanes_with_gaps(self):
        got = run('CONSISTS OF *+ IN "Phrases"', GAPPY)
        assert got.rows == []
        assert got.warnings == [GAPS]

    def test_a_sequence_over_lanes_with_gaps(self):
        assert run('a THEN b IN "Phrases"', GAPPY).warnings == [GAPS]

    def test_not_with_within(self):
        got = run('a THEN c IN "Phrases" WITHIN 2 s', GAPPY)
        assert got.rows == [] and got.warnings == []

    def test_not_when_most_neighbours_touch(self):
        got = run("verse THEN bridge IN form", FIXTURES["pop"])
        assert got.rows == [] and got.warnings == []

    def test_not_for_one_unit(self):
        got = run('x IN "Phrases"', GAPPY)
        assert not any("neighbouring" in w for w in got.warnings)

    def test_not_when_something_matched(self):
        got = run('*+ IN "Phrases"', GAPPY)
        assert got.rows and got.warnings == []


class TestHarmonyFields:
    def test_in_where(self):
        got = run("* IN form WHERE roman = I", FIXTURES["harmony"])
        assert got.warnings == [f"roman {HELD_BY_NONE}"]

    def test_in_brackets(self):
        got = run("*[tonic = C] IN form", FIXTURES["harmony"])
        assert got.warnings == [f"tonic {HELD_BY_NONE}"]

    def test_not_on_chords(self):
        got = run("* IN harmony WHERE roman = vii", FIXTURES["harmony"])
        assert got.rows == [] and got.warnings == []


class TestNowhere:
    def test_a_label_no_unit_has(self):
        got = run("verse THEN bogus IN form", FIXTURES["pop"])
        assert got.warnings == ["bogus occurs nowhere in the lanes searched (IN form)"]

    def test_each_label_once(self):
        got = run("bogus THEN bogus IN form", FIXTURES["pop"])
        assert got.warnings == ["bogus occurs nowhere in the lanes searched (IN form)"]

    def test_a_quoted_lane(self):
        got = run('x IN "Phrases"', GAPPY)
        assert got.warnings == ['x occurs nowhere in the lanes searched (IN "Phrases")']

    def test_not_for_a_label_that_occurs(self):
        # both occur; no verse is followed by an outro
        got = run("verse THEN outro IN form", FIXTURES["pop"])
        assert got.rows == [] and got.warnings == []

    def test_not_for_a_negated_label(self):
        got = run("NOT bogus THEN bogus IN form", FIXTURES["pop"])
        assert got.warnings == ["bogus occurs nowhere in the lanes searched (IN form)"]

    def test_the_sql_shown_is_the_search_alone(self):
        empty = run("bogus IN form", FIXTURES["pop"])
        found = run("verse IN form", FIXTURES["pop"])
        assert len(empty.sql_blocks) == len(found.sql_blocks)
