"""Files that pass the reader and still can't go in the index: one of them
never stops opening, and the others go through (FR-007, FR-060; research R2, R8).
The files are real ``.tla`` content, read through WP3's reader."""

import copy
import json
import logging
import os
import sqlite3
import time
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


# --------------------------------------------------------------------------- #
# Subfolders that can't be listed
# --------------------------------------------------------------------------- #
def locking(monkeypatch, *locked):
    real = os.scandir

    def scandir(path="."):
        if Path(path) in locked:
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", scandir)


def test_the_walk_names_the_folders_it_couldnt_list(tmp_path, monkeypatch):
    tla_files.write(tmp_path / "a.tla", song())
    tla_files.write(tmp_path / "sub" / "locked" / "b.tla", song())
    locking(monkeypatch, tmp_path / "sub" / "locked")
    unlisted = []
    found = scan.walk(tmp_path, READER, scan_settings(), unlisted)
    assert [f.path for f in found] == ["a.tla"]
    assert unlisted == ["sub/locked"]


def scan_settings():
    from tilia_core.corpus.settings import NoSettings

    return NoSettings()


def test_results_warn_of_a_folder_that_couldnt_be_listed_at_opening(
    tmp_path, monkeypatch
):
    tla_files.write(tmp_path / "a.tla", song())
    tla_files.write(tmp_path / "locked" / "b.tla", song())
    locking(monkeypatch, tmp_path / "locked")
    with opened(tmp_path) as corpus:
        assert list(states(corpus)) == ["a.tla"]
        result = tql.run(corpus, "verse")
        assert any(
            "can't list the folder locked" in w and "as last read" in w
            for w in result.warnings
        )


# --------------------------------------------------------------------------- #
# Names that differ only in normal form (finding 4)
# --------------------------------------------------------------------------- #
NFC = unicodedata.normalize("NFC", "café.tla")
NFD = unicodedata.normalize("NFD", "café.tla")
OTHER = "cafe\u0301\u0323.tla"  # another form of another name: only for the rule


def twins(folder, first=NFC, second=NFD):
    tla_files.write(folder / first, song("one"))
    tla_files.write(folder / second, song("two two two"))
    if len({unicodedata.normalize("NFC", p.name) for p in folder.iterdir()}) == len(
        list(folder.iterdir())
    ):
        pytest.skip("this file system holds one file per normal form")


def found(root, name):
    return Found(unicodedata.normalize("NFC", name), root / name, 1, 1)


def test_one_of_two_twins_keeps_the_path_by_a_rule_of_the_names_alone(tmp_path):
    a, b = found(tmp_path, NFC), found(tmp_path, NFD)
    for given in ([a, b], [b, a]):
        (kept, other) = scan._one_per_path(given, tmp_path)
        assert kept is a
        assert other.path == NFD and other.native == b.native
        assert other.reason == scan.TWIN_REASON
    # without a name in NFC, the first by code point
    composed_only_partly = unicodedata.normalize("NFD", "éa\u0323.tla")
    other_form = "e\u0301\u1ea1.tla"
    assert unicodedata.normalize("NFC", other_form) == unicodedata.normalize(
        "NFC", composed_only_partly
    )
    c, d = found(tmp_path, composed_only_partly), found(tmp_path, other_form)
    for given in ([c, d], [d, c]):
        (kept, other) = scan._one_per_path(given, tmp_path)
        assert kept is min(c, d, key=lambda f: f.native.name)
        assert kept.path == unicodedata.normalize("NFC", other_form)
        assert other.path == max(composed_only_partly, other_form)


def test_folders_can_be_twins_too(tmp_path):
    a = Found("é/x.tla", tmp_path / "é" / "x.tla", 1, 1)
    b = Found("é/x.tla", tmp_path / "e\u0301" / "x.tla", 1, 1)
    (kept, other) = scan._one_per_path([b, a], tmp_path)
    assert kept is a and other.path == "e\u0301/x.tla"


def test_files_without_twins_come_back_as_they_were(tmp_path):
    given = [found(tmp_path, "a.tla"), found(tmp_path, NFD)]
    assert scan._one_per_path(given, tmp_path) is given


