"""User Story 4's scenarios 2 and 3: copies of one file keep their own keys and
rows, and a user's own SQL reads the tables and changes nothing (FR-042,
FR-043)."""

import os

import corpus_docs
import pytest
from json_reader import JsonDocumentReader

from tilia_core import open_corpus, tql
from tilia_core.corpus import scan

HOUR_NS = 3600 * 10**9


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(scan, "sleep", lambda seconds: None)


def song():
    units = [["A", 2, 0, 20], ["verse", 1, 0, 10], ["chorus", 1, 10, 20]]
    return corpus_docs.document(
        corpus_docs.hierarchy(units, fields={"role": "form"}), document_id="song"
    )


def opened(folder):
    return open_corpus(folder, reader=JsonDocumentReader(), rescan_before_reads=False)


def one(corpus, sql, *args):
    with corpus.reading() as r:
        return r.connection.execute(sql, args).fetchall()


@pytest.fixture
def copies(tmp_path):
    """``b.tla``, opened, then its copy ``a.tla`` found by a scan: keys in the
    order the files were found, paths in the other order."""
    original = corpus_docs.write_doc(tmp_path / "b.tla", song())
    info = original.stat()
    os.utime(original, ns=(info.st_atime_ns, info.st_mtime_ns - HOUR_NS))
    corpus = opened(tmp_path)
    (tmp_path / "a.tla").write_bytes(original.read_bytes())
    report = corpus.scan()
    yield corpus, report
    corpus.close()


def test_scenario_2_copies_have_their_own_keys_and_rows(copies):
    corpus, report = copies
    assert report.shared_ids == (("a.tla", "b.tla"),)
    a, b = corpus.file("a.tla"), corpus.file("b.tla")
    assert a.document_id == b.document_id == "song"
    assert b.id < a.id  # b was found first
    units = {
        path: one(
            corpus,
            "SELECT c.id, c.uuid FROM components c JOIN files f "
            "ON f.id = c.file_id WHERE f.path = ? ORDER BY c.uuid",
            path,
        )
        for path in ("a.tla", "b.tla")
    }
    assert [u for _, u in units["a.tla"]] == [u for _, u in units["b.tla"]]
    assert not {k for k, _ in units["a.tla"]} & {k for k, _ in units["b.tla"]}


def test_scenario_2_no_join_mixes_the_copies_units(copies):
    corpus, _ = copies
    assert one(
        corpus,
        "SELECT count(*) FROM components c JOIN timelines t ON t.id = c.timeline_id "
        "WHERE t.file_id != c.file_id",
    ) == [(0,)]
    assert one(
        corpus,
        "SELECT count(*) FROM hierarchies h JOIN components c ON c.id = h.component_id "
        "JOIN components p ON p.id = h.parent_id WHERE p.file_id != c.file_id",
    ) == [(0,)]
    assert one(
        corpus, "SELECT count(*) FROM hierarchies WHERE parent_id IS NOT NULL"
    ) == [(4,)]
    result = tql.run(corpus, "verse THEN chorus IN form")
    assert len(result.matches) == 2
    for m in result.matches:
        (verse,), (chorus,) = m.slots
        assert verse.file_id == chorus.file_id


def test_scenario_2_results_are_ordered_by_path_and_statistics_count_copies_apart(
    copies,
):
    corpus, _ = copies
    a, b = corpus.file("a.tla"), corpus.file("b.tla")
    result = tql.run(corpus, "verse IN form")
    assert [m.slots[0][0].file_id for m in result.matches] == [a.id, b.id]
    table = result.stats("counts", by="file")
    assert table.columns[:2] == ["file", "matches"]
    assert [row[:2] for row in table.rows] == [("a.tla", 1), ("b.tla", 1)]


def test_scenario_2_the_first_builds_report_lists_copies(tmp_path):
    for name in ("a.tla", "sub/a.tla", "c.tla"):
        corpus_docs.write_doc(tmp_path / name, song())
    with opened(tmp_path) as corpus:
        assert corpus.open_report.shared_ids == (("a.tla", "c.tla", "sub/a.tla"),)


def test_scenario_3_a_users_select_returns_the_files_rows_and_changes_nothing(copies):
    corpus, _ = copies

    def everything():
        with corpus.reading() as r:
            con = r.connection
            tables = [
                t[0]
                for t in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            return {t: con.execute(f"SELECT * FROM {t}").fetchall() for t in tables}

    before, generation = everything(), corpus.generation
    table = tql.sql(
        corpus,
        "SELECT f.path, t.name, c.label, c.start FROM components c "
        "JOIN timelines t ON t.id = c.timeline_id JOIN files f ON f.id = c.file_id "
        "WHERE c.kind = 'hierarchy' ORDER BY f.path, c.start, c.label",
    )
    assert table.columns == ["path", "name", "label", "start"]
    assert table.rows == [
        (path, "Form (A)", label, start)
        for path in ("a.tla", "b.tla")
        for label, start in (("A", 0.0), ("verse", 0.0), ("chorus", 10.0))
    ]
    with pytest.raises(tql.TQLError):
        tql.sql(corpus, "DELETE FROM components")
    assert everything() == before and corpus.generation == generation
