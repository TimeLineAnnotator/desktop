"""What TQL 0.2 changes in how a query runs: ``$n`` times read a unit's piece
of the lane (R1), each comparison on ``$n`` picks its own unit (O5), and
``WITHIN`` after an order relation widens "inside" past the unit's end."""

import examples
import fixture_index

from tilia_core import tql

FIXTURES = examples.load()["fixtures"]

# level 1 has a gap from 10 to 20 s, where the lane shows a piece of A
PIECE = {
    "name": "piece",
    "length": 40,
    "timelines": [
        {
            "name": "Form",
            "kind": "hierarchy",
            "units": [["a", 1, 0, 10], ["c", 1, 20, 40], ["A", 2, 0, 40]],
        }
    ],
}
# x starts inside A and ends 1.5 s after it
SPILL = {
    "name": "spill",
    "length": 40,
    "timelines": [
        {
            "name": "Form",
            "kind": "hierarchy",
            "units": [["A", 1, 0, 20], ["B", 1, 20, 40]],
        },
        {
            "name": "Layers",
            "kind": "range",
            "rows": ["solo"],
            "units": [["solo", "x", 15, 21.5], ["solo", "y", 0, 5]],
        },
    ],
}


def starts(fixture, query):
    got = tql.run(fixture_index.build_index(fixture), query)
    return [r["$1.start"] for r in got.rows]


class TestPieces:
    def test_a_step_reads_its_piece_of_the_unit(self):
        assert starts(PIECE, 'a THEN A IN "Form" WHERE $2.duration = 10') == [0]
        assert starts(PIECE, 'a THEN A IN "Form" WHERE $2.start = 10') == [0]
        assert starts(PIECE, 'a THEN A THEN c IN "Form" WHERE $2.end = 20') == [0]

    def test_not_the_whole_unit(self):
        assert starts(PIECE, 'a THEN A IN "Form" WHERE $2.duration = 40') == []
        assert starts(PIECE, 'a THEN A IN "Form" WHERE $2.start = 0') == []

    def test_a_unit_found_whole_reads_its_own_times(self):
        assert starts(PIECE, 'A IN "Form" WHERE duration = 40') == [0]

    def test_the_row_shows_the_piece(self):
        got = tql.run(fixture_index.build_index(PIECE), 'a THEN A IN "Form"')
        row = got.rows[0]
        assert (row["$2.start"], row["$2.end"]) == (10, 20)


class TestEachComparisonPicksItsUnit:
    def test_two_comparisons_two_units(self):
        # verse{2} holds verses at 8 and 24 s: each comparison finds its own
        query = "verse{2} THEN chorus IN form WHERE $1.start = 8 AND $1.start = 24"
        assert starts(FIXTURES["pop"], query) == [8]

    def test_a_comparison_no_unit_meets(self):
        query = "verse{2} THEN chorus IN form WHERE $1.start = 99"
        assert starts(FIXTURES["pop"], query) == []


class TestWithinInside:
    def test_contains_needs_the_unit_inside(self):
        assert starts(SPILL, 'A IN "Form" CONTAINS x IN Layers') == []

    def test_within_widens_inside_past_the_end(self):
        assert starts(SPILL, 'A IN "Form" CONTAINS x IN Layers WITHIN 2 s') == [0]
        assert starts(SPILL, 'A IN "Form" ENDS WITH x IN Layers WITHIN 2 s') == [0]

    def test_by_no_more_than_within(self):
        assert starts(SPILL, 'A IN "Form" CONTAINS x IN Layers WITHIN 1 s') == []
