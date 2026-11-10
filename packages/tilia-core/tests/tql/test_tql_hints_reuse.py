"""The hints of an empty result take over what the search loaded: no timeline
is read twice in a run, and the SQL the result shows is the search's alone."""

import fixture_index

from tilia_core import tql

FIXTURE = {
    "length": 40,
    "timelines": [
        {
            "name": "Form (X)",
            "kind": "hierarchy",
            "units": [
                ["x", 1, 0, 4],
                ["y", 1, 4, 8],
                ["x", 1, 12, 16],
                ["y", 1, 18, 20],
            ],
        },
        {"name": "Cadences", "kind": "marker", "units": [["PAC", 8], ["HC", 16]]},
    ],
}

LOAD = 'SELECT c.id, c.timeline_id, c.kind, c.label, c.start, c."end"'


def run(query, *fixtures):
    index = fixture_index.build_index(*fixtures)
    ran = []
    index.connection().set_trace_callback(ran.append)
    try:
        got = tql.run(index, query)
    finally:
        index.connection().set_trace_callback(None)
    return got, [s for s in ran if s.startswith(LOAD)]


def test_the_hints_read_no_timeline_the_search_read():
    other = dict(FIXTURE, name="g")
    got, loads = run("x THEN zzz IN form", FIXTURE, other)
    assert got.matches == []
    assert any("zzz occurs nowhere" in w for w in got.warnings)
    assert any("neighbouring pairs" in w for w in got.warnings)
    assert len(loads) == len(set(loads)) == 2  # the form of each file, once


def test_the_hints_add_nothing_to_the_sql_shown():
    with_hints, _ = run("x THEN zzz IN form", FIXTURE)
    with_match, _ = run("x THEN y IN form", FIXTURE)
    assert with_hints.warnings and with_match.matches
    assert with_hints.sql.count("\n\n") == with_match.sql.count("\n\n")
    assert "zzz" in with_hints.sql
    assert "a unit of the query" not in with_hints.sql
