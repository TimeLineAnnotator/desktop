"""The core's own writes (User Story 3; research R5, R11): ``writing()``,
``written()`` and ``fingerprint()``. The index writes no file: the tests write as
a writer would, in ``tmp_path``."""

import logging
import os
import threading
import time
from pathlib import Path

import corpus_docs
import pytest
from json_reader import JsonDocumentReader

from tilia_core import open_corpus, tql
from tilia_core.corpus import fingerprint, scan
from tilia_core.corpus.documents import UnreadableFile

PATIENCE = 10  # seconds a test waits for another thread
HOUR_NS = 3600 * 10**9
READER = JsonDocumentReader()


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(scan, "sleep", lambda seconds: None)


def song(name, labels=("verse", "chorus")):
    units = [[label, 1, 10 * i, 10 * (i + 1)] for i, label in enumerate(labels)]
    return corpus_docs.document(
        corpus_docs.hierarchy(units, fields={"role": "form"}), document_id=name
    )


def write(folder, relpath, document=None, **kw):
    return corpus_docs.write_doc(
        folder / relpath, document or song(Path(relpath).stem), **kw
    )


@pytest.fixture
def folder(tmp_path):
    for name in ("a", "b"):
        path = write(tmp_path, f"{name}.tla")
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns - HOUR_NS))
    return tmp_path


def opened(folder, **kw):
    kw.setdefault("reader", READER)
    kw.setdefault("rescan_before_reads", False)
    return open_corpus(folder, **kw)


def labels(corpus, path):
    with corpus.reading() as r:
        return [
            row[0]
            for row in r.connection.execute(
                "SELECT c.label FROM components c JOIN files f ON f.id = c.file_id "
                "WHERE f.path = ? ORDER BY c.start",
                (path,),
            )
        ]


def wait_until(condition, what):
    deadline = time.monotonic() + PATIENCE
    while not condition():
        assert time.monotonic() < deadline, what
        time.sleep(0.005)


# --------------------------------------------------------------------------- #
# User Story 3
# --------------------------------------------------------------------------- #
def test_scenario_1_a_write_told_to_the_index_is_held_at_once(folder):
    with opened(folder) as corpus:
        with corpus.writing():
            write(folder, "a.tla", song("a", ["intro", "outro"]))
            report = corpus.written("a.tla")
        assert report.changed == ("a.tla",)
        assert (report.generation_before, report.generation_after) == (1, 2)
        assert labels(corpus, "a.tla") == ["intro", "outro"]
        # the next scan doesn't take it for someone else's
        later = corpus.scan()
        assert not later and corpus.generation == 2


def test_scenario_2_a_change_by_another_program_afterwards_is_reported(folder):
    with opened(folder) as corpus:
        with corpus.writing():
            write(folder, "a.tla", song("a", ["intro"]))
            corpus.written("a.tla")
        write(folder, "a.tla", song("a", ["outro", "coda"]))  # another program
        assert corpus.scan().changed == ("a.tla",)
        assert labels(corpus, "a.tla") == ["outro", "coda"]


def test_scenario_3_the_fingerprint_on_disk_is_the_one_the_scan_records(folder):
    with opened(folder) as corpus:
        recorded = corpus.file("a.tla").fingerprint
        assert fingerprint(folder / "a.tla", READER) == recorded
        write(folder, "copy crlf.tla", song("a"), crlf=True)
        write(folder, "copy shuffled.tla", song("a"), shuffle_keys=True, bom=True)
        for name in ("copy crlf.tla", "copy shuffled.tla"):
            assert fingerprint(folder / name, READER) == recorded
        corpus.scan()
        assert corpus.file("copy crlf.tla").fingerprint == recorded


def test_fingerprint_raises_for_a_file_it_cant_read_and_without_a_reader(folder):
    (folder / "broken.tla").write_text("{oops", encoding="utf-8")
    with pytest.raises(UnreadableFile):
        fingerprint(folder / "broken.tla", READER)
    with pytest.raises(NotImplementedError, match="project-management#7"):
        fingerprint(folder / "a.tla")


# --------------------------------------------------------------------------- #
# writing() and written()
# --------------------------------------------------------------------------- #
def test_a_scan_started_while_writing_is_held_waits_and_then_reports_nothing(folder):
    with opened(folder) as corpus:
        reports = {}
        scanning = threading.Thread(
            target=lambda: reports.update(scan=corpus.scan()), daemon=True
        )
        with corpus.writing():
            write(folder, "a.tla", song("a", ["intro"]))  # written, not yet told
            scanning.start()
            wait_until(
                lambda: corpus._scanner.turn.waiting == 1 or "scan" in reports,
                "the scan neither waited nor ended",
            )
            assert "scan" not in reports  # it waits for writing()
            corpus.written("a.tla")
        scanning.join(PATIENCE)
        assert not scanning.is_alive()
        assert not reports["scan"]
        assert corpus.generation == 2  # the write's change, once


