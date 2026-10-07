"""``tql.sql``: one read-only statement, with limits, that never changes the
index."""

import contextlib
import sqlite3
import threading

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import readonly
from tilia_core.tql.syntax import TQLError

FIXTURES = examples.load()["fixtures"]
# What SQLite says when the authorizer refuses: a statement that runs and only
# then turns out to return no columns ("not a statement that reads") is no
# refusal. VACUUM's message differs: SQLite refuses its inner ATTACH.
REFUSED_BY = r"^(not authorized|authorization denied)"
FUNCTION_REFUSED = r"^not authorized to use function: "
# What SQLite says when PRAGMA query_only refuses a write.
READ_ONLY = r"^attempt to write a readonly database$"
LONG_READ = (
    "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT x FROM n"
)


@pytest.fixture
def index():
    return fixture_index.build_index(FIXTURES["exposition"])


def snapshot(index):
    """What a statement could change: the whole main database, temporary
    objects, attached databases, three pragmas and an open transaction."""
    con = index.connection()
    return (
        con.total_changes,
        con.in_transaction,
        list(con.iterdump()),
        con.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY name"
        ).fetchall(),
        con.execute(
            "SELECT type, name, sql FROM sqlite_temp_master ORDER BY name"
        ).fetchall(),
        con.execute("PRAGMA database_list").fetchall(),
        con.execute("PRAGMA writable_schema").fetchone(),
        con.execute("PRAGMA user_version").fetchone(),
        con.execute("PRAGMA query_only").fetchone(),
        {
            name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        },
    )


def sqlite_has(text):
    """Whether this Python's SQLite runs ``text`` (a module or a function that
    some builds leave out)."""
    try:
        sqlite3.connect(":memory:").execute(text)
    except sqlite3.OperationalError:
        return False
    return True


NO_FTS5 = pytest.mark.skipif(
    not sqlite_has("CREATE VIRTUAL TABLE t USING fts5(a)"), reason="no fts5"
)
NO_FTS3 = pytest.mark.skipif(
    not sqlite_has("SELECT fts3_tokenizer('simple')"), reason="no fts3"
)
REFUSED = [
    "INSERT INTO components SELECT * FROM components",
    "INSERT INTO fields VALUES ('file', 'f1', 'x', 'y') RETURNING *",
    "UPDATE components SET label = 'x'",
    "DELETE FROM components",
    "DELETE FROM components RETURNING id",
    "EXPLAIN DELETE FROM components",
    "CREATE TABLE t (a)",
    "CREATE TEMP TABLE t (a)",
    "CREATE TEMP VIEW v AS SELECT 1",
    "CREATE VIEW v AS SELECT 1",
    "CREATE TRIGGER g AFTER INSERT ON components BEGIN SELECT 1; END",
    pytest.param("CREATE VIRTUAL TABLE v USING fts5(a)", marks=NO_FTS5),
    "ALTER TABLE components RENAME TO c2",
    "ALTER TABLE components ADD COLUMN zz",
    "DROP TABLE components",
    "ATTACH DATABASE ':memory:' AS other",
    "DETACH DATABASE main",
    "PRAGMA writable_schema = ON",
    "PRAGMA query_only = OFF",
    "PRAGMA table_info(components)",
    "BEGIN",
    "COMMIT",
    "SAVEPOINT s",
    "ANALYZE",
    "REINDEX",
    "VACUUM",
    "REPLACE INTO components SELECT * FROM components",
    "WITH x AS (SELECT 1) DELETE FROM components",
]


@pytest.mark.parametrize("text", REFUSED)
def test_a_statement_that_writes_or_loads_is_refused_and_changes_nothing(index, text):
    before = snapshot(index)
    with pytest.raises(TQLError, match=REFUSED_BY):
        tql.sql(index, text)
    assert snapshot(index) == before


@pytest.mark.parametrize(
    "text",
    [
        "SELECT load_extension('nothing')",
        "SELECT LOAD_EXTENSION('nothing', 'entry')",
        pytest.param("SELECT fts3_tokenizer('simple')", marks=NO_FTS3),
    ],
)
def test_the_functions_that_load_code_are_refused(index, text):
    # SQLite refuses load_extension itself while loading is off, with a
    # plain "not authorized"; only the authorizer names the function.
    before = snapshot(index)
    with pytest.raises(TQLError, match=FUNCTION_REFUSED):
        tql.sql(index, text)
    assert snapshot(index) == before


