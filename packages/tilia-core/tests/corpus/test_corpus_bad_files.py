"""Files that pass the reader and still can't go in the index: one of them
never stops opening, and the others go through (FR-007, FR-060; research R2, R8).
The files are real ``.tla`` content, read through WP3's reader."""

import logging
import os
import sqlite3
import unicodedata
from pathlib import Path

import pytest
import tla_files
from tla_files import Doctored, TlaReader, song, spoiled

from tilia_core import open_corpus, tql
from tilia_core.corpus import scan
from tilia_core.corpus import store as store_module
from tilia_core.corpus.scan import Found

READER = TlaReader()


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(scan, "sleep", lambda seconds: None)


def opened(folder, **kw):
    kw.setdefault("reader", READER)
    kw.setdefault("rescan_before_reads", False)
    return open_corpus(folder, **kw)


def states(corpus):
    return {f.path: f.state for f in corpus.files()}


def components_per_path(corpus):
    with corpus.reading() as r:
        return dict(
            r.connection.execute(
                "SELECT f.path, count(c.id) FROM files f "
                "LEFT JOIN components c ON c.file_id = f.id GROUP BY f.path"
            ).fetchall()
        )


def rows_by_content(corpus):
    """The index's rows, without its keys."""
    with corpus.reading() as r:
        con = r.connection
        return {
            "components": sorted(
                con.execute(
                    "SELECT f.path, c.uuid, c.kind, c.start, c.label FROM components c "
                    "JOIN files f ON f.id = c.file_id"
                ).fetchall()
            ),
            "files": sorted(
                con.execute("SELECT path, state, reason FROM files").fetchall(),
                key=str,
            ),
        }


# Each of these passes tla.read, and can't be stored.
CANT_STORE = {
    "a label with a lone surrogate": (tla_files.surrogate_label, "UnicodeEncodeError"),
    "a level too big for SQLite": (tla_files.huge_level, "OverflowError"),
}


def good_and(folder, bad):
    tla_files.write(folder / "a.tla", song())
    tla_files.write(folder / "bad.tla", bad)
    tla_files.write(folder / "z.tla", song())


# What a reader may give under contracts/reader.md, though WP3's refuses these.
LAX = {
    "a marker without a time": (Doctored("marker", "time", None), "TypeError"),
    "a level that is a list": (Doctored("hierarchy", "level", [1]), "TypeError"),
    "a row id that is a list": (Doctored("range", "row_id", ["r1"]), "TypeError"),
    "a beat with text for a time": (Doctored("beat", "time", "x"), "ValueError"),
}


CANT_BUILD = {
    "a beat without a time, by WP3's reader": (
        TlaReader(),
        tla_files.null_beat,
        "KeyError",
    ),
    **{name: (reader, lambda d: None, err) for name, (reader, err) in LAX.items()},
}


@pytest.mark.parametrize("reader,change,error", CANT_BUILD.values(), ids=CANT_BUILD)
def test_a_file_whose_rows_cant_be_built_is_unreadable(
    tmp_path, reader, change, error, caplog
):
    good_and(tmp_path, spoiled(change))
    with caplog.at_level(logging.ERROR, logger=scan.__name__):
        with opened(tmp_path, reader=reader) as corpus:
            assert states(corpus) == {
                "a.tla": "readable",
                "bad.tla": "unreadable",
                "z.tla": "readable",
            }
            ((path, line, reason),) = corpus.open_report.unreadable
            assert (path, line) == ("bad.tla", None)
            assert reason.startswith(f"can't read: {error}: ")
            assert corpus.file("bad.tla").reason == reason
            assert corpus.open_report.error is None
            per_file = components_per_path(corpus)
            assert per_file["bad.tla"] == 0
            assert per_file["a.tla"] == per_file["z.tla"] > 0
            result = tql.run(corpus, "verse")
            assert len(result.rows) == 2
            assert any("1 file was left out: 1 unreadable" in w for w in result.warnings)
    logged = [r for r in caplog.records if "bad.tla" in r.getMessage()]
    assert logged and logged[0].exc_info  # with its traceback


@pytest.mark.parametrize("change,error", CANT_STORE.values(), ids=CANT_STORE)
def test_a_file_that_cant_be_stored_is_unreadable(tmp_path, change, error, caplog):
    good_and(tmp_path, spoiled(change))
    with caplog.at_level(logging.ERROR, logger=store_module.__name__):
        with opened(tmp_path) as corpus:
            assert states(corpus) == {
                "a.tla": "readable",
                "bad.tla": "unreadable",
                "z.tla": "readable",
            }
            ((path, line, reason),) = corpus.open_report.unreadable
            assert (path, line) == ("bad.tla", None)
            assert reason.startswith(f"can't index: {error}: ")
            assert corpus.file("bad.tla").reason == reason
            assert corpus.file("bad.tla").fingerprint is None
            assert corpus.file("bad.tla").document_id is None
            assert corpus.open_report.error is None
            per_file = components_per_path(corpus)
            assert per_file["bad.tla"] == 0
            assert per_file["a.tla"] == per_file["z.tla"] > 0
            assert corpus.generation == 1
            assert not corpus._store._writer.in_transaction
            result = tql.run(corpus, "verse")
            assert len(result.rows) == 2
            assert any("1 file was left out: 1 unreadable" in w for w in result.warnings)
            assert not any("last change" in w for w in result.warnings)
    assert any(r.exc_info for r in caplog.records)


