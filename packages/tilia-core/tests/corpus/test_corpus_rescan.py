"""Rereading one file (FR-020), and rescans before reads (FR-024; research R10).
The scan's clock is replaced, so no test sleeps for it."""

import os
import threading
import time
from pathlib import Path

import corpus_docs
import pytest
from json_reader import JsonDocumentReader

from tilia_core import open_corpus, tql
from tilia_core.corpus import scan

PATIENCE = 10  # seconds a test waits for another thread
HOUR_NS = 3600 * 10**9


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(scan, "sleep", lambda seconds: None)


@pytest.fixture
def clock(monkeypatch):
    """The scan's clock, at 1000 s until a test moves it."""
    now = [1000.0]
    monkeypatch.setattr(scan, "clock", lambda: now[0])
    return now


class CountingReader(JsonDocumentReader):
    """The stand-in, counting its reads by file name, and holding a read of a
    name in ``hold`` until its event is set."""

    def __init__(self):
        self.reads = []
        self.hold = {}  # name -> (inside, go_on)

    def read(self, path):
        name = Path(path).name
        self.reads.append(name)
        if name in self.hold:
            inside, go_on = self.hold[name]
            inside.set()
            assert go_on.wait(PATIENCE)
        return super().read(path)


def song(name, labels=("verse", "chorus")):
    units = [[label, 1, 10 * i, 10 * (i + 1)] for i, label in enumerate(labels)]
    return corpus_docs.document(
        corpus_docs.hierarchy(units, fields={"role": "form"}), document_id=name
    )


def write(folder, relpath, document=None, **kw):
    return corpus_docs.write_doc(
        folder / relpath, document or song(Path(relpath).stem), **kw
    )


def settle(path):
    info = path.stat()
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns - HOUR_NS))


@pytest.fixture
def folder(tmp_path):
    for name in ("a", "b"):
        settle(write(tmp_path, f"{name}.tla"))
    return tmp_path


def labels(corpus):
    with corpus.reading() as r:
        return r.connection.execute(
            "SELECT f.path, c.label FROM components c JOIN files f ON f.id = c.file_id "
            "ORDER BY f.path, c.start"
        ).fetchall()


def wait_until(condition, what):
    deadline = time.monotonic() + PATIENCE
    while not condition():
        assert time.monotonic() < deadline, what
        time.sleep(0.005)


# --------------------------------------------------------------------------- #
# Rescans before reads
# --------------------------------------------------------------------------- #
def test_scenario_9_a_query_after_2_s_sees_a_file_changed_in_tilia(folder, clock):
    with open_corpus(folder, reader=JsonDocumentReader()) as corpus:
        write(folder, "a.tla", song("a", ["intro", "chorus"]))  # TiLiA saved it
        clock[0] += 2.5
        result = tql.run(corpus, "intro IN form")
        assert [m.slots[0][0].label for m in result.matches] == ["intro"]
        assert result.generation == corpus.generation == 2


def test_no_rescan_within_2_s(folder, clock):
    reader = CountingReader()
    with open_corpus(folder, reader=reader) as corpus:
        write(folder, "a.tla", song("a", ["intro"]))
        reader.reads.clear()
        clock[0] += 1.9
        assert tql.run(corpus, "intro IN form").matches == []
        assert reader.reads == []
        clock[0] += 0.2  # 2.1 s since the last scan
        assert len(tql.run(corpus, "intro IN form").matches) == 1
        assert reader.reads == ["a.tla"]


def test_the_rescan_dates_from_the_last_scan(folder, clock):
    reader = CountingReader()
    with open_corpus(folder, reader=reader) as corpus:
        clock[0] += 5
        corpus.scan()  # a scan of its own
        write(folder, "a.tla", song("a", ["intro"]))
        reader.reads.clear()
        clock[0] += 1
        corpus.files()
        assert reader.reads == []


def test_two_threads_share_one_rescan(folder, clock):
    reader = CountingReader()
    with open_corpus(folder, reader=reader) as corpus:
        write(folder, "a.tla", song("a", ["intro"]))
        inside, go_on = threading.Event(), threading.Event()
        reader.hold["a.tla"] = (inside, go_on)
        reader.reads.clear()
        clock[0] += 3
        seen = {}

        def query(name):
            seen[name] = tql.run(corpus, "intro IN form").generation

        first = threading.Thread(target=query, args=("first",), daemon=True)
        first.start()
        assert inside.wait(PATIENCE)  # its rescan is reading a.tla
        second = threading.Thread(target=query, args=("second",), daemon=True)
        second.start()
        try:
            wait_until(
                lambda: corpus._scanner._job is not None
                and corpus._scanner._job.waiters == 1,
                "the second read never waited for the first one's rescan",
            )
        finally:
            go_on.set()
            first.join(PATIENCE)
            second.join(PATIENCE)
        assert not first.is_alive() and not second.is_alive()
        assert seen == {"first": 2, "second": 2}
        assert reader.reads == ["a.tla"]


