"""The scan: keeping the index true to the files (User Story 2; research R7-R9;
data-model.md, "File states" and "The scan report")."""

import dataclasses
import logging
import os
import threading
import time
from pathlib import Path

import corpus_docs
import pytest
from json_reader import JsonDocumentReader

from tilia_core import open_corpus, tql
from tilia_core.corpus import scan, store

PATIENCE = 10  # seconds a test waits for another thread
HOUR_NS = 3600 * 10**9


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(scan, "sleep", lambda seconds: None)


class CountingReader(JsonDocumentReader):
    """The stand-in, counting its reads by relative name, and raising
    ``errors[name]`` for a name in it."""

    def __init__(self):
        self.reads = []
        self.errors = {}
        self.hold = {}  # name -> (inside, go_on) events

    def read(self, path):
        name = Path(path).name
        self.reads.append(name)
        if name in self.hold:
            inside, go_on = self.hold[name]
            inside.set()
            assert go_on.wait(PATIENCE)
        if name in self.errors:
            raise self.errors[name]
        return super().read(path)


def song(name, labels=("verse", "chorus"), **kw):
    units = [[label, 1, 10 * i, 10 * (i + 1)] for i, label in enumerate(labels)]
    return corpus_docs.document(
        corpus_docs.hierarchy(units, fields={"role": "form"}), document_id=name, **kw
    )


def write(folder, relpath, document=None, **kw):
    name = Path(relpath).stem
    return corpus_docs.write_doc(folder / relpath, document or song(name), **kw)


def settle(*paths):
    """Date files back by an hour, so that a scan has no reason to read them."""
    for path in paths:
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns - HOUR_NS))


def settle_all(folder):
    settle(*[p for p in folder.rglob("*.tla") if p.is_file()])


def opened(folder, reader=None):
    return open_corpus(folder, reader=reader or JsonDocumentReader())


def labels(corpus):
    with corpus.reading() as r:
        return r.connection.execute(
            "SELECT f.path, c.label FROM components c JOIN files f ON f.id = c.file_id "
            "ORDER BY f.path, c.start"
        ).fetchall()


def states(corpus):
    return {f.path: f.state for f in corpus.files()}


def unit_keys(corpus, path):
    with corpus.reading() as r:
        return r.connection.execute(
            "SELECT c.id FROM components c JOIN files f ON f.id = c.file_id "
            "WHERE f.path = ? ORDER BY c.id",
            (path,),
        ).fetchall()


@pytest.fixture
def folder(tmp_path):
    for name in ("a", "b", "c"):
        write(tmp_path, f"{name}.tla")
    settle_all(tmp_path)
    return tmp_path


# --------------------------------------------------------------------------- #
# User Story 2
# --------------------------------------------------------------------------- #
def test_scenario_1_a_file_changed_by_another_program(folder):
    with opened(folder) as corpus:
        write(folder, "b.tla", song("b", ["intro", "outro"]))
        report = corpus.scan()
        assert report.changed == ("b.tla",)
        assert not (report.added or report.moved or report.unavailable)
        assert (report.generation_before, report.generation_after) == (1, 2)
        assert corpus.generation == 2
        assert ("b.tla", "intro") in labels(corpus)
        assert ("b.tla", "verse") not in labels(corpus)


def test_scenario_2_a_touched_file_is_read_and_nothing_is_reported(folder):
    reader = CountingReader()
    with opened(folder, reader) as corpus:
        reader.reads.clear()
        os.utime(folder / "b.tla")
        report = corpus.scan()
        assert reader.reads == ["b.tla"]
        assert not report and report.generation_before == report.generation_after
        assert corpus.generation == 1


def test_scenario_3_an_old_version_restored_with_its_older_date(folder):
    path = folder / "a.tla"
    old_bytes, old_info = path.read_bytes(), path.stat()
    write(folder, "a.tla", song("a", ["VERSE", "CHORUS"]))  # later, the same size
    assert path.stat().st_size == old_info.st_size
    later = old_info.st_mtime_ns + HOUR_NS // 2
    os.utime(path, ns=(later, later))  # settled: only its date can tell
    with opened(folder) as corpus:
        path.write_bytes(old_bytes)
        os.utime(path, ns=(old_info.st_atime_ns, old_info.st_mtime_ns))  # older
        report = corpus.scan()
        assert report.changed == ("a.tla",)
        assert ("a.tla", "verse") in labels(corpus)


