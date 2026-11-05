"""The store of a corpus's index: the pool of read connections, the
readers-writer lock, the generation and closing (research R2, R3;
contracts/index-reader.md)."""

import itertools
import logging
import sqlite3
import subprocess
import sys
import threading
import time

import corpus_docs
import pytest

from tilia_core.corpus import build, store
from tilia_core.corpus.settings import NoSettings
from tilia_core.corpus.store import Store

PATIENCE = 10  # seconds a test waits for another thread on a loaded machine


def keys():
    return itertools.count(1).__next__


def rows_of(next_key, name="a", label="x"):
    doc = corpus_docs.document(
        corpus_docs.markers([[label, 1], ["y", 2]], tid="m", ordinal=1),
        document_id=name,
    )
    return build.rows(doc, NoSettings(), next_key).at(f"{name}.tla", None)


def test_a_new_store_is_empty_at_generation_0():
    s = Store()
    with s.reading() as r:
        assert r.generation == 0 and count(r, "files") == 0
    s.apply([], [rows_of(keys())])
    assert s.generation == 1
    s.close()


@pytest.fixture
def filled():
    """A store holding one file (generation 1), and its key counter."""
    s = Store()
    next_key = keys()
    assert s.apply([], [rows_of(next_key)]) is None
    yield s, next_key
    # on a thread of its own: a test that failed may have left a read open,
    # and close() waits for it
    closing = threading.Thread(target=s.close, daemon=True)
    closing.start()
    closing.join(PATIENCE)


def count(read, table="components"):
    return read.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


class Thread(threading.Thread):
    """A thread that keeps what its target returned, or raised."""

    def __init__(self, target):
        super().__init__(daemon=True)
        self._work = target
        self.result = self.error = None

    def run(self):
        try:
            self.result = self._work()
        except BaseException as err:  # noqa: BLE001
            self.error = err

    def finish(self):
        self.join(PATIENCE)
        assert not self.is_alive()
        if self.error is not None:
            raise self.error
        return self.result


def started(target):
    t = Thread(target)
    t.start()
    return t


# --------------------------------------------------------------------------- #
# Reads and changes
# --------------------------------------------------------------------------- #
def test_a_read_sees_one_generation_while_another_thread_applies_a_change(filled):
    s, next_key = filled
    inside, go_on = threading.Event(), threading.Event()
    seen = []

    def read():
        with s.reading() as r:
            seen.append((r.generation, count(r)))
            inside.set()
            assert go_on.wait(PATIENCE)
            seen.append((r.generation, count(r)))

    reader = started(read)
    assert inside.wait(PATIENCE)
    change = started(lambda: s.apply([], [rows_of(next_key, "b")]))
    time.sleep(0.2)
    assert change.is_alive()  # the change waits for the read
    go_on.set()
    reader.finish()
    assert change.finish() is None
    assert seen == [(1, 2), (1, 2)]
    with s.reading() as r:
        assert (r.generation, count(r)) == (2, 4)


def test_two_reads_run_at_once_each_on_its_own_connection_and_handler(filled):
    s, _ = filled
    barrier = threading.Barrier(2, timeout=PATIENCE)
    calls = [0, 0]

    def read(k):
        with s.reading() as r:
            barrier.wait()  # both reads are open now

            def handler(k=k):
                calls[k] += 1
                return 0

            r.connection.set_progress_handler(handler, 1)
            r.connection.execute(
                "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n "
                "WHERE i < 2000) SELECT count(*) FROM n"
            ).fetchall()
            barrier.wait()  # neither has ended
            return r.connection

    a, b = started(lambda: read(0)), started(lambda: read(1))
    con_a, con_b = a.finish(), b.finish()
    assert con_a is not con_b
    assert calls[0] > 0 and calls[1] > 0
    assert s.connections == 2


def test_a_change_waits_for_a_running_read(filled):
    s, next_key = filled
    inside, go_on = threading.Event(), threading.Event()

    def read():
        with s.reading():
            inside.set()
            assert go_on.wait(PATIENCE)

    reader = started(read)
    assert inside.wait(PATIENCE)
    change = started(lambda: s.apply([], [rows_of(next_key, "b")]))
    change.join(0.3)
    assert change.is_alive()
    assert s.generation == 1
    go_on.set()
    reader.finish()
    change.finish()
    assert s.generation == 2


def test_the_generation_moves_only_when_apply_changed_something(filled):
    s, next_key = filled
    assert s.generation == 1
    assert s.apply([], []) is None
    assert s.generation == 1
    assert s.apply([999], []) is None  # no such file
    assert s.generation == 1
    with s.reading() as r:
        (fid,) = r.connection.execute("SELECT id FROM files").fetchone()
    assert s.apply([fid], []) is None
    assert s.generation == 2
    with s.reading() as r:
        for table in ("files", "timelines", "components", "categories", "fields"):
            assert count(r, table) == 0, table
    assert s.apply([], [rows_of(next_key)]) is None
    assert s.generation == 3


