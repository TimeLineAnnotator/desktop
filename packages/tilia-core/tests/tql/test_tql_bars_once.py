"""The bars of every file are read with one statement per run (search, hints
and result rows alike), and a bar's fields without reading every unit of its
file."""

import fixture_index

from tilia_core import tql


def fixture(name, bars):
    return {
        "name": name,
        "length": 4 * bars + 2,
        "timelines": [
            {"name": "Form (X)", "kind": "hierarchy", "units": [["a", 1, 0, 8]]},
            {
                "name": "Beats",
                "kind": "beats",
                "start": 0,
                "every": 1,
                "beats_per_bar": 4,
                "bars": bars,
            },
        ],
    }


def statements(index, query):
    """The result of ``query``, and every statement it ran."""
    ran = []
    index.connection().set_trace_callback(ran.append)
    try:
        got = tql.run(index, query)
    finally:
        index.connection().set_trace_callback(None)
    return got, ran


def test_a_run_reads_the_bars_of_every_file_once():
    index = fixture_index.build_index(
        fixture("one", 3), fixture("two", 5), fixture("three", 4)
    )
    got, ran = statements(index, "*[bar.beat_count = 4] IN bars")
    assert len(got.matches) == 12
    assert len([s for s in ran if "FROM measures" in s]) == 1
    assert not [s for s in ran if "LEFT JOIN positions" in s]  # no unit's fields


def test_the_bars_of_a_sequence_where_are_read_once():
    index = fixture_index.build_index(fixture("one", 3), fixture("two", 5))
    got, ran = statements(
        index, "* THEN * IN bars WHERE $1.bar.beat_count != $2.bar.beat_count"
    )
    assert got.matches == []
    assert len([s for s in ran if "FROM measures" in s]) == 1  # hints included
