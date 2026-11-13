"""Reading many files in worker processes
(TimeLineAnnotator/project-management#156).

A scan that reads at least ``scan.PARALLEL_READS_FROM`` files with WP3's
reader reads them in worker processes, and gives the index that reading them
one by one in this process gives. The tests lower the threshold, so that a few
files are enough."""

import _thread
import logging
import os
import pickle
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tilia_core import open_corpus
from tilia_core.corpus import _workers, cache, scan, tla_reader
from tilia_core.corpus.tla_reader import TlaReader

OLD = Path(__file__).parents[1] / "tla" / "old"
OLD_COUNT = len(list(OLD.glob("*.tla")))


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(scan, "sleep", lambda seconds: None)


@pytest.fixture
def folder(tmp_path):
    """Old files of every version in ``tests/tla/old``, some in a subfolder,
    and one that isn't JSON."""
    root = tmp_path / "corpus"
    (root / "sub").mkdir(parents=True)
    for i, path in enumerate(sorted(OLD.glob("*.tla"))):
        shutil.copy(path, root / ("sub" if i % 2 else "") / path.name)
    (root / "not-json.tla").write_text("{ not json", encoding="utf-8")
    return root


def opened(folder):
    return open_corpus(folder, rescan_before_reads=False)


def tables(corpus) -> dict[str, list[tuple]]:
    """Every row of every table, keys and all."""
    with corpus.reading() as r:
        con: sqlite3.Connection = r.connection
        names = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        return {
            name: sorted(
                con.execute(f'SELECT * FROM "{name}"').fetchall(),
                key=lambda row: [(v is None, str(v)) for v in row],
            )
            for name in names
        }


def states(corpus) -> list[tuple[str, int]]:
    with corpus.reading() as r:
        return r.connection.execute(
            "SELECT state, count(*) FROM files GROUP BY state ORDER BY state"
        ).fetchall()


@pytest.fixture
def in_workers(monkeypatch):
    """Files read in this process, through ``scan.read_file``; with a low
    threshold for reading in workers, and two of them, which start faster
    than one per CPU."""
    monkeypatch.setattr(scan, "PARALLEL_READS_FROM", 2)
    monkeypatch.setattr(_workers, "cpus", lambda: 2)
    here: list[str] = []
    one_by_one = scan.read_file

    def read_file(reader, found):
        here.append(found.path)
        return one_by_one(reader, found)

    monkeypatch.setattr(scan, "read_file", read_file)
    return here


def test_a_rescan_of_many_changed_files_reads_them_in_workers(
    folder, in_workers, monkeypatch
):
    monkeypatch.setattr(scan, "PARALLEL_READS_FROM", 10**9)
    with opened(folder) as corpus:
        in_workers.clear()
        monkeypatch.setattr(scan, "PARALLEL_READS_FROM", 2)
        for path in sorted(folder.rglob("*.tla")):
            shutil.copy(path, path.with_name("copy-" + path.name))
        report = corpus.scan()
        assert in_workers == []
        assert len(report.added) == OLD_COUNT + 1


def test_reading_in_workers_gives_the_index_reading_one_by_one_gives(
    folder, in_workers, monkeypatch
):
    with opened(folder) as corpus:
        assert in_workers == []
        parallel = tables(corpus)
    monkeypatch.setattr(scan, "PARALLEL_READS_FROM", 10**9)
    with opened(folder) as corpus:
        assert len(in_workers) == OLD_COUNT + 1
        assert tables(corpus) == parallel


def test_when_the_workers_fail_the_files_are_read_here(
    folder, in_workers, monkeypatch, caplog
):
    monkeypatch.setattr(_workers, "_BOOT", "import sys\nsys.exit(3)\n")
    with caplog.at_level(logging.WARNING, logger=scan.LOG.name):
        corpus = opened(folder)
    with corpus:
        assert len(in_workers) == OLD_COUNT + 1
        assert any(
            "couldn't be read in worker processes" in r.getMessage()
            for r in caplog.records
        )
        assert states(corpus) == [("readable", OLD_COUNT), ("unreadable", 1)]


