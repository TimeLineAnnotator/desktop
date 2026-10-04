"""``tql.sql``: one read-only statement, with limits, that never changes the
index."""

import threading

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql.syntax import TQLError

FIXTURES = examples.load()["fixtures"]


@pytest.fixture
def index():
    return fixture_index.build_index(FIXTURES["exposition"])


def snapshot(index):
    con = index.connection()
    return (
        con.total_changes,
        con.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY name"
        ).fetchall(),
        {
            name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        },
    )


REFUSED = [
    "INSERT INTO components SELECT * FROM components",
    "UPDATE components SET label = 'x'",
    "DELETE FROM components",
    "CREATE TABLE t (a)",
    "CREATE TEMP TABLE t (a)",
    "CREATE TEMP VIEW v AS SELECT 1",
    "CREATE VIEW v AS SELECT 1",
    "CREATE TRIGGER g AFTER INSERT ON components BEGIN SELECT 1; END",
    "DROP TABLE components",
    "ATTACH DATABASE ':memory:' AS other",
    "DETACH DATABASE main",
    "PRAGMA writable_schema = ON",
    "PRAGMA table_info(components)",
    "BEGIN",
    "COMMIT",
    "SAVEPOINT s",
    "SELECT load_extension('nothing')",
    "REPLACE INTO components SELECT * FROM components",
    "WITH x AS (SELECT 1) DELETE FROM components",
]


@pytest.mark.parametrize("text", REFUSED)
def test_a_statement_that_writes_or_loads_is_refused_and_changes_nothing(index, text):
    before = snapshot(index)
    with pytest.raises(TQLError):
        tql.sql(index, text)
    assert snapshot(index) == before


def test_two_statements_are_refused(index):
    before = snapshot(index)
    with pytest.raises(TQLError):
        tql.sql(index, "SELECT 1; DELETE FROM components")
    with pytest.raises(TQLError):
        tql.sql(index, "SELECT 1; SELECT 2")
    assert snapshot(index) == before


def test_an_empty_statement_is_refused(index):
    with pytest.raises(TQLError):
        tql.sql(index, "  -- nothing\n")


def test_a_read_gives_a_table(index):
    got = tql.sql(index, "SELECT id, label FROM components WHERE label = 'PAC'")
    assert got.columns == ["id", "label"]
    assert got.rows == [(r[0], "PAC") for r in got.rows] and len(got.rows) == 1
    assert isinstance(got.rows[0], tuple)
    assert got.stopped is None


def test_a_trailing_semicolon_and_comments_are_fine(index):
    got = tql.sql(index, "-- a comment\nSELECT 1 AS one;\n")
    assert got.rows == [(1,)]


def test_the_tql_functions_are_registered(index):
    got = tql.sql(
        index,
        "SELECT tql_fold('ÄB'), 'abc' REGEXP 'b', tql_color('red'), "
        "tql_position('f1', 1.0, 'bar')",
    )
    assert got.rows[0][0] == "äb"
    assert got.rows[0][1] == 1
    assert got.rows[0][2].startswith("#")


def test_with_recursive_is_allowed(index):
    got = tql.sql(
        index,
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n WHERE x < 5) "
        "SELECT x FROM n",
    )
    assert got.rows == [(1,), (2,), (3,), (4,), (5,)]


def test_max_rows_stops_reading(index):
    total = tql.sql(index, "SELECT id FROM components")
    got = tql.sql(index, "SELECT id FROM components", max_rows=3)
    assert len(total.rows) > 3
    assert got.rows == total.rows[:3]
    assert got.stopped == "max_rows"


def test_max_rows_equal_to_the_rows_is_not_a_stop(index):
    n = len(tql.sql(index, "SELECT id FROM components").rows)
    got = tql.sql(index, "SELECT id FROM components", max_rows=n)
    assert len(got.rows) == n
    assert got.stopped is None


def test_cancel_set_before_the_call_stops_it(index):
    cancel = threading.Event()
    cancel.set()
    got = tql.sql(
        index,
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
        "SELECT x FROM n",
        cancel=cancel,
    )
    assert got.stopped == "cancelled"


def test_a_time_limit_stops_a_long_read_without_raising(index):
    got = tql.sql(
        index,
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
        "SELECT x FROM n",
        time_limit=0.05,
    )
    assert got.stopped == "time_limit"


def test_a_failing_statement_raises_with_sqlites_message(index):
    with pytest.raises(TQLError, match="no such table: nope"):
        tql.sql(index, "SELECT * FROM nope")
    with pytest.raises(TQLError, match="no such column"):
        tql.sql(index, "SELECT nope FROM components")
    with pytest.raises(TQLError, match="syntax error"):
        tql.sql(index, "SELEC 1")


def test_the_connection_writes_normally_afterwards(index):
    con = index.connection()
    for text in ("DELETE FROM components", "SELECT 1", "SELECT * FROM nope"):
        try:
            tql.sql(index, text, max_rows=1)
        except TQLError:
            pass
    con.execute("CREATE TABLE scratch (a)")
    con.execute("INSERT INTO scratch VALUES (1)")
    con.execute("DROP TABLE scratch")
    assert con.execute("SELECT 1").fetchone() == (1,)
    # no progress handler is left behind: a long statement runs through
    tql.sql(index, "SELECT 1", time_limit=0.0001)
    assert con.execute(
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n WHERE x < 200000) "
        "SELECT count(*) FROM n"
    ).fetchone() == (200000,)


def test_a_run_still_works_after_a_refused_call(index):
    with pytest.raises(TQLError):
        tql.sql(index, "DROP TABLE components")
    assert tql.run(index, "PAC IN cadences").rows