def test_scenario_4_a_rename_and_a_move_keep_their_records(folder):
    with opened(folder) as corpus:
        keys = {p: corpus.file(p).id for p in ("a.tla", "b.tla")}
        units = {p: unit_keys(corpus, p) for p in ("a.tla", "b.tla")}
        os.rename(folder / "a.tla", folder / "renamed.tla")
        (folder / "songs").mkdir()
        os.rename(folder / "b.tla", folder / "songs" / "b.tla")
        report = corpus.scan()
        assert report.moved == (("a.tla", "renamed.tla"), ("b.tla", "songs/b.tla"))
        assert not (report.unavailable or report.added or report.changed)
        assert states(corpus) == {
            "c.tla": "readable",
            "renamed.tla": "readable",
            "songs/b.tla": "readable",
        }
        assert corpus.file("renamed.tla").id == keys["a.tla"]
        assert corpus.file("songs/b.tla").id == keys["b.tla"]
        # the same content keeps its units' keys
        assert unit_keys(corpus, "renamed.tla") == units["a.tla"]
        assert unit_keys(corpus, "songs/b.tla") == units["b.tla"]
        assert corpus.generation == 2


def test_scenario_5_a_deleted_file_is_unavailable_and_read_again_when_back(
    folder, tmp_path_factory
):
    outside = tmp_path_factory.mktemp("outside")
    with opened(folder) as corpus:
        os.remove(folder / "a.tla")
        os.rename(folder / "b.tla", outside / "b.tla")  # out of the corpus
        report = corpus.scan()
        assert report.unavailable == ("a.tla", "b.tla")
        assert not report.moved
        assert {p for p, _ in labels(corpus)} == {"c.tla"}
        a = corpus.file("a.tla")
        assert (a.state, a.document_id, a.fields, a.timeline_kinds) == (
            "unavailable",
            "a",
            {},
            {},
        )
        result = tql.run(corpus, "verse IN form")
        assert {m.slots[0][0].label for m in result.matches} == {"verse"}
        assert "2 files were left out: 2 unavailable" in result.warnings
        # back again
        os.rename(outside / "b.tla", folder / "b.tla")
        report = corpus.scan()
        assert report.back == ("b.tla",) and not report.added
        assert states(corpus)["b.tla"] == "readable"
        assert ("b.tla", "verse") in labels(corpus)
        assert corpus.generation == 3


def test_scenario_6_line_endings_changed_report_nothing(folder):
    with opened(folder) as corpus:
        write(folder, "a.tla", crlf=True)
        report = corpus.scan()
        assert not report and corpus.generation == 1