def test_a_twin_is_listed_as_unreadable_at_opening(tmp_path):
    twins(tmp_path)
    with opened(tmp_path) as corpus:
        rows = {f.path: f for f in corpus.files()}
        assert rows[NFC].state == "readable"
        assert rows[NFD].state == "unreadable"
        assert rows[NFD].reason == scan.TWIN_REASON
        assert corpus.open_report.unreadable == ((NFD, None, scan.TWIN_REASON),)
        assert tql.run(corpus, '"one"').rows and not tql.run(corpus, '"two two two"').rows
        result = tql.run(corpus, '"one"')
        assert any("1 file was left out: 1 unreadable" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# The same, in a scan after the opening
# --------------------------------------------------------------------------- #
ANY_BAD = {
    "a beat without a time": (tla_files.null_beat, "can't read: KeyError"),
    **{name: (c, f"can't index: {e}") for name, (c, e) in CANT_STORE.items()},
}


def long_ago(*paths):
    """Date ``paths`` long past, so a scan reads them again only if they change."""
    then = time.time() - 3600
    for path in paths:
        os.utime(path, (then, then))


def said_last_change(result):
    return any("couldn't take the last change" in w for w in result.warnings)


@pytest.mark.parametrize("change,reason", ANY_BAD.values(), ids=ANY_BAD)
def test_a_bad_file_that_appears_stops_no_other_change(tmp_path, change, reason):
    a = song()
    tla_files.write(tmp_path / "a.tla", a)
    tla_files.write(tmp_path / "z.tla", song())
    with opened(tmp_path) as corpus:
        tla_files.unit(a, "Marker")["label"] = "PAC"
        tla_files.write(tmp_path / "a.tla", a)
        tla_files.write(tmp_path / "bad.tla", spoiled(change))
        report = corpus.scan()
        assert report.error is None
        assert report.added == ("bad.tla",)
        assert report.changed == ("a.tla",)
        ((path, line, why),) = report.unreadable
        assert (path, line) == ("bad.tla", None) and why.startswith(reason)
        assert corpus.file("bad.tla").state == "unreadable"
        assert not corpus._store._writer.in_transaction
        result = tql.run(corpus, "PAC")
        assert len(result.rows) == 1
        assert not said_last_change(result)


@pytest.mark.parametrize("change,reason", ANY_BAD.values(), ids=ANY_BAD)
def test_a_file_edited_badly_loses_its_rows_and_comes_back(tmp_path, change, reason):
    data = song()
    good = json.dumps(data, indent=2)
    tla_files.write(tmp_path / "a.tla", data)
    with opened(tmp_path) as corpus:
        assert components_per_path(corpus)["a.tla"] > 0
        change(data)
        tla_files.write(tmp_path / "a.tla", data)
        report = corpus.scan()
        assert report.error is None and report.changed == ()
        ((path, _, why),) = report.unreadable
        assert path == "a.tla" and why.startswith(reason)
        assert components_per_path(corpus)["a.tla"] == 0
        assert corpus.file("a.tla").state == "unreadable"
        (tmp_path / "a.tla").write_text(good, encoding="utf-8")
        report = corpus.scan()
        assert report.changed == ("a.tla",) and report.unreadable == ()
        assert corpus.file("a.tla").state == "readable"
        assert components_per_path(corpus)["a.tla"] > 0


@pytest.mark.parametrize("change,reason", ANY_BAD.values(), ids=ANY_BAD)
def test_a_bad_file_on_record_is_left_alone_by_later_scans(tmp_path, change, reason):
    tla_files.write(tmp_path / "a.tla", song())
    tla_files.write(tmp_path / "bad.tla", spoiled(change))
    long_ago(tmp_path / "a.tla", tmp_path / "bad.tla")
    with opened(tmp_path) as corpus:
        generation = corpus.generation
        for _ in range(3):
            report = corpus.scan()
            assert not report
            assert report.generation_after == generation


@pytest.mark.parametrize("change,reason", ANY_BAD.values(), ids=ANY_BAD)
def test_a_move_into_a_bad_file_is_a_move_and_unreadable(tmp_path, change, reason):
    data = song()
    tla_files.write(tmp_path / "a.tla", data)
    with opened(tmp_path) as corpus:
        key = corpus.file("a.tla").id
        (tmp_path / "a.tla").unlink()
        change(data)
        tla_files.write(tmp_path / "b.tla", data)
        report = corpus.scan()
        assert report.moved == (("a.tla", "b.tla"),)
        assert report.unreadable[0][0] == "b.tla"
        assert report.unreadable[0][2].startswith(reason)
        assert states(corpus) == {"b.tla": "unreadable"}
        assert corpus.file("b.tla").id == key


# --------------------------------------------------------------------------- #
# A change the index can't take at all, in a scan
# --------------------------------------------------------------------------- #
def disk_full(con, rows):
    raise sqlite3.OperationalError("database or disk is full")


def test_a_change_that_fails_warns_until_one_is_applied(tmp_path, monkeypatch):
    a = song()
    tla_files.write(tmp_path / "a.tla", a)
    with opened(tmp_path) as corpus:
        tla_files.unit(a, "Marker")["label"] = "PAC"
        tla_files.write(tmp_path / "a.tla", a)
        generation = corpus.generation
        with monkeypatch.context() as m:
            m.setattr(store_module, "_insert", disk_full)
            report = corpus.scan()
            assert report.error == "database or disk is full"
            assert corpus.generation == generation
            result = tql.run(corpus, "HC")
            assert len(result.rows) == 1  # as last indexed
            assert said_last_change(result)
        report = corpus.scan()
        assert report.error is None and report.changed == ("a.tla",)
        result = tql.run(corpus, "PAC")
        assert len(result.rows) == 1
        assert not said_last_change(result)


def test_the_warning_goes_when_the_failed_change_was_undone(tmp_path, monkeypatch):
    path = tla_files.write(tmp_path / "a.tla", song())
    long_ago(path)
    content, date = path.read_bytes(), path.stat().st_mtime_ns
    with opened(tmp_path) as corpus:
        with monkeypatch.context() as m:
            m.setattr(store_module, "_insert", disk_full)
            tla_files.write(path, song("edited"))
            assert corpus.scan().error is not None
            assert said_last_change(tql.run(corpus, "verse"))
        path.write_bytes(content)
        os.utime(path, ns=(date, date))
        report = corpus.scan()
        assert not report and report.error is None
        assert not said_last_change(tql.run(corpus, "verse"))


def test_ctrl_c_during_a_scan_goes_through_and_leaves_reads_working(
    tmp_path, monkeypatch
):
    a = song()
    tla_files.write(tmp_path / "a.tla", a)
    with opened(tmp_path) as corpus:
        generation = corpus.generation
        tla_files.unit(a, "Marker")["label"] = "PAC"
        tla_files.write(tmp_path / "a.tla", a)

        def interrupted(con, rows):
            raise KeyboardInterrupt

        with monkeypatch.context() as m:
            m.setattr(store_module, "_insert", interrupted)
            with pytest.raises(KeyboardInterrupt):
                corpus.scan()
        assert not corpus._store._writer.in_transaction
        assert corpus.generation == generation
        result = tql.run(corpus, "HC")
        assert len(result.rows) == 1 and not said_last_change(result)
        assert corpus.scan().changed == ("a.tla",)
        assert len(tql.run(corpus, "PAC").rows) == 1


# --------------------------------------------------------------------------- #
# A subfolder that can't be listed, in a scan
# --------------------------------------------------------------------------- #
def said_cant_list(result, folder):
    return any(f"can't list the folder {folder}" in w for w in result.warnings)


def test_files_under_a_folder_that_cant_be_listed_keep_their_last_state(
    tmp_path, monkeypatch
):
    tla_files.write(tmp_path / "a.tla", song())
    tla_files.write(tmp_path / "locked" / "b.tla", song())
    tla_files.write(tmp_path / "locked" / "deep" / "c.tla", song())
    with opened(tmp_path) as corpus:
        generation = corpus.generation
        rows = rows_by_content(corpus)
        with monkeypatch.context() as m:
            locking(m, tmp_path / "locked")
            report = corpus.scan()
            assert not report and report.error is None
            assert corpus.generation == generation
            assert rows_by_content(corpus) == rows
            assert set(states(corpus).values()) == {"readable"}
            result = tql.run(corpus, "verse")
            assert len(result.rows) == 3
            assert said_cant_list(result, "locked")
            assert not any("left out" in w for w in result.warnings)
        report = corpus.scan()
        assert not report and corpus.generation == generation
        assert not said_cant_list(tql.run(corpus, "verse"), "locked")


def test_other_changes_go_through_while_a_folder_cant_be_listed(tmp_path, monkeypatch):
    a = song()
    tla_files.write(tmp_path / "a.tla", a)
    tla_files.write(tmp_path / "gone.tla", song())
    tla_files.write(tmp_path / "locked" / "b.tla", song())
    with opened(tmp_path) as corpus:
        locking(monkeypatch, tmp_path / "locked")
        tla_files.unit(a, "Marker")["label"] = "PAC"
        tla_files.write(tmp_path / "a.tla", a)
        tla_files.write(tmp_path / "new.tla", song())
        (tmp_path / "gone.tla").unlink()
        report = corpus.scan()
        assert report.changed == ("a.tla",)
        assert report.added == ("new.tla",)
        assert report.unavailable == ("gone.tla",)
        assert corpus.file("locked/b.tla").state == "readable"


def test_what_went_behind_a_locked_folder_shows_once_it_can_be_listed(
    tmp_path, monkeypatch
):
    tla_files.write(tmp_path / "locked" / "b.tla", song())
    tla_files.write(tmp_path / "locked" / "c.tla", song())
    with opened(tmp_path) as corpus:
        with monkeypatch.context() as m:
            locking(m, tmp_path / "locked")
            (tmp_path / "locked" / "b.tla").unlink()
            tla_files.write(tmp_path / "locked" / "c.tla", song("edited"))
            assert not corpus.scan()
            assert corpus.file("locked/b.tla").state == "readable"
        report = corpus.scan()
        assert report.unavailable == ("locked/b.tla",)
        assert len(tql.run(corpus, "edited").rows) == 1


def test_a_move_out_of_a_locked_folder_is_a_copy_until_it_can_be_listed(
    tmp_path, monkeypatch
):
    data = song()
    tla_files.write(tmp_path / "locked" / "b.tla", data)
    with opened(tmp_path) as corpus:
        with monkeypatch.context() as m:
            locking(m, tmp_path / "locked")
            (tmp_path / "locked" / "b.tla").unlink()
            tla_files.write(tmp_path / "out.tla", data)
            report = corpus.scan()
            assert report.added == ("out.tla",) and report.moved == ()
            assert report.shared_ids == (("locked/b.tla", "out.tla"),)
        report = corpus.scan()
        assert report.moved == (("locked/b.tla", "out.tla"),)
        assert list(states(corpus)) == ["out.tla"]


def test_only_what_lies_under_the_folder_is_kept(tmp_path, monkeypatch):
    tla_files.write(tmp_path / "sub" / "b.tla", song())
    tla_files.write(tmp_path / "subway" / "c.tla", song())
    with opened(tmp_path) as corpus:
        locking(monkeypatch, tmp_path / "sub")
        (tmp_path / "subway" / "c.tla").unlink()
        assert corpus.scan().unavailable == ("subway/c.tla",)
        assert corpus.file("sub/b.tla").state == "readable"


def test_a_file_the_walk_cant_look_at_is_kept_too(tmp_path, monkeypatch):
    tla_files.write(tmp_path / "a.tla", song())
    with opened(tmp_path) as corpus:
        scanner = corpus._scanner
        real = scan.walk

        def walk(root, reader, settings, unlisted=None):
            unlisted.append("a.tla")
            return [f for f in real(root, reader, settings) if f.path != "a.tla"]

        monkeypatch.setattr(scan, "walk", walk)
        report = scanner.scan()
        assert not report
        assert corpus.file("a.tla").state == "readable"
        assert said_cant_list(tql.run(corpus, "verse"), "a.tla")


def test_a_folder_that_can_be_listed_and_is_empty_has_lost_its_files(tmp_path):
    tla_files.write(tmp_path / "sub" / "b.tla", song())
    with opened(tmp_path) as corpus:
        (tmp_path / "sub" / "b.tla").unlink()
        assert corpus.scan().unavailable == ("sub/b.tla",)


# --------------------------------------------------------------------------- #
# A deleted file whose id lives on (Felipe's decision 3 on the review)
# --------------------------------------------------------------------------- #
def copies(folder, other_content):
    """``piece1`` and ``piece2``, with one document id; their content differs if
    ``other_content``."""
    data = song()
    tla_files.write(folder / "piece1.tla", data)
    other = copy.deepcopy(data)
    if other_content:
        tla_files.unit(other, "Marker")["label"] = "edited"
    tla_files.write(folder / "piece2.tla", other)
    return other


def test_a_deleted_file_whose_id_lives_on_in_other_content_is_unavailable(tmp_path):
    copies(tmp_path, other_content=True)
    with opened(tmp_path) as corpus:
        kept = components_per_path(corpus)["piece2.tla"]
        (tmp_path / "piece1.tla").unlink()
        report = corpus.scan()
        assert report.moved == ()
        assert report.unavailable == ("piece1.tla",)
        assert states(corpus) == {"piece1.tla": "unavailable", "piece2.tla": "readable"}
        assert components_per_path(corpus) == {"piece1.tla": 0, "piece2.tla": kept}
        result = tql.run(corpus, "edited")
        assert len(result.rows) == 1
        assert any("1 file was left out: 1 unavailable" in w for w in result.warnings)
        assert not corpus.scan()


def test_it_comes_back_when_it_does(tmp_path):
    copies(tmp_path, other_content=True)
    content = (tmp_path / "piece1.tla").read_bytes()
    with opened(tmp_path) as corpus:
        (tmp_path / "piece1.tla").unlink()
        corpus.scan()
        (tmp_path / "piece1.tla").write_bytes(content)
        report = corpus.scan()
        assert report.back == ("piece1.tla",)
        assert corpus.file("piece1.tla").state == "readable"


def test_a_deleted_file_with_an_exact_copy_has_moved_onto_it(tmp_path):
    copies(tmp_path, other_content=False)
    with opened(tmp_path) as corpus:
        (tmp_path / "piece1.tla").unlink()
        report = corpus.scan()
        assert report.moved == (("piece1.tla", "piece2.tla"),)
        assert report.unavailable == ()
        assert list(states(corpus)) == ["piece2.tla"]


def test_a_copy_edited_as_the_original_goes_is_no_copy_any_more(tmp_path):
    other = copies(tmp_path, other_content=False)
    with opened(tmp_path) as corpus:
        (tmp_path / "piece1.tla").unlink()
        tla_files.unit(other, "Marker")["label"] = "edited"
        tla_files.write(tmp_path / "piece2.tla", other)
        report = corpus.scan()
        assert report.moved == ()
        assert report.unavailable == ("piece1.tla",)
        assert report.changed == ("piece2.tla",)


def test_an_edit_and_a_rename_into_a_new_path_stays_a_move(tmp_path):
    data = song()
    tla_files.write(tmp_path / "a.tla", data)
    with opened(tmp_path) as corpus:
        key = corpus.file("a.tla").id
        (tmp_path / "a.tla").unlink()
        tla_files.unit(data, "Marker")["label"] = "edited"
        tla_files.write(tmp_path / "b.tla", data)
        report = corpus.scan()
        assert report.moved == (("a.tla", "b.tla"),)
        assert report.unavailable == ()
        assert list(states(corpus)) == ["b.tla"]
        assert corpus.file("b.tla").id == key


def test_twins_dont_flip_at_every_scan(tmp_path):
    twins(tmp_path)
    with opened(tmp_path) as corpus:
        generation = corpus.generation
        rows = rows_by_content(corpus)
        for _ in range(4):
            report = corpus.scan()
            assert not report
            assert report.generation_after == generation
            assert rows_by_content(corpus) == rows


def test_a_twin_takes_the_path_when_the_other_goes(tmp_path):
    twins(tmp_path)
    with opened(tmp_path) as corpus:
        (tmp_path / NFC).unlink()
        report = corpus.scan()
        assert report.changed == (NFC,)
        assert report.unavailable == (NFD,)
        assert corpus.file(NFC).state == "readable"
        assert len(tql.run(corpus, '"two two two"').rows) == 1
        generation = corpus.generation
        assert not corpus.scan()
        assert corpus.generation == generation


# --------------------------------------------------------------------------- #
# Rereading with the corpus folder gone (FR-021; finding 5)
# --------------------------------------------------------------------------- #
def test_a_reread_with_the_folder_gone_changes_nothing(tmp_path):
    folder = tmp_path / "corpus"
    tla_files.write(folder / "a.tla", song())
    tla_files.write(folder / "b.tla", song())
    with opened(folder) as corpus:
        generation = corpus.generation
        rows = rows_by_content(corpus)
        folder.rename(tmp_path / "elsewhere")
        report = corpus.reread("a.tla")
        assert not report
        assert report.generation_after == generation == corpus.generation
        assert rows_by_content(corpus) == rows
        assert not corpus.available
        assert corpus.file("a.tla").state == "readable"
        result = tql.run(corpus, "verse")
        assert len(result.rows) == 2
        assert any("reach" in w or "unavailable" in w for w in result.warnings)
        (tmp_path / "elsewhere").rename(folder)
        report = corpus.scan()
        assert not report and corpus.generation == generation
        assert corpus.available


def test_a_reread_that_fails_otherwise_with_the_folder_gone_changes_nothing(
    tmp_path, monkeypatch
):
    tla_files.write(tmp_path / "a.tla", song())
    with opened(tmp_path) as corpus:
        generation = corpus.generation
        native = tmp_path / "a.tla"

        def no_share(path, *args, **kwargs):
            raise OSError(64, "The specified network name is no longer available")

        monkeypatch.setattr(os, "stat", no_share)
        report = corpus._scanner.reread("a.tla", native)
        monkeypatch.undo()
        assert not report and corpus.generation == generation
        assert not corpus.available
        assert corpus.file("a.tla").state == "readable"


def test_a_reread_of_a_deleted_file_in_a_folder_still_there_marks_it(tmp_path):
    tla_files.write(tmp_path / "a.tla", song())
    with opened(tmp_path) as corpus:
        (tmp_path / "a.tla").unlink()
        assert corpus.reread("a.tla").unavailable == ("a.tla",)
        assert corpus.available


def test_a_reread_that_fails_otherwise_in_a_folder_still_there_is_unreadable(
    tmp_path, monkeypatch
):
    tla_files.write(tmp_path / "a.tla", song())
    with opened(tmp_path) as corpus:
        native = tmp_path / "a.tla"
        real = os.stat

        def locked(path, *args, **kwargs):
            if Path(path) == native:
                raise PermissionError(13, "Permission denied", str(path))
            return real(path, *args, **kwargs)

        monkeypatch.setattr(os, "stat", locked)
        monkeypatch.setattr(READER, "read", _refuse, raising=False)
        report = corpus._scanner.reread("a.tla", native)
        monkeypatch.undo()
        assert report.unreadable[0][0] == "a.tla"
        assert corpus.available


def _refuse(path):
    raise PermissionError(13, "Permission denied", str(path))


def test_rereading_a_twin_by_its_name_leaves_the_rows_alone(tmp_path):
    twins(tmp_path)
    with opened(tmp_path) as corpus:
        generation = corpus.generation
        rows = rows_by_content(corpus)
        report = corpus.reread(NFD)
        assert report.changed == () and corpus.generation == generation
        assert rows_by_content(corpus) == rows
        assert not corpus.scan()


@pytest.mark.parametrize("change,reason", ANY_BAD.values(), ids=ANY_BAD)
def test_a_read_that_rescans_survives_a_bad_file(tmp_path, change, reason):
    tla_files.write(tmp_path / "a.tla", song())
    with opened(tmp_path, rescan_before_reads=True) as corpus:
        tla_files.write(tmp_path / "bad.tla", spoiled(change))
        corpus._scanner.last_scan = None  # the rescan is due
        result = tql.run(corpus, "verse")
        assert len(result.rows) == 1
        assert any("1 file was left out: 1 unreadable" in w for w in result.warnings)
        assert corpus.file("bad.tla").reason.startswith(reason)


def test_a_reread_that_goes_through_doesnt_clear_a_failed_scans_warning(
    tmp_path, monkeypatch
):
    a = song()
    tla_files.write(tmp_path / "a.tla", a)
    tla_files.write(tmp_path / "b.tla", song())
    with opened(tmp_path) as corpus:
        tla_files.unit(a, "Marker")["label"] = "PAC"
        tla_files.write(tmp_path / "a.tla", a)
        with monkeypatch.context() as m:
            m.setattr(store_module, "_insert", disk_full)
            assert corpus.scan().error is not None
        tla_files.write(tmp_path / "b.tla", song("edited"))
        assert corpus.reread("b.tla").error is None
        # a.tla is still as last indexed
        assert said_last_change(tql.run(corpus, "HC"))
        assert corpus.scan().changed == ("a.tla",)
        assert not said_last_change(tql.run(corpus, "HC"))


def test_written_with_the_folder_gone_changes_nothing_and_blames_no_writer(
    tmp_path, caplog
):
    folder = tmp_path / "corpus"
    tla_files.write(folder / "a.tla", song())
    with opened(folder) as corpus:
        generation = corpus.generation
        rows = rows_by_content(corpus)
        folder.rename(tmp_path / "elsewhere")
        with caplog.at_level(logging.WARNING, logger=scan.__name__):
            report = corpus.written("a.tla", "not what the record says")
        assert not report and corpus.generation == generation
        assert rows_by_content(corpus) == rows
        assert not corpus.available
        assert not any("writer wrote" in r.getMessage() for r in caplog.records)
