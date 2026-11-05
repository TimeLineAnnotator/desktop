"""``tql.run``, ``tql.sql`` and ``Result.stats`` read inside the index reader's
``reading()``, over readable files only, and say what they left out
(contracts/index-reader.md)."""

import threading
from contextlib import contextmanager

import examples
import fixture_index
import pytest

from tilia_core import tql

FIXTURES = examples.load()["fixtures"]
LEFT_OUT = "2 files were left out: 1 unreadable, 1 unavailable"
OUT_OF_REACH = (
    "the corpus folder can't be reached; these results come from the files as "
    "last read"
)


class Reading:
    """A read that counts what goes through it."""

    def __init__(self, index, generation, available):
        self._index = index
        self._thread = threading.get_ident()
        self.generation = generation
        self.available = available

    @property
    def connection(self):
        assert self._index.depth > 0, "the connection was used after the read"
        self._index.connection_uses += 1
        return self._index.inner.connection()

    def time_map(self, file_id):
        self._index.time_maps_read += 1
        return self._index.inner.time_map(file_id)


class RecordingIndex:
    """An index reader over a fixture index whose ``connection()`` refuses to
    work: every read must go through ``reading()``."""

    def __init__(self, inner, generation=1, available=True):
        self.inner = inner
        self.read_generation = generation  # what a read sees
        self.available = available
        self.depth = 0
        self.reads = 0
        self.connection_uses = 0
        self.time_maps_read = 0

    @contextmanager
    def reading(self):
        self.reads += 1
        self.depth += 1
        try:
            yield Reading(self, self.read_generation, self.available)
        finally:
            self.depth -= 1

    def connection(self):
        raise AssertionError("connection() outside reading()")

    @property
    def generation(self):
        # never the one a result carries: that is its read's
        return self.read_generation + 100

    def time_map(self, file_id):  # what tql's SQL functions ask
        return self.inner.time_map(file_id)


def recording(name="pop", **kw):
    return RecordingIndex(fixture_index.build_index(FIXTURES[name]), **kw)


def add_left_out_files(index):
    """One unreadable and one unavailable row in ``files``, as a corpus keeps
    them: no rows elsewhere, no media length, no time map."""
    con = index.connection()
    con.executemany(
        "INSERT INTO files (id, path, document_id, state, reason) VALUES (?,?,?,?,?)",
        [
            (900, "bad.tla", None, "unreadable", "can't read (line 3): not valid JSON"),
            (901, "gone.tla", "gone", "unavailable", None),
        ],
    )


# --------------------------------------------------------------------------- #
# Reading inside reading()
# --------------------------------------------------------------------------- #
def test_run_reads_inside_one_reading():
    index = recording()
    got = tql.run(index, "verse THEN chorus IN form WHERE $1.bar >= 1")
    assert got.rows
    assert index.reads == 1 and index.depth == 0
    assert index.connection_uses >= 1
    assert index.time_maps_read >= 1  # the file's time map, through the read


def test_the_result_carries_the_generation_of_its_read():
    index = recording(generation=7)
    assert index.generation != 7
    assert tql.run(index, "verse IN form").generation == 7


def test_sql_reads_inside_one_reading():
    index = recording()
    assert tql.sql(index, "SELECT count(*) FROM files").rows == [(1,)]
    assert index.reads == 1 and index.depth == 0


def test_stats_read_inside_one_reading():
    index = recording()
    result = tql.run(index, "verse IN form")
    table = result.stats("counts", "file")
    assert table.rows == [("f1.tla", len(result.matches), 1)]
    assert index.reads == 2 and index.depth == 0


def test_a_read_nested_in_reading_shares_it():
    index = fixture_index.build_index(FIXTURES["pop"])
    with index.reading() as r:
        got = tql.run(index, "verse IN form")
        assert r.connection.execute("SELECT count(*) FROM files").fetchone() == (1,)
    assert got.rows