def test_a_frozen_program_reads_here(folder, in_workers, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with opened(folder):
        assert len(in_workers) == OLD_COUNT + 1


def test_a_reader_failure_in_a_worker_is_logged_here_with_its_traceback(
    folder, in_workers, monkeypatch, caplog
):
    # The workers run in this process here, so that the failing reader
    # reaches them; what comes back is what a worker sends: the outcome and
    # the traceback's text.
    monkeypatch.setattr(
        _workers, "run", lambda function, tasks, workers: [function(*t) for t in tasks]
    )
    read = TlaReader.read

    def failing(self, path):
        if path.name == "0.7.0.tla":
            raise ZeroDivisionError("a bug in the reader")
        return read(self, path)

    monkeypatch.setattr(TlaReader, "read", failing)
    with caplog.at_level(logging.ERROR, logger=scan.LOG.name):
        corpus = opened(folder)
    with corpus:
        assert in_workers == []
        (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
        message = record.getMessage()
        assert "0.7.0.tla" in message
        assert "Traceback" in message
        assert "ZeroDivisionError: a bug in the reader" in message
        with corpus.reading() as r:
            (reason,) = r.connection.execute(
                "SELECT reason FROM files WHERE path = 'sub/0.7.0.tla'"
            ).fetchone()
        assert reason == "can't read: ZeroDivisionError: a bug in the reader"


def in_this_process(monkeypatch):
    """The workers run in this process, so that what the test patches reaches
    them; what comes back is what a worker sends, through pickle. The
    functions they ran, and the results they sent."""
    ran = SimpleNamespace(functions=[], results=[])

    def run(function, tasks, workers):
        ran.functions.append(function)
        results = [pickle.loads(pickle.dumps(function(*t))) for t in tasks]
        ran.results.extend(results)
        return results

    monkeypatch.setattr(_workers, "run", run)
    return ran


def test_the_workers_send_rows_instead_of_documents(folder, in_workers, monkeypatch):
    ran = in_this_process(monkeypatch)
    with opened(folder) as corpus:
        assert ran.functions == [scan._read_and_build_in_worker]
        outcomes = [result[0] for result in ran.results]
        assert all(o.document is None for o in outcomes)
        sent = [o for o in outcomes if o.prebuilt is not None]
        assert len(sent) == OLD_COUNT
        assert states(corpus) == [("readable", OLD_COUNT), ("unreadable", 1)]


def test_with_other_settings_the_rows_are_built_here(folder, in_workers, monkeypatch):
    ran = in_this_process(monkeypatch)
    with open_corpus(
        folder, rescan_before_reads=False, time_map_of=tla_reader.time_map_of
    ) as corpus:
        assert ran.functions == [scan._read_in_worker]
        assert states(corpus) == [("readable", OLD_COUNT), ("unreadable", 1)]


def test_the_time_maps_built_in_workers_are_those_built_here(
    folder, in_workers, monkeypatch
):
    with opened(folder) as corpus:
        parallel = {f.path: corpus.time_map(f.id) for f in corpus.files()}
    monkeypatch.setattr(scan, "PARALLEL_READS_FROM", 10**9)
    with opened(folder) as corpus:
        here = {f.path: corpus.time_map(f.id) for f in corpus.files()}
    assert in_workers
    assert any(tmap is not None for tmap in here.values())
    assert parallel.keys() == here.keys()
    for path, tmap in here.items():
        if tmap is None:
            assert parallel[path] is None, path
            continue
        sent = parallel[path]
        assert isinstance(sent, cache.LazyTimeMap), path
        assert (sent.timeline_id, sent.guessed) == (tmap.timeline_id, tmap.guessed)
        assert sent.measure_rows() == tmap.measure_rows(), path


def test_files_moved_keep_their_keys_when_read_in_workers(folder, in_workers):
    with opened(folder) as corpus:
        before = tables(corpus)
        (folder / "moved").mkdir()
        for path in sorted(folder.glob("*.tla")):
            path.rename(folder / "moved" / path.name)
        report = corpus.scan()
        assert in_workers == []
        assert report.moved
        after = tables(corpus)
    for table in before:
        if table != "files":  # its paths changed
            assert after[table] == before[table], table


def test_a_failure_to_build_rows_in_a_worker_is_logged_here_with_its_traceback(
    folder, in_workers, monkeypatch, caplog
):
    in_this_process(monkeypatch)
    rows_of = scan._rows_of
    bad = TlaReader().read(folder / "sub" / "0.7.0.tla").document_id

    def failing(document, *args):
        if document.document_id == bad:
            raise ZeroDivisionError("a bug in the rows")
        return rows_of(document, *args)

    monkeypatch.setattr(scan, "_rows_of", failing)
    with caplog.at_level(logging.ERROR, logger=scan.LOG.name):
        corpus = opened(folder)
    with corpus:
        assert in_workers == []
        (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
        message = record.getMessage()
        assert "can't be built" in message
        assert "0.7.0.tla" in message
        assert "Traceback" in message
        assert "ZeroDivisionError: a bug in the rows" in message
        with corpus.reading() as r:
            (state, reason) = r.connection.execute(
                "SELECT state, reason FROM files WHERE path = 'sub/0.7.0.tla'"
            ).fetchone()
        assert state == "unreadable"
        assert reason == "can't read: ZeroDivisionError: a bug in the rows"
        assert states(corpus) == [("readable", OLD_COUNT - 1), ("unreadable", 2)]


SCRIPT = """\
import sys
from tilia_core import open_corpus
from tilia_core.corpus import scan

scan.PARALLEL_READS_FROM = 2
read_here = []
one_by_one = scan.read_file
scan.read_file = lambda reader, found: read_here.append(found) or one_by_one(reader, found)
print("the script ran", flush=True)
corpus = open_corpus(sys.argv[1], rescan_before_reads=False)
with corpus.reading() as r:
    (files,) = r.connection.execute("SELECT count(*) FROM files").fetchone()
print("files", files, "read here", len(read_here), flush=True)
corpus.close()
"""


def test_a_script_without_a_main_guard_runs_once(folder, tmp_path):
    # multiprocessing's spawn runs the main module again in every worker, so
    # that such a script would run once per worker, each run reading the
    # whole folder again.
    script = tmp_path / "script.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(script), str(folder)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        "the script ran",
        f"files {OLD_COUNT + 1} read here 0",
    ]


def pid_and_path(n: int) -> tuple[int, int, list[str]]:
    return n, os.getpid(), list(sys.path)


def test_workers_give_results_in_order_from_other_processes_with_this_sys_path():
    results = _workers.run(pid_and_path, [(n,) for n in range(10)], 3)
    assert [n for n, _, _ in results] == list(range(10))
    assert os.getpid() not in {pid for _, pid, _ in results}
    assert len({pid for _, pid, _ in results}) <= 3
    assert all(path == sys.path for _, _, path in results)


def stop(n: int) -> None:
    if n == 5:
        os._exit(3)


def test_a_worker_that_stops_early_fails_the_run():
    with pytest.raises(_workers.WorkersFailed):
        _workers.run(stop, [(n,) for n in range(10)], 2)


def sleep_for(seconds: float) -> None:
    time.sleep(seconds)


def test_ctrl_c_stops_the_workers_at_once():
    # A wait without a timeout doesn't see Ctrl-C (on Windows, nor the
    # interrupt_main that stands for it here on every system).
    timer = threading.Timer(1.0, _thread.interrupt_main)
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            _workers.run(sleep_for, [(3,)] * 4, 2)
    finally:
        timer.cancel()
    assert time.monotonic() - started < 3


class NoThread(threading.Thread):
    def start(self):
        raise RuntimeError("can't start new thread")


def test_a_thread_that_cant_start_fails_the_run(monkeypatch):
    monkeypatch.setattr(
        _workers, "threading", SimpleNamespace(Lock=threading.Lock, Thread=NoThread)
    )
    with pytest.raises(_workers.WorkersFailed):
        _workers.run(sleep_for, [(0,)] * 2, 2)


def ctrl_c_ignored() -> bool:
    return signal.getsignal(signal.SIGINT) is signal.SIG_IGN


def test_workers_leave_ctrl_c_to_this_process():
    # Ctrl-C reaches every process of a terminal on Linux and macOS; this one
    # stops the workers, which would each print a traceback.
    assert _workers.run(ctrl_c_ignored, [()], 1) == [True]