def test_scenario_7_a_file_being_written_is_tried_again_then_read_later(folder):
    reader = CountingReader()
    with opened(folder, reader) as corpus:
        reader.reads.clear()
        whole = (folder / "c.tla").read_bytes()
        (folder / "c.tla").write_bytes(whole[: len(whole) // 2])  # half written
        report = corpus.scan()
        assert reader.reads == ["c.tla", "c.tla"]  # one retry
        assert [u[0] for u in report.unreadable] == ["c.tla"]
        assert states(corpus)["c.tla"] == "unreadable"
        (folder / "c.tla").write_bytes(whole)
        report = corpus.scan()
        assert report.changed == ("c.tla",) and not report.unreadable
        assert states(corpus)["c.tla"] == "readable"


def test_scenario_8_nothing_changed_reads_no_file(folder):
    reader = CountingReader()
    with opened(folder, reader) as corpus:
        reader.reads.clear()
        report = corpus.scan()
        assert reader.reads == []
        assert not report and report.generation_before == report.generation_after == 1


def test_scenario_10_the_corpus_folder_out_of_reach_changes_nothing(tmp_path, caplog):
    folder = tmp_path / "corpus"
    for name in ("a", "b"):
        write(folder, f"{name}.tla")
    settle_all(folder)
    with opened(folder) as corpus:
        before = labels(corpus)
        os.rename(folder, tmp_path / "away")
        with caplog.at_level(logging.WARNING, logger=scan.__name__):
            report = corpus.scan()
        assert not report and report.generation_after == 1
        assert corpus.available is False and corpus.generation == 1
        assert labels(corpus) == before
        assert states(corpus) == {"a.tla": "readable", "b.tla": "readable"}
        result = tql.run(corpus, "verse IN form")
        assert len(result.matches) == 2
        assert any("can't be reached" in w for w in result.warnings)
        assert any("can't be reached" in m for m in caplog.messages)
        # back, with a change made meanwhile
        os.rename(tmp_path / "away", folder)
        write(folder, "b.tla", song("b", ["intro"]))
        report = corpus.scan()
        assert corpus.available is True
        assert report.changed == ("b.tla",) and corpus.generation == 2


# --------------------------------------------------------------------------- #
# Fingerprints, format versions and the racy rule
# --------------------------------------------------------------------------- #
class CurrentVersionReader(JsonDocumentReader):
    """Canonical bytes in one format version, as WP3's writer writes the
    current one whatever version a file was read in; the stand-in's own keep
    the document's."""

    def canonical_bytes(self, document):
        return super().canonical_bytes(
            dataclasses.replace(document, format_version="current")
        )


def test_a_re_save_that_only_changes_the_format_version(folder):
    with opened(folder, CurrentVersionReader()) as corpus:
        fingerprint = corpus.file("a.tla").fingerprint
        keys = unit_keys(corpus, "a.tla")
        write(folder, "a.tla", song("a", format_version="1.1"))
        report = corpus.scan()
        assert report.changed == ("a.tla",)
        assert corpus.file("a.tla").format_version == "1.1"
        assert corpus.file("a.tla").fingerprint == fingerprint
        assert corpus.generation == 2
        assert unit_keys(corpus, "a.tla") == keys  # the same rows


def test_the_racy_rule_finds_an_edit_that_kept_size_and_date(tmp_path):
    write(tmp_path, "a.tla", song("a", ["xx"]))  # fresh: racy once read
    with opened(tmp_path) as corpus:
        rec = corpus._scanner.records["a.tla"]
        assert scan.is_racy(rec)
        write(tmp_path, "a.tla", song("a", ["yy"]))  # the same size
        info = (tmp_path / "a.tla").stat()
        os.utime(tmp_path / "a.tla", ns=(info.st_atime_ns, rec.mtime_ns))
        assert (info.st_size, rec.mtime_ns) == (rec.size, rec.mtime_ns)
        report = corpus.scan()
        assert report.changed == ("a.tla",)
        assert labels(corpus) == [("a.tla", "yy")]


def test_a_racy_file_read_again_inside_the_window_stays_racy(tmp_path, monkeypatch):
    path = write(tmp_path, "a.tla")
    mtime = path.stat().st_mtime_ns
    clock = iter(
        [mtime + 10**9, mtime + 15 * 10**8, mtime - 10**9, mtime + 3 * 10**9]
    )
    monkeypatch.setattr(scan, "now_ns", lambda: next(clock))
    reader = CountingReader()
    with opened(tmp_path, reader) as corpus:
        for _ in range(3):  # read 1 s after, 1.5 s after, 1 s before its date
            assert scan.is_racy(corpus._scanner.records["a.tla"])
            corpus.scan()
        assert reader.reads == ["a.tla"] * 4
        # the read 3 s after its date settles it
        assert not scan.is_racy(corpus._scanner.records["a.tla"])
        corpus.scan()
        assert reader.reads == ["a.tla"] * 4
        assert corpus.generation == 1


# --------------------------------------------------------------------------- #
# Copies and moves
# --------------------------------------------------------------------------- #
def test_a_copy_is_added_and_listed_as_sharing_a_document_id(folder):
    with opened(folder) as corpus:
        (folder / "old").mkdir()
        (folder / "old" / "a.tla").write_bytes((folder / "a.tla").read_bytes())
        report = corpus.scan()
        assert report.added == ("old/a.tla",) and not report.moved
        assert report.shared_ids == (("a.tla", "old/a.tla"),)
        assert corpus.file("a.tla").id != corpus.file("old/a.tla").id
        # reported when the group is new, not at every scan
        os.utime(folder / "c.tla")
        assert not corpus.scan().shared_ids


def test_a_copy_then_the_original_deleted_with_a_scan_between_is_a_move(folder):
    with opened(folder) as corpus:
        (folder / "old").mkdir()
        (folder / "old" / "a.tla").write_bytes((folder / "a.tla").read_bytes())
        corpus.scan()
        copy_key = corpus.file("old/a.tla").id
        os.remove(folder / "a.tla")
        report = corpus.scan()
        assert report.moved == (("a.tla", "old/a.tla"),)
        assert not report.unavailable and not report.added
        assert corpus.file("a.tla") is None  # its record and rows removed
        assert corpus.file("old/a.tla").id == copy_key
        assert [p for p, _ in labels(corpus)].count("old/a.tla") == 2
        assert {p for p, _ in labels(corpus)} == {"b.tla", "c.tla", "old/a.tla"}


def test_of_several_new_files_with_the_id_the_same_content_wins_then_the_first_path(
    folder,
):
    with opened(folder) as corpus:
        a_bytes = (folder / "a.tla").read_bytes()
        os.remove(folder / "a.tla")
        write(folder, "m.tla", song("a", ["edited"]))
        (folder / "z.tla").write_bytes(a_bytes)  # the same content
        report = corpus.scan()
        assert report.moved == (("a.tla", "z.tla"),)
        assert report.added == ("m.tla",)
        assert report.shared_ids == (("m.tla", "z.tla"),)
    for name in ("m.tla", "z.tla"):
        os.remove(folder / name)
    write(folder, "a.tla")
    settle_all(folder)
    with opened(folder) as corpus:
        os.remove(folder / "a.tla")
        write(folder, "y.tla", song("a", ["one"]))
        write(folder, "x.tla", song("a", ["two"]))
        report = corpus.scan()
        assert report.moved == (("a.tla", "x.tla"),)  # the first by path
        assert report.changed == ("x.tla",)  # and its content changed
        assert report.added == ("y.tla",)


def test_an_unavailable_file_found_at_another_path_is_back_as_a_move(folder):
    with opened(folder) as corpus:
        a_bytes = (folder / "a.tla").read_bytes()
        os.remove(folder / "a.tla")
        corpus.scan()
        key = corpus.file("a.tla").id
        (folder / "elsewhere.tla").write_bytes(a_bytes)
        report = corpus.scan()
        assert report.moved == (("a.tla", "elsewhere.tla"),)
        assert report.back == ("elsewhere.tla",) and not report.added
        assert corpus.file("a.tla") is None
        assert corpus.file("elsewhere.tla").id == key


# --------------------------------------------------------------------------- #
# Unreadable files
# --------------------------------------------------------------------------- #
def broken(path, text="oops"):
    path.write_text("{\n" + text + "\n}", encoding="utf-8")


def test_an_unreadable_file_that_becomes_readable_is_changed(folder):
    broken(folder / "d.tla")
    with opened(folder) as corpus:
        assert states(corpus)["d.tla"] == "unreadable"
        write(folder, "d.tla")
        report = corpus.scan()
        assert report.changed == ("d.tla",) and not report.unreadable
        assert states(corpus)["d.tla"] == "readable"
        assert corpus.generation == 2


def test_an_unreadable_file_is_reported_again_only_when_its_reason_changes(folder):
    broken(folder / "d.tla")
    with opened(folder) as corpus:
        broken(folder / "d.tla", "still broken")  # the same reason, another size
        report = corpus.scan()
        assert not report and corpus.generation == 1
        (folder / "d.tla").write_text("\n\n{oops}", encoding="utf-8")  # line 3
        report = corpus.scan()
        ((path, line, reason),) = report.unreadable
        assert (path, line) == ("d.tla", 3)
        assert corpus.file("d.tla").reason == reason
        assert corpus.generation == 2


def test_a_readable_file_that_becomes_unreadable_loses_its_rows(folder):
    with opened(folder) as corpus:
        broken(folder / "a.tla")
        report = corpus.scan()
        assert [u[0] for u in report.unreadable] == ["a.tla"]
        assert not report.changed
        assert {p for p, _ in labels(corpus)} == {"b.tla", "c.tla"}
        a = corpus.file("a.tla")
        assert (a.state, a.document_id, a.fingerprint) == ("unreadable", None, None)


def test_a_file_that_couldnt_be_opened_is_read_once_it_can_be(folder):
    reader = CountingReader()
    reader.errors["a.tla"] = PermissionError(13, "Permission denied")
    with opened(folder, reader) as corpus:
        assert corpus._scanner.records["a.tla"].os_error
        info = (folder / "a.tla").stat()
        reader.reads.clear()
        assert not corpus.scan()  # still locked: tried again, not reported again
        assert reader.reads == ["a.tla", "a.tla"]
        del reader.errors["a.tla"]
        report = corpus.scan()  # its size and date never changed
        assert (folder / "a.tla").stat().st_mtime_ns == info.st_mtime_ns
        assert report.changed == ("a.tla",)
        assert states(corpus)["a.tla"] == "readable"
        assert not corpus._scanner.records["a.tla"].os_error


def test_an_unreadable_file_going_missing_is_unavailable(folder):
    broken(folder / "d.tla")
    with opened(folder) as corpus:
        os.remove(folder / "d.tla")
        report = corpus.scan()
        assert report.unavailable == ("d.tla",)
        d = corpus.file("d.tla")
        assert (d.state, d.document_id, d.reason) == ("unavailable", None, None)


# --------------------------------------------------------------------------- #
# A change that can't be applied, turns and threads
# --------------------------------------------------------------------------- #
def test_a_change_that_cant_be_applied_leaves_the_records_for_the_next_scan(
    folder, monkeypatch
):
    monkeypatch.setattr(store, "PATIENCE", 0.2)
    with opened(folder) as corpus:
        write(folder, "b.tla", song("b", ["intro"]))
        os.remove(folder / "c.tla")
        records = dict(corpus._scanner.records)
        with corpus.reading() as r:
            cursor = r.connection.execute("SELECT * FROM components")
            cursor.fetchone()  # left open: it holds a table lock
        report = corpus.scan()
        assert report.error is not None and "locked" in report.error
        assert not report and report.generation_after == 1
        assert corpus._scanner.records == records
        cursor.close()
        assert ("b.tla", "verse") in labels(corpus)
        report = corpus.scan()  # the same changes, applied now
        assert report.error is None
        assert (report.changed, report.unavailable) == (("b.tla",), ("c.tla",))
        assert corpus.generation == 2


def test_a_scan_inside_a_read_raises(folder):
    with opened(folder) as corpus:
        with corpus.reading():
            with pytest.raises(RuntimeError, match="inside a read"):
                corpus.scan()


def wait_until(condition, what):
    deadline = time.monotonic() + PATIENCE
    while not condition():
        assert time.monotonic() < deadline, what
        time.sleep(0.005)


def test_concurrent_scans_share_one_scan(folder):
    reader = CountingReader()
    with opened(folder, reader) as corpus:
        write(folder, "a.tla", song("a", ["intro"]))
        inside, go_on = threading.Event(), threading.Event()
        reader.hold["a.tla"] = (inside, go_on)
        reader.reads.clear()
        reports = {}
        first = threading.Thread(target=lambda: reports.update(a=corpus.scan()))
        first.start()
        assert inside.wait(PATIENCE)  # the first scan is reading a.tla
        second = threading.Thread(target=lambda: reports.update(b=corpus.scan()))
        second.start()
        try:
            wait_until(
                lambda: corpus._scanner._job is not None
                and corpus._scanner._job.waiters == 1,
                "the second call never waited for the running scan",
            )
        finally:
            go_on.set()
            first.join(PATIENCE)
            second.join(PATIENCE)
        assert not first.is_alive() and not second.is_alive()
        assert reports["a"] is reports["b"]
        assert reports["a"].changed == ("a.tla",)
        assert reader.reads == ["a.tla"]
        assert corpus.generation == 2


def test_a_scan_waits_for_the_change_mutex(folder):
    with opened(folder) as corpus:
        write(folder, "a.tla", song("a", ["intro"]))
        turn = corpus._scanner.turn
        done = threading.Event()
        with turn:
            t = threading.Thread(target=lambda: (corpus.scan(), done.set()))
            t.start()
            wait_until(lambda: turn.waiting == 1 or done.is_set(), "no wait")
            assert not done.is_set()
        t.join(PATIENCE)
        assert done.is_set() and corpus.generation == 2


def test_scanning_writes_nothing_in_the_folder(folder):
    broken(folder / "d.tla")
    with opened(folder) as corpus:
        write(folder, "a.tla", song("a", ["intro"]))
        os.remove(folder / "b.tla")
        before = {p: p.read_bytes() for p in folder.rglob("*")}
        corpus.scan()
        corpus.scan()
        assert {p: p.read_bytes() for p in folder.rglob("*")} == before


def test_the_report_is_frozen_and_true_when_anything_changed():
    empty = scan.ScanReport((), (), (), (), (), (), (), 1, 1)
    assert not empty
    for field in (
        "added",
        "changed",
        "moved",
        "unavailable",
        "back",
        "unreadable",
        "shared_ids",
    ):
        assert dataclasses.replace(empty, **{field: ("x",)})
    with pytest.raises(dataclasses.FrozenInstanceError):
        empty.added = ("x",)
