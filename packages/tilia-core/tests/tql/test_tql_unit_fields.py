"""A unit's stored fields read with its timeline's units are those read with
its whole file's, and a query on one timeline loads no other's."""

import examples
import fixture_index

from tilia_core import tql
from tilia_core.tql import values
from tilia_core.tql.showsql import Recorder

FIXTURES = examples.load()["fixtures"]


def test_a_timelines_units_have_the_fields_the_files_give_them():
    index = fixture_index.build_index(*FIXTURES.values())
    con = index.connection()
    seen = 0
    for (file_id,) in con.execute("SELECT id FROM files"):
        whole = values.Facts(Recorder(con), file_id)
        alone = values.Facts(Recorder(con), file_id)
        for comp_id, timeline_id in con.execute(
            "SELECT id, timeline_id FROM components WHERE file_id = ?", (file_id,)
        ):
            assert alone.unit(comp_id, timeline_id) == whole.unit(comp_id)
            seen += 1
    assert seen > 100


def test_a_where_on_the_keys_reads_no_chords_fields():
    index = fixture_index.build_index(FIXTURES["sonata"])
    ran = []
    index.connection().set_trace_callback(ran.append)
    try:
        got = tql.run(index, "* IN keys WHERE mode = major")
    finally:
        index.connection().set_trace_callback(None)
    assert got.matches
    loads = [s for s in ran if "LEFT JOIN positions p" in s]
    assert loads and all("c.timeline_id = " in s for s in loads)
