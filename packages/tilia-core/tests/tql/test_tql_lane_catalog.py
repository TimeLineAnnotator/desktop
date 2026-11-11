"""The lanes of every file are read with a few statements per run
(compile.Catalog), and name the same lanes as a file's own statements."""

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import compile as tql_compile
from tilia_core.tql.syntax import Lane

FIXTURES = examples.load()["fixtures"]
NAMES = ["sonata", "pop", "harmony", "repeat", "recipe", "exposition"]
LANES = [
    None,
    Lane("form", False),
    Lane("cadences", False),
    Lane("harmony", False),
    Lane("keys", False),
    Lane("time_map", False),
    Lane("bars", False),
    Lane("beats", False),
    Lane("hierarchies", False),
    Lane("ranges", False),
    Lane("markers", False),
    Lane("chords", False),
    Lane("form*", False),
    Lane("*", False),
    Lane("solo", False),
    Lane("Form (A)", True),
    Lane("nothing", False),
]


@pytest.fixture(scope="module")
def index():
    return fixture_index.build_index(*(FIXTURES[n] for n in NAMES))


def test_the_catalog_names_the_lanes_a_files_statements_name(index):
    con = index.connection()
    catalog = tql_compile.Catalog(con)
    keys = [r[0] for r in con.execute("SELECT id FROM files ORDER BY id")]
    assert len(keys) == len(NAMES)
    seen = 0
    for key in keys:
        for lane in LANES:
            alone = tql_compile.resolve_lanes(con, key, lane)
            assert tql_compile.resolve_lanes(catalog, key, lane) == alone
            seen += len(alone)
        assert tql_compile.bar_lane(catalog, key) == tql_compile.bar_lane(con, key)
        for (tid,) in con.execute("SELECT id FROM timelines WHERE file_id = ?", (key,)):
            assert tql_compile.timeline_lanes(
                catalog, tid
            ) == tql_compile.timeline_lanes(con, tid)
    assert seen > 100


def test_a_run_reads_the_lanes_of_every_file_once(index):
    ran = []
    index.connection().set_trace_callback(ran.append)
    try:
        got = tql.run(index, "nothing THEN * IN form")
    finally:
        index.connection().set_trace_callback(None)
    assert got.matches == []  # the hints, too, look up lanes
    assert [s for s in ran if "FROM hierarchies h JOIN" in s and "level" in s] == [
        s for s in ran if "c.file_id, c.timeline_id, h.level" in s
    ]
    assert len([s for s in ran if "c.file_id, c.timeline_id, h.level" in s]) == 1
    assert len([s for s in ran if "ORDER BY file_id, ordinal" in s]) == 1
    assert not [s for s in ran if "SELECT path FROM files WHERE id" in s]
