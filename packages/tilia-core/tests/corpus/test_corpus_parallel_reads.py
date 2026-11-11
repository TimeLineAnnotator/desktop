"""Reading many files in worker processes
(TimeLineAnnotator/project-management#156).

A scan that reads at least ``scan.PARALLEL_READS_FROM`` files with WP3's
reader reads them in worker processes, and gives the index that reading them
one by one in this process gives. The tests lower the threshold, so that a few
files are enough."""

import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tilia_core import open_corpus
from tilia_core.corpus import _workers, scan
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
    threshold for reading in workers."""
    monkeypatch.setattr(scan, "PARALLEL_READS_FROM", 2, raising=False)
    here: list[str] = []
    one_by_one = scan.read_file

    def read_file(reader, found):
        here.append(found.path)
        return one_by_one(reader, found)

    monkeypatch.setattr(scan, "read_file", read_file)
    return here


def test_a_build_of_many_files_reads_them_in_workers(folder, in_workers):
    corpus = opened(folder)
    try:
        assert in_workers == []
        assert states(corpus) == [("readable", OLD_COUNT), ("unreadable", 1)]
    finally:
        corpus.close()


def test_a_rescan_of_many_changed_files_reads_them_in_workers(
    folder, in_workers, monkeypatch
):
    monkeypatch.setattr(scan, "PARALLEL_READS_FROM", 10**9, raising=False)
    corpus = opened(folder)
    try:
        in_workers.clear()
        monkeypatch.setattr(scan, "PARALLEL_READS_FROM", 2, raising=False)
        for path in sorted(folder.rglob("*.tla")):
            shutil.copy(path, path.with_name("copy-" + path.name))
        report = corpus.scan()
        assert in_workers == []
        assert len(report.added) == OLD_COUNT + 1
    finally:
        corpus.close()


def test_reading_in_workers_gives_the_index_reading_one_by_one_gives(
    folder, in_workers, monkeypatch
):
    corpus = opened(folder)
    try:
        assert in_workers == []
        parallel = tables(corpus)
    finally:
        corpus.close()
    monkeypatch.setattr(scan, "PARALLEL_READS_FROM", 10**9, raising=False)
    corpus = opened(folder)
    try:
        assert len(in_workers) == OLD_COUNT + 1
        assert tables(corpus) == parallel
    finally:
        corpus.close()


def test_when_the_workers_fail_the_files_are_read_here(
    folder, in_workers, monkeypatch, caplog
):
    monkeypatch.setattr(_workers, "_BOOT", "import sys\nsys.exit(3)\n")
    with caplog.at_level(logging.WARNING, logger=scan.LOG.name):
        corpus = opened(folder)
    try:
        assert len(in_workers) == OLD_COUNT + 1
        assert any(
            "couldn't be read in worker processes" in r.getMessage()
            for r in caplog.records
        )
        assert states(corpus) == [("readable", OLD_COUNT), ("unreadable", 1)]
    finally:
        corpus.close()


def test_a_frozen_program_reads_here(folder, in_workers, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    corpus = opened(folder)
    try:
        assert len(in_workers) == OLD_COUNT + 1
    finally:
        corpus.close()


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
    try:
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
    finally:
        corpus.close()


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
