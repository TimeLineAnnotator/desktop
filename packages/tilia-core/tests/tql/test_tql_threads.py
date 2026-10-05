"""``run`` and ``sql`` on several threads: each call uses the connection the
index reader gives its thread and keeps nothing between calls."""

import sqlite3
import subprocess
import sys
import threading
from collections import Counter

import examples
import fixture_index
import pytest
from test_tql_examples import _rows

from tilia_core import tql
from tilia_core.tql import TQLError
from tilia_core.tql.inuse import in_use

DATA = examples.load()
EXAMPLES = DATA["examples"]


def rows_of(index, example):
    result = tql.run(index, example.query)
    return Counter(_rows(result, tql.parse(example.query).has_target))


def own_indexes():
    """What a thread builds for itself: one index per fixture, made on demand."""
    made = {}

    def index_for(example):
        if example.fixture not in made:
            made[example.fixture] = fixture_index.build_index(
                DATA["fixtures"][example.fixture]
            )
        return made[example.fixture]

    return index_for


def alone():
    index_for = own_indexes()
    return {e.n: rows_of(index_for(e), e) for e in EXAMPLES}


@pytest.fixture(scope="module")
def expected():
    return alone()


def on_threads(work, count=2):
    """Run ``work(k)`` on ``count`` threads that start together; the results
    by thread. An exception of a thread is raised here."""
    barrier = threading.Barrier(count)
    results, errors = {}, []

    def target(k):
        try:
            barrier.wait()
            results[k] = work(k)
        except BaseException as err:  # noqa: BLE001
            errors.append(err)

    threads = [threading.Thread(target=target, args=(k,)) for k in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]
    return results


def test_every_example_on_two_threads_with_an_index_each(expected):
    def work(k):
        order = EXAMPLES if k == 0 else EXAMPLES[::-1]
        index_for = own_indexes()
        return {e.n: rows_of(index_for(e), e) for e in order}

    for got in on_threads(work).values():
        assert got == expected


class SharedReader:
    """An index reader over one file database that gives each thread a
    connection of its own, as the library's does."""

    def __init__(self, path, maps):
        self.path = path
        self._maps = maps
        self._local = threading.local()
        self.opened = 0
        self._lock = threading.Lock()

    def connection(self):
        con = getattr(self._local, "con", None)
        if con is None:
            con = self._local.con = sqlite3.connect(self.path)
            with self._lock:
                self.opened += 1
        return con

    def time_map(self, file_id):
        return self._maps.get(file_id)

    @property
    def generation(self):
        return 1


def shared_reader(tmp_path, name, fixture):
    built = fixture_index.build_index(fixture)
    path = tmp_path / f"{name}.db"
    target = sqlite3.connect(path)
    built.connection().backup(target)
    target.close()
    return SharedReader(path, built._maps)


def test_every_example_on_two_threads_sharing_one_reader(tmp_path, expected):
    readers = {
        name: shared_reader(tmp_path, name, fixture)
        for name, fixture in DATA["fixtures"].items()
    }

    def work(k):
        order = EXAMPLES if k == 0 else EXAMPLES[::-1]
        return {e.n: rows_of(readers[e.fixture], e) for e in order}

    for got in on_threads(work).values():
        assert got == expected
    assert all(r.opened <= 2 for r in readers.values())


def test_sql_on_two_threads_sharing_one_reader(tmp_path):
    reader = shared_reader(tmp_path, "sql", DATA["fixtures"]["exposition"])
    text = "SELECT id, label FROM components ORDER BY id"
    want = tql.sql(reader, text).rows
    got = on_threads(lambda k: [tql.sql(reader, text).rows for _ in range(20)])
    assert all(rows == want for runs in got.values() for rows in runs)


def test_a_cancel_on_one_thread_does_not_stop_the_other(tmp_path, expected):
    e = EXAMPLES[0]
    reader = shared_reader(tmp_path, "cancel", DATA["fixtures"][e.fixture])
    cancel = threading.Event()
    cancel.set()

    def work(k):
        if k == 0:
            return tql.run(reader, e.query, cancel=cancel).stopped
        return rows_of(reader, e)

    got = on_threads(work)
    assert got[0] == "cancelled"
    assert got[1] == expected[e.n]