# --------------------------------------------------------------------------- #
# Statistics of a result whose files changed
# --------------------------------------------------------------------------- #
def test_stats_leave_out_the_units_whose_keys_are_gone_and_warn():
    index = recording(generation=1)
    result = tql.run(index, "* IN form")
    con = index.inner.connection()
    n = len(result.matches)
    # Form (A) changed: its units have new keys (research R4)
    changed = [
        r[0]
        for r in con.execute(
            "SELECT c.id FROM components c JOIN timelines t ON t.id = c.timeline_id "
            "WHERE t.name = 'Form (A)'"
        )
    ]
    con.execute(
        "UPDATE components SET id = id + 10000 WHERE id IN (%s)"
        % ",".join("?" * len(changed)),
        changed,
    )
    index.read_generation = 2
    table = result.stats("counts", "timeline")
    assert dict((r[0], r[1]) for r in table.rows) == {"Form (B)": n - len(changed)}
    gone = len(changed)
    assert result.warnings == [
        f"files changed since this result; {gone} of its units were left out; "
        "run it again"
    ]


def test_stats_of_the_same_generation_keep_every_unit():
    index = recording()
    result = tql.run(index, "* IN form")
    con = index.inner.connection()
    con.execute("UPDATE components SET id = id + 10000")  # same generation
    table = result.stats("counts", "timeline")
    assert sum(r[1] for r in table.rows) == len(result.matches)
    assert result.warnings == []


# --------------------------------------------------------------------------- #
# Files left out, and a folder out of reach
# --------------------------------------------------------------------------- #
def harmony_with_left_out_files(**kw):
    index = recording("harmony", **kw)
    add_left_out_files(index.inner)
    return index


def test_a_result_counts_the_files_left_out():
    got = tql.run(harmony_with_left_out_files(), "* IN harmony")
    assert got.rows
    assert LEFT_OUT in got.warnings


@pytest.mark.parametrize(
    "rows, warning",
    [
        ([(900, "bad.tla", "unreadable")], "1 file was left out: 1 unreadable"),
        (
            [(900, "a.tla", "unavailable"), (901, "b.tla", "unavailable")],
            "2 files were left out: 2 unavailable",
        ),
    ],
)
def test_the_count_names_only_the_states_it_has(rows, warning):
    index = fixture_index.build_index(FIXTURES["harmony"])
    index.connection().executemany(
        "INSERT INTO files (id, path, state) VALUES (?,?,?)", rows
    )
    assert warning in tql.run(index, "* IN harmony").warnings


def test_no_warning_without_files_left_out():
    got = tql.run(fixture_index.build_index(FIXTURES["harmony"]), "* IN harmony")
    assert got.warnings == []


def test_a_result_says_when_the_corpus_folder_cant_be_reached():
    got = tql.run(recording("harmony", available=False), "* IN harmony")
    assert got.rows
    assert got.warnings == [OUT_OF_REACH]


def test_a_query_of_only_a_file_condition_lists_no_file_left_out():
    # the harmony fixture's file has a composer: the two left out have none,
    # and are no match
    index = harmony_with_left_out_files()
    got = tql.run(index, "WHERE file.composer != *")
    assert got.grain == "file"
    assert got.rows == []
    got = tql.run(index, "WHERE file.composer = *")
    assert [r["file"] for r in got.rows] == ["f1"]


def test_a_query_that_needs_media_lengths_or_time_maps_does_not_warn_of_them():
    index = harmony_with_left_out_files()
    for query in ("WHERE start >= 0%", "* IN harmony WHERE start >= 0%"):
        got = tql.run(index, query)
        assert got.rows, query
        assert got.warnings == [LEFT_OUT], query
    # f1 has no time map either: one file, not three, could not answer
    got = tql.run(index, "WHERE bar >= 1")
    assert [w for w in got.warnings if "time map" in w] == [
        "1 file without a time map could not answer"
    ]


def test_statistics_go_over_readable_files_only():
    index = harmony_with_left_out_files()
    result = tql.run(index, "* IN harmony")
    table = result.stats("positions")
    assert table.rows
    assert not any("media length" in w for w in result.warnings)


def test_sql_lists_every_file_row():
    index = harmony_with_left_out_files()
    assert sorted(tql.sql(index, "SELECT path, state FROM files").rows) == [
        ("bad.tla", "unreadable"),
        ("f1.tla", "readable"),
        ("gone.tla", "unavailable"),
    ]


def test_show_sql_prints_the_readable_filter():
    got = tql.run(harmony_with_left_out_files(), "WHERE file.composer = *")
    assert "FROM files WHERE state = 'readable'" in got.sql