def test_nothing_half_built_stays_behind(tmp_path):
    (tmp_path / "with").mkdir()
    (tmp_path / "without").mkdir()
    a, z = song(), song()
    bad = song()
    # the hierarchy is fine and comes first: its rows and keys are made before the
    # beat fails
    tla_files.null_beat(bad)
    for folder in ("with", "without"):
        tla_files.write(tmp_path / folder / "a.tla", a)
        tla_files.write(tmp_path / folder / "z.tla", z)
    tla_files.write(tmp_path / "with" / "bad.tla", bad)
    with opened(tmp_path / "with") as corpus, opened(tmp_path / "without") as clean:
        ours, theirs = rows_by_content(corpus), rows_by_content(clean)
        assert ours["components"] == theirs["components"]
        assert [f for f in ours["files"] if f[0] != "bad.tla"] == theirs["files"]
        record = corpus._scanner.records["bad.tla"]
        assert record.keys == (record.key,) and record.time_map is None
        with corpus.reading() as r:
            con = r.connection
            assert con.execute(
                "SELECT count(*) FROM timelines WHERE file_id = ?", (record.key,)
            ).fetchone() == (0,)
            # every key once: the gap the failed build left is never handed out
            keys = [x for (x,) in con.execute("SELECT id FROM components")]
            assert len(keys) == len(set(keys))


def test_a_fresh_build_gives_the_same_keys_with_a_bad_file(tmp_path):
    good_and(tmp_path, spoiled(tla_files.null_beat))
    with opened(tmp_path) as one, opened(tmp_path) as two:
        with one.reading() as r:
            first = r.connection.execute(
                "SELECT id, uuid FROM components ORDER BY id"
            ).fetchall()
        with two.reading() as r:
            assert first == r.connection.execute(
                "SELECT id, uuid FROM components ORDER BY id"
            ).fetchall()


def test_time_map_of_raising_makes_the_file_unreadable(tmp_path):
    good_and(tmp_path, song())

    def time_map_of(document, roles):
        if document.document_id == bad_id:
            raise ValueError("no such bar")
        return None

    bad_id = READER.read(tmp_path / "bad.tla").document_id
    with opened(tmp_path, time_map_of=time_map_of) as corpus:
        assert corpus.file("bad.tla").state == "unreadable"
        assert corpus.file("bad.tla").reason == "can't read: ValueError: no such bar"
        assert corpus.file("a.tla").state == "readable"


def test_a_file_with_a_name_sqlite_cant_store_is_listed_all_the_same(tmp_path):
    name = "bad\ud800.tla"
    tla_files.write(tmp_path / "a.tla", song())
    try:
        tla_files.write(tmp_path / name, song())
    except (OSError, UnicodeError) as err:
        pytest.skip(f"this system can't name a file so: {err}")
    with opened(tmp_path) as corpus:
        rows = {f.path: f for f in corpus.files()}
        assert rows["a.tla"].state == "readable"
        written_out = "bad\\ud800.tla"
        assert rows[written_out].state == "unreadable"
        assert rows[written_out].reason.startswith("can't index: UnicodeEncodeError")
        assert name in corpus._scanner.records


def test_a_reason_with_a_lone_surrogate_is_stored(tmp_path):
    tla_files.write(tmp_path / "a.tla", song())

    class Refuses(TlaReader):
        def read(self, path):
            raise ValueError("no such thing as \ud800")

    with opened(tmp_path, reader=Refuses()) as corpus:
        (row,) = corpus.files()
        assert row.state == "unreadable"
        assert row.reason == "can't read: ValueError: no such thing as \\ud800"
        assert corpus.open_report.error is None


# --------------------------------------------------------------------------- #
# What still stops an opening
# --------------------------------------------------------------------------- #
class RecordingStore(store_module.Store):
    made: list = []

    def __init__(self):
        super().__init__()
        self.made.append(self)


@pytest.fixture
def stores(monkeypatch):
    RecordingStore.made = []
    monkeypatch.setattr("tilia_core.corpus.Store", RecordingStore)
    return RecordingStore.made


def is_closed(store):
    with pytest.raises(RuntimeError, match="closed"):
        with store.reading():
            pass
    return True


def test_opening_closes_the_store_on_any_exception(tmp_path, stores):
    tla_files.write(tmp_path / "a.tla", song())

    class Broken(TlaReader):
        def is_temporary(self, name):
            raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        opened(tmp_path, reader=Broken())
    assert is_closed(stores[0])


def test_ctrl_c_while_reading_stops_the_opening_and_closes_the_store(tmp_path, stores):
    tla_files.write(tmp_path / "a.tla", song())

    class Interrupted(TlaReader):
        def read(self, path):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        opened(tmp_path, reader=Interrupted())
    assert is_closed(stores[0])


def test_ctrl_c_while_the_index_fills_stops_the_opening_and_closes_it(
    tmp_path, stores, monkeypatch
):
    tla_files.write(tmp_path / "a.tla", song())
    tla_files.write(tmp_path / "b.tla", song())
    real = store_module._insert
    calls = []

    def insert(con, rows):
        calls.append(rows)
        if len(calls) == 2:
            raise KeyboardInterrupt
        real(con, rows)

    monkeypatch.setattr(store_module, "_insert", insert)
    with pytest.raises(KeyboardInterrupt):
        opened(tmp_path)
    assert is_closed(stores[0])


# --------------------------------------------------------------------------- #
# A first build the index can't take at all
# --------------------------------------------------------------------------- #
def test_a_failed_first_build_warns_and_doesnt_look_empty(tmp_path, monkeypatch):
    good_and(tmp_path, song())

    def insert(con, rows):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(store_module, "_insert", insert)
    with opened(tmp_path) as corpus:
        assert corpus.open_report.error == "database or disk is full"
        assert corpus.open_report.added == ()
        assert corpus.generation == 0 and corpus.files() == []
        result = tql.run(corpus, "verse")
        assert result.rows == []
        assert any(
            "couldn't take the last change" in w and "disk is full" in w
            for w in result.warnings
        )