def test_apply_deletes_every_row_of_a_file_and_only_its():
    s = Store()
    next_key = keys()
    doc = corpus_docs.every_kind(document_id="one")
    one = build.rows(doc, NoSettings(), next_key).at("one.tla", None)
    two = build.rows(
        corpus_docs.every_kind(document_id="two"), NoSettings(), next_key
    ).at("two.tla", None)
    s.apply([], [one, two])
    with s.reading() as r:
        before = {t: count(r, t) for t in one.TABLES}
    s.apply([one.file_id], [])
    with s.reading() as r:
        for table, found in two.tables().items():
            assert count(r, table) == len(found), table
        assert before["components"] == 2 * len(two.components)
    s.close()


def test_a_nested_read_does_not_wait_behind_a_waiting_change(filled):
    s, next_key = filled
    inside, go_on = threading.Event(), threading.Event()
    nested = []

    def read():
        with s.reading() as outer:
            inside.set()
            assert go_on.wait(PATIENCE)
            with s.reading() as inner:  # a change is waiting now
                nested.append(inner.connection is outer.connection)
                nested.append(inner.generation == outer.generation)
            # without the check, this thread would wait for its own read:
            # reader.finish() below fails, and the fixture's close gives up
            with pytest.raises(RuntimeError, match="inside a read"):
                s.apply([], [])

    reader = started(read)
    assert inside.wait(PATIENCE)
    change = started(lambda: s.apply([], [rows_of(next_key, "b")]))
    time.sleep(0.2)
    go_on.set()
    reader.finish()
    change.finish()
    assert nested == [True, True]


@pytest.mark.parametrize("patience, waits", [(60.0, False), (0.0, True)])
def test_new_reads_wait_only_once_a_change_has_waited_too_long(
    filled, monkeypatch, patience, waits
):
    s, next_key = filled
    monkeypatch.setattr(store, "PATIENCE", patience)
    inside, go_on = threading.Event(), threading.Event()

    def hold():
        with s.reading():
            inside.set()
            assert go_on.wait(PATIENCE)

    holder = started(hold)
    assert inside.wait(PATIENCE)
    change = started(lambda: s.apply([], [rows_of(next_key, "b")]))
    time.sleep(0.2)  # the change is waiting

    def read_once():
        with s.reading() as r:
            return r.generation

    newcomer = started(read_once)
    newcomer.join(0.3)
    assert newcomer.is_alive() is waits
    go_on.set()
    holder.finish()
    change.finish()
    if waits:
        assert newcomer.finish() == 2  # it read after the change
    else:
        assert newcomer.finish() == 1


def test_connection_raises_outside_reading(filled):
    s, _ = filled
    with pytest.raises(RuntimeError, match="inside reading"):
        s.connection()
    with s.reading() as r:
        assert s.connection() is r.connection
        with s.reading():
            assert s.connection() is r.connection
    with pytest.raises(RuntimeError):
        s.connection()


def test_a_readings_connection_raises_in_another_thread(filled):
    s, _ = filled
    with s.reading() as r:
        r.connection.execute("SELECT 1").fetchall()
        other = started(lambda: r.connection)
        other.join(PATIENCE)
        assert isinstance(other.error, RuntimeError)


def test_a_reading_gives_the_time_maps_and_availability_of_its_generation(filled):
    s, next_key = filled
    with s.reading() as r:
        assert r.available is True and r.time_map(1) is None
    rows = rows_of(next_key, "b")
    marker = object()
    s.apply([], [rows], time_maps={rows.file_id: marker})
    s.available = False
    with s.reading() as r:
        assert r.time_map(rows.file_id) is marker
        assert r.available is False
        held = r
    s.apply([rows.file_id], [], time_maps={rows.file_id: None})
    assert held.time_map(rows.file_id) is marker  # a read keeps its generation's
    with s.reading() as r:
        assert r.time_map(rows.file_id) is None


# --------------------------------------------------------------------------- #
# A statement left open
# --------------------------------------------------------------------------- #
def leave_a_cursor_open(s):
    with s.reading() as r:
        cursor = r.connection.execute("SELECT * FROM components")
        cursor.fetchone()  # the statement is running: it holds a table lock
    return cursor


def snapshot(s):
    with s.reading() as r:
        return {
            t: r.connection.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
            for t in ("files", "components", "categories")
        }


def test_a_cursor_left_open_fails_a_change_cleanly_and_not_for_good(filled, caplog):
    s, next_key = filled
    cursor = leave_a_cursor_open(s)
    before = snapshot(s)  # reads don't conflict with the open statement
    with s.reading() as r:
        (fid,) = r.connection.execute("SELECT id FROM files").fetchone()
    started_at = time.monotonic()
    with caplog.at_level(logging.ERROR, logger="tilia_core.corpus.store"):
        err = s.apply([fid], [rows_of(next_key, "b")])
    waited = time.monotonic() - started_at
    assert isinstance(err, sqlite3.OperationalError) and "locked" in str(err)
    assert 2.0 <= waited < 2.0 + PATIENCE  # retried for 2 s
    assert any("couldn't be changed" in m for m in caplog.messages)
    cursor.close()
    assert snapshot(s) == before
    assert s.generation == 1
    # nothing stays broken: the same change applies once the cursor is closed
    assert s.apply([fid], [rows_of(next_key, "b")]) is None
    assert s.generation == 2