def test_a_call_leaves_nothing_on_the_connection(tmp_path):
    reader = shared_reader(tmp_path, "left", DATA["fixtures"]["exposition"])
    tql.run(reader, "PAC IN cadences")
    con = reader.connection()
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    temp = con.execute("SELECT name FROM sqlite_temp_master").fetchall()
    assert temp == []
    tql.run(reader, "PAC IN cadences")
    assert {r[0] for r in con.execute("SELECT name FROM sqlite_master")} == tables


class HoldingReader:
    """An index reader that gives every thread the same connection. While
    ``armed`` is set, ``time_map`` says so (``inside``) and waits for
    ``release``, which holds the statement that asked for it open."""

    def __init__(self, index):
        self._index = index
        self.armed = threading.Event()
        self.inside = threading.Event()
        self.release = threading.Event()

    def connection(self):
        return self._index.connection()

    def time_map(self, file_id):
        if self.armed.is_set():
            self.inside.set()
            self.release.wait(10)
        return self._index.time_map(file_id)

    @property
    def generation(self):
        return self._index.generation


def in_thread(work):
    """Run ``work()`` on a new thread; what it returned, or the exception it
    raised."""
    box = []

    def target():
        try:
            box.append(work())
        except BaseException as err:  # noqa: BLE001
            box.append(err)

    t = threading.Thread(target=target)
    t.start()
    t.join(10)
    assert not t.is_alive()
    return box[0]


def shared_connection_scenario():
    """Run in a child process: calls from other threads raise while one thread
    holds a statement open on the shared connection."""
    reader = HoldingReader(fixture_index.build_index(DATA["fixtures"]["exposition"]))
    held = "SELECT id, tql_position(id, 1.0, 'bar') FROM files"
    alone_rows = tql.sql(reader, held).rows
    before = tql.run(reader, "PAC IN cadences")
    reader.armed.set()
    a = {}
    thread = threading.Thread(target=lambda: a.update(rows=tql.sql(reader, held).rows))
    thread.start()
    assert reader.inside.wait(10)
    reader.armed.clear()
    calls = [
        lambda: tql.run(reader, "PAC IN cadences"),
        lambda: tql.sql(reader, "SELECT count(*) FROM files"),
        lambda: before.stats("counts"),
    ]
    for call in calls:
        err = in_thread(call)
        assert isinstance(err, RuntimeError), err
    reader.release.set()
    thread.join(10)
    assert not thread.is_alive()
    assert a["rows"] == alone_rows
    after = in_thread(lambda: tql.run(reader, "PAC IN cadences"))
    assert after.rows == before.rows
    print("SCENARIO OK")


def test_a_shared_connection_raises_instead_of_freezing():
    code = (
        f"import sys; sys.path[:0] = {sys.path!r}\n"
        "import faulthandler; faulthandler.dump_traceback_later(30, exit=True)\n"
        "import test_tql_threads\n"
        "test_tql_threads.shared_connection_scenario()\n"
    )
    try:
        done = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired as err:
        pytest.fail(f"the child froze:\n{err.stdout}\n{err.stderr}")
    shown = f"stdout:\n{done.stdout}\nstderr:\n{done.stderr}"
    assert done.returncode == 0, shown
    assert "SCENARIO OK" in done.stdout, shown


def test_a_call_that_raises_or_stops_frees_its_connection():
    reader = fixture_index.build_index(DATA["fixtures"]["exposition"])
    cancel = threading.Event()
    cancel.set()
    err = in_thread(lambda: tql.sql(reader, "DELETE FROM files"))
    assert isinstance(err, TQLError)
    err = in_thread(lambda: tql.run(reader, "* IN cadences WHERE file.nosuchfield = 1"))
    assert isinstance(err, TQLError)
    stopped = in_thread(lambda: tql.run(reader, "PAC IN cadences", cancel=cancel))
    assert stopped.stopped == "cancelled"
    count = in_thread(lambda: tql.sql(reader, "SELECT count(*) FROM files"))
    assert count.rows == [(1,)]


def test_marks_nest_on_one_thread_and_are_per_connection():
    con = sqlite3.connect(":memory:", check_same_thread=False)
    other = sqlite3.connect(":memory:", check_same_thread=False)

    def enter(c):
        def work():
            with in_use(c):
                return "ok"

        return in_thread(work)

    with in_use(con):
        with in_use(con):
            pass
        assert isinstance(enter(con), RuntimeError)
        assert enter(other) == "ok"
    assert enter(con) == "ok"
    with pytest.raises(ValueError):
        with in_use(con):
            raise ValueError
    assert enter(con) == "ok"
