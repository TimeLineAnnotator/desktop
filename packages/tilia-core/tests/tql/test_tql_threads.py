"""``run`` and ``sql`` on several threads: each call uses the connection the
index reader gives its thread and keeps nothing between calls."""

import sqlite3
import threading
from collections import Counter

import examples
import fixture_index
import pytest
from test_tql_examples import _rows

from tilia_core import tql

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