@pytest.mark.skipif(
    not hasattr(sqlite3.Connection, "enable_load_extension"),
    reason="this Python cannot load extensions",
)
def test_load_extension_is_refused_when_loading_is_on(index):
    index.connection().enable_load_extension(True)
    before = snapshot(index)
    with pytest.raises(TQLError, match=FUNCTION_REFUSED):
        tql.sql(index, "SELECT load_extension('nothing')")
    assert snapshot(index) == before


def test_vacuum_into_writes_no_file(index, tmp_path):
    copy = tmp_path / "copy.db"
    before = snapshot(index)
    with pytest.raises(TQLError, match=REFUSED_BY):
        tql.sql(index, f"VACUUM INTO '{copy}'")
    assert not copy.exists()
    assert snapshot(index) == before


# What PRAGMA query_only refuses on its own (see readonly's docstring).
QUERY_ONLY_REFUSES = [
    "INSERT INTO components SELECT * FROM components",
    "UPDATE components SET label = 'x'",
    "DELETE FROM components",
    "CREATE TABLE t (a)",
    "CREATE TEMP TABLE t (a)",
    "DROP TABLE components",
    "ALTER TABLE components RENAME TO c2",
    "ALTER TABLE components ADD COLUMN zz",
    "PRAGMA user_version = 9",
]


@pytest.fixture
def no_authorizer(monkeypatch):
    """An authorizer that allows everything: only query_only is left."""
    monkeypatch.setattr(readonly, "_authorize", readonly._allow_all)


@pytest.mark.parametrize("text", QUERY_ONLY_REFUSES)
def test_query_only_refuses_a_write_the_authorizer_lets_through(
    index, no_authorizer, text
):
    before = snapshot(index)
    with pytest.raises(TQLError, match=READ_ONLY):
        tql.sql(index, text)
    con = index.connection()
    if con.in_transaction:
        # Python's sqlite3 began one before INSERT, UPDATE or DELETE, and the
        # refused write left it open with nothing in it.
        con.rollback()
    assert snapshot(index) == before


def test_query_only_refuses_vacuum_into_the_authorizer_lets_through(
    index, no_authorizer, tmp_path
):
    # SQLite can create the file before query_only refuses the write; that no
    # file appears is the authorizer's doing (test_vacuum_into_writes_no_file).
    before = snapshot(index)
    with pytest.raises(TQLError, match=READ_ONLY):
        tql.sql(index, f"VACUUM INTO '{tmp_path / 'copy.db'}'")
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


@pytest.mark.parametrize("text", ["SELECT 'a\x00b'", "SELECT '\ud800'"])
def test_text_sqlite_cannot_take_raises_a_tql_error(index, text):
    with pytest.raises(TQLError):
        tql.sql(index, text)


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


@pytest.mark.parametrize("query_only", [0, 1])
@pytest.mark.parametrize(
    "text, limits",
    [
        pytest.param("SELECT 1", {}, id="reads"),
        pytest.param("DELETE FROM components", {}, id="refused"),
        pytest.param("SELECT * FROM nope", {}, id="fails"),
        pytest.param("SELECT 'a\x00b'", {}, id="cannot-pass"),
        pytest.param(LONG_READ, {"time_limit": 0.01}, id="stopped"),
    ],
)
def test_query_only_is_put_back_as_it_was(index, query_only, text, limits):
    con = index.connection()
    con.execute(f"PRAGMA query_only = {query_only}")
    with contextlib.suppress(TQLError):
        tql.sql(index, text, **limits)
    assert con.execute("PRAGMA query_only").fetchone() == (query_only,)


def test_a_transaction_the_caller_has_open_is_left_alone(index, no_authorizer):
    con = index.connection()
    con.execute("CREATE TABLE scratch (a)")
    con.commit()
    con.execute("INSERT INTO scratch VALUES (1)")
    tql.sql(index, "SELECT 1")
    with pytest.raises(TQLError, match=READ_ONLY):
        tql.sql(index, "DELETE FROM scratch")
    assert con.in_transaction
    assert con.execute("PRAGMA query_only").fetchone() == (0,)
    con.execute("INSERT INTO scratch VALUES (2)")
    con.commit()
    assert con.execute("SELECT a FROM scratch").fetchall() == [(1,), (2,)]


def test_a_run_still_works_after_a_refused_call(index):
    with pytest.raises(TQLError):
        tql.sql(index, "DROP TABLE components")
    assert tql.run(index, "PAC IN cadences").rows