def test_a_nested_read_does_not_rescan(folder, clock):
    reader = CountingReader()
    with open_corpus(folder, reader=reader) as corpus:
        reader.reads.clear()
        with corpus.reading() as outer:
            write(folder, "a.tla", song("a", ["intro"]))
            clock[0] += 3
            with corpus.reading() as inner:  # a scan here would raise
                assert inner.generation == outer.generation == 1
            assert tql.run(corpus, "intro IN form").matches == []
        assert reader.reads == []


def test_a_read_on_a_thread_holding_the_change_mutex_does_not_rescan(folder, clock):
    reader = CountingReader()
    with open_corpus(folder, reader=reader) as corpus:
        reader.reads.clear()
        with corpus._scanner.turn:  # as writing() will hold it
            write(folder, "a.tla", song("a", ["intro"]))
            clock[0] += 3
            assert tql.run(corpus, "intro IN form").matches == []
            assert reader.reads == []
        assert len(tql.run(corpus, "intro IN form").matches) == 1  # now it does


def test_rescans_before_reads_are_off_when_asked(folder, clock):
    reader = CountingReader()
    with open_corpus(folder, reader=reader, rescan_before_reads=False) as corpus:
        write(folder, "a.tla", song("a", ["intro"]))
        reader.reads.clear()
        clock[0] += 60
        assert tql.run(corpus, "intro IN form").matches == []
        corpus.files()
        assert reader.reads == []


# --------------------------------------------------------------------------- #
# Rereading one file
# --------------------------------------------------------------------------- #
def test_reread_adds_a_new_file_of_the_corpus(folder):
    reader = CountingReader()
    with open_corpus(folder, reader=reader, rescan_before_reads=False) as corpus:
        write(folder, "sub/new.tla")
        write(folder, "a.tla", song("a", ["intro"]))  # changed, but not asked
        reader.reads.clear()
        report = corpus.reread(folder / "sub" / "new.tla")
        assert report.added == ("sub/new.tla",) and not report.changed
        assert reader.reads == ["new.tla"]  # nothing else is read
        assert {f.path: f.state for f in corpus.files()} == {
            "a.tla": "readable",
            "b.tla": "readable",
            "sub/new.tla": "readable",
        }  # the rest of the folder isn't scanned
        assert corpus.generation == 2
        assert corpus.reread("sub/new.tla").added == ()  # relative works too


def test_reread_reads_a_changed_file_at_once_whatever_its_date(folder):
    with open_corpus(folder, reader=JsonDocumentReader()) as corpus:
        path = folder / "a.tla"
        info = path.stat()
        write(folder, "a.tla", song("a", ["intrO", "chorus"]))  # the same size
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))  # the same date
        assert not corpus.scan()  # a scan can't see it
        report = corpus.reread("a.tla")
        assert report.changed == ("a.tla",)
        assert ("a.tla", "intrO") in labels(corpus)


def test_reread_of_a_file_gone_makes_it_unavailable(folder):
    with open_corpus(folder, reader=JsonDocumentReader()) as corpus:
        os.remove(folder / "a.tla")
        assert corpus.reread("a.tla").unavailable == ("a.tla",)


def test_reread_refuses_a_path_outside_the_corpus(folder, tmp_path_factory):
    outside = write(tmp_path_factory.mktemp("outside"), "x.tla")
    write(folder, ".hidden/y.tla")
    (folder / "notes.txt").write_text("x")
    write(folder, "z.tmp.tla")
    with open_corpus(folder, reader=JsonDocumentReader()) as corpus:
        for path in (outside, "../x.tla", ".hidden/y.tla", "notes.txt", "z.tmp.tla"):
            with pytest.raises(ValueError):
                corpus.reread(path)
        assert [f.path for f in corpus.files()] == ["a.tla", "b.tla"]


def test_reread_inside_a_read_raises(folder):
    with open_corpus(folder, reader=JsonDocumentReader()) as corpus:
        with corpus.reading():
            with pytest.raises(RuntimeError, match="inside a read"):
                corpus.reread("a.tla")


def test_a_reread_while_a_scan_finds_the_same_new_file_adds_it_once(folder):
    reader = CountingReader()
    with open_corpus(folder, reader=reader, rescan_before_reads=False) as corpus:
        write(folder, "new.tla")
        inside, go_on = threading.Event(), threading.Event()
        reader.hold["new.tla"] = (inside, go_on)
        reports = {}
        scanning = threading.Thread(
            target=lambda: reports.update(scan=corpus.scan()), daemon=True
        )
        scanning.start()
        assert inside.wait(PATIENCE)  # the scan is reading new.tla
        rereading = threading.Thread(
            target=lambda: reports.update(reread=corpus.reread("new.tla")),
            daemon=True,
        )
        rereading.start()
        try:
            wait_until(
                lambda: corpus._scanner.turn.waiting == 1
                or reader.reads.count("new.tla") > 1,
                "the reread neither waited for the scan nor read the file",
            )
        finally:
            go_on.set()
            scanning.join(PATIENCE)
            rereading.join(PATIENCE)
        assert not scanning.is_alive() and not rereading.is_alive()
        assert reports["scan"].added == ("new.tla",)
        assert reports["reread"].added == ()
        assert [f.path for f in corpus.files()] == ["a.tla", "b.tla", "new.tla"]