def test_a_read_inside_writing_does_not_rescan(folder, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(scan, "clock", lambda: now[0])
    with opened(folder, rescan_before_reads=True) as corpus:
        with corpus.writing():
            write(folder, "a.tla", song("a", ["intro"]))
            now[0] += 3
            assert tql.run(corpus, "intro IN form").matches == []  # no rescan
            corpus.written("a.tla")
            assert len(tql.run(corpus, "intro IN form").matches) == 1
        assert corpus.generation == 2


def test_written_with_another_fingerprint_keeps_what_is_on_disk(folder, caplog):
    with opened(folder) as corpus:
        expected = fingerprint(folder / "a.tla", READER)
        write(folder, "a.tla", song("a", ["someone", "else"]))  # in between
        with caplog.at_level(logging.WARNING, logger=scan.__name__):
            with corpus.writing():
                report = corpus.written("a.tla", fingerprint=expected)
        assert report.changed == ("a.tla",)
        assert labels(corpus, "a.tla") == ["someone", "else"]
        assert corpus.file("a.tla").fingerprint == fingerprint(folder / "a.tla", READER)
        assert any("on disk" in m and "a.tla" in m for m in caplog.messages)


def test_written_with_the_files_fingerprint_logs_nothing(folder, caplog):
    with opened(folder) as corpus:
        write(folder, "a.tla", song("a", ["intro"]))
        wrote = fingerprint(folder / "a.tla", READER)
        with caplog.at_level(logging.WARNING, logger=scan.__name__):
            corpus.written("a.tla", fingerprint=wrote)
        assert not [m for m in caplog.messages if "on disk" in m]


def test_a_second_written_for_the_same_write_does_not_move_the_generation(folder):
    with opened(folder) as corpus:
        with corpus.writing():
            write(folder, "a.tla", song("a", ["intro"]))
            assert corpus.written("a.tla")
            again = corpus.written("a.tla")
        assert not again and corpus.generation == 2


def test_written_adds_a_new_file_and_refuses_one_outside(folder, tmp_path_factory):
    outside = write(tmp_path_factory.mktemp("outside"), "x.tla")
    with opened(folder) as corpus:
        with corpus.writing():
            write(folder, "new.tla")
            assert corpus.written(folder / "new.tla").added == ("new.tla",)
            with pytest.raises(ValueError):
                corpus.written(outside)


def test_writing_and_written_inside_a_read_raise(folder):
    with opened(folder) as corpus:
        with corpus.reading():
            with pytest.raises(RuntimeError, match="inside a read"):
                with corpus.writing():
                    pass
            with pytest.raises(RuntimeError, match="inside a read"):
                corpus.written("a.tla")


def test_writing_is_re_entrant_and_written_works_inside_it(folder):
    with opened(folder) as corpus:
        done = threading.Event()

        def nested():
            with corpus.writing():
                with corpus.writing():
                    write(folder, "a.tla", song("a", ["intro"]))
                    corpus.written("a.tla")
            done.set()

        threading.Thread(target=nested, daemon=True).start()
        # a mutex that isn't re-entrant fails the test instead of hanging it
        assert done.wait(PATIENCE), "writing() inside writing() deadlocked"
        assert corpus._scanner.turn.waiting == 0
        assert labels(corpus, "a.tla") == ["intro"]
        corpus.scan()  # the mutex is free again


def test_a_scan_inside_writing_while_another_scan_waits_does_not_deadlock(folder):
    with opened(folder) as corpus:
        holding, done = threading.Event(), threading.Event()
        outcome = {}

        def writer():
            with corpus.writing():
                holding.set()
                wait_until(lambda: corpus._scanner._job is not None, "no waiting scan")
                write(folder, "a.tla", song("a", ["intro"]))
                outcome["inner"] = corpus.scan()  # its own, not the waiting one
            done.set()

        w = threading.Thread(target=writer, daemon=True)
        w.start()
        assert holding.wait(PATIENCE)
        other = threading.Thread(
            target=lambda: outcome.update(other=corpus.scan()), daemon=True
        )
        other.start()
        # a deadlock fails the test instead of hanging it
        assert done.wait(PATIENCE), "the scan inside writing() deadlocked"
        other.join(PATIENCE)
        assert not other.is_alive()
        assert outcome["inner"].changed == ("a.tla",)
        assert not outcome["other"]


def test_written_writes_nothing(folder):
    with opened(folder) as corpus:
        write(folder, "a.tla", song("a", ["intro"]))
        before = {p: p.read_bytes() for p in folder.rglob("*")}
        corpus.written("a.tla")
        fingerprint(folder / "a.tla", READER)
        assert {p: p.read_bytes() for p in folder.rglob("*")} == before