def test_a_cursor_closed_while_apply_retries_lets_it_through(filled):
    s, next_key = filled
    cursor = leave_a_cursor_open(s)
    closer = threading.Timer(0.5, cursor.close)
    closer.start()
    started_at = time.monotonic()
    assert s.apply([], [rows_of(next_key, "b")]) is None
    assert 0.4 <= time.monotonic() - started_at < 2.0
    closer.join()
    assert s.generation == 2


# --------------------------------------------------------------------------- #
# The pool
# --------------------------------------------------------------------------- #
def test_fifty_threads_eight_at_a_time_leave_at_most_eight_connections(filled):
    s, _ = filled
    at_once = threading.BoundedSemaphore(8)
    used = set()
    lock = threading.Lock()

    def read():
        with at_once:
            with s.reading() as r:
                with lock:
                    used.add(id(r.connection))
                r.connection.execute("SELECT count(*) FROM components").fetchall()
                time.sleep(0.01)

    threads = [started(read) for _ in range(50)]
    for t in threads:
        t.finish()
    assert 1 <= s.connections <= 8
    opened = s.connections
    for _ in range(20):
        started(read).finish()
    assert s.connections == opened  # later reads reuse them
    assert len(used) <= 8


def test_a_connection_comes_back_without_its_handler_and_authorizer(filled):
    s, _ = filled
    with s.reading() as r:
        con = r.connection
        con.set_progress_handler(lambda: 1, 1)  # would interrupt every statement
        con.set_authorizer(lambda *a: sqlite3.SQLITE_DENY)  # would refuse every one
        con.row_factory = sqlite3.Row
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("SELECT count(*) FROM components").fetchall()
    with s.reading() as r:
        assert r.connection is con  # the idle one, reused
        assert r.connection.execute("SELECT count(*) FROM components").fetchall() == [
            (2,)
        ]


# --------------------------------------------------------------------------- #
# Closing
# --------------------------------------------------------------------------- #
def test_close_inside_a_read_raises_and_a_second_close_does_nothing():
    s = Store()

    def close_inside_a_read():
        with s.reading():
            s.close()

    inside = started(close_inside_a_read)
    inside.join(PATIENCE)  # without the check, it would wait for itself
    assert isinstance(inside.error, RuntimeError)
    s.close()
    s.close()
    with pytest.raises(RuntimeError):
        with s.reading():
            pass
    with pytest.raises(RuntimeError):
        s.apply([], [])


def close_during_reads_scenario():
    """Run in a child process: ``close()`` while reads run statements that call
    a Python function closing over their connection, as WP13's do. It waits
    for them, then closes every connection; on Python 3.10, closing one while
    such a statement runs would deadlock."""
    s = Store()
    next_key = keys()
    s.apply([], [rows_of(next_key, f"f{k}") for k in range(20)])
    inside = threading.Barrier(5, timeout=30)
    kept, errors = [], []

    def read():
        try:
            with s.reading() as r:
                con = r.connection
                # a function that closes over its connection, as tql_chord does
                con.create_function("slow", 1, lambda x, con=con: x if con else None)
                kept.append(con)
                inside.wait()
                con.execute(
                    "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n "
                    "WHERE i < 20000) SELECT sum(slow(i)) FROM n, components"
                ).fetchall()
        except BaseException as err:  # noqa: BLE001
            errors.append(err)

    threads = [threading.Thread(target=read) for _ in range(4)]
    for t in threads:
        t.start()
    inside.wait()  # every read is running its statement
    s.close()
    for t in threads:
        t.join(30)
        assert not t.is_alive()
    assert errors == [], errors  # every read ran to its end before the close
    for con in kept:
        try:
            con.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            pass
        else:
            raise AssertionError("a connection kept past its read is still open")
    fresh = sqlite3.connect(s._uri, uri=True)
    tables = fresh.execute("SELECT name FROM sqlite_master").fetchall()
    fresh.close()
    assert tables == [], tables
    print("SCENARIO OK")


def test_close_waits_for_reads_that_call_python_and_closes_every_connection():
    code = (
        f"import sys; sys.path[:0] = {sys.path!r}\n"
        "import faulthandler; faulthandler.dump_traceback_later(60, exit=True)\n"
        "import test_corpus_store\n"
        "test_corpus_store.close_during_reads_scenario()\n"
    )
    try:
        done = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
        )
    except subprocess.TimeoutExpired as err:
        pytest.fail(f"the child froze:\n{err.stdout}\n{err.stderr}")
    shown = f"stdout:\n{done.stdout}\nstderr:\n{done.stderr}"
    assert done.returncode == 0, shown
    assert "SCENARIO OK" in done.stdout, shown


def test_the_database_is_one_per_store():
    a, b = Store(), Store()
    next_key = keys()
    a.apply([], [rows_of(next_key)])
    with b.reading() as r:
        assert count(r, "files") == 0
    a.close()
    b.close()
