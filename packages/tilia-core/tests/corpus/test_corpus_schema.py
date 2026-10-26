"""The index's tables, columns, types and indexes, as data-model.md lists them
(TimeLineAnnotator/project-management#124, #126)."""

import sqlite3

import pytest

from tilia_core.corpus.schema import KIND_TABLES, create_schema

# table: [(column, type)], in order
COLUMNS = {
    "files": [
        ("id", "INTEGER"),
        ("path", "TEXT"),
        ("document_id", "TEXT"),
        ("format_version", "TEXT"),
        ("state", "TEXT"),
        ("reason", "TEXT"),
        ("fingerprint", "TEXT"),
        ("media_length", "REAL"),
        ("time_unit", "TEXT"),
        ("time_map", "INTEGER"),
        ("time_map_guessed", "INTEGER"),
    ],
    "timelines": [
        ("id", "INTEGER"),
        ("file_id", "INTEGER"),
        ("uuid", "TEXT"),
        ("kind", "TEXT"),
        ("name", "TEXT"),
        ("name_folded", "TEXT"),
        ("ordinal", "INTEGER"),
        ("role", "TEXT"),
        ("author", "TEXT"),
    ],
    "components": [
        ("id", "INTEGER"),
        ("file_id", "INTEGER"),
        ("timeline_id", "INTEGER"),
        ("uuid", "TEXT"),
        ("kind", "TEXT"),
        ("start", "REAL"),
        ("end", "REAL"),
        ("label", "TEXT"),
        ("color", "TEXT"),
        ("comments", "TEXT"),
    ],
    "hierarchies": [
        ("component_id", "INTEGER"),
        ("level", "INTEGER"),
        ("parent_id", "INTEGER"),
        ("depth", "INTEGER"),
    ],
    "ranges": [
        ("component_id", "INTEGER"),
        ("row_id", "TEXT"),
        ("row", "TEXT"),
        ("row_folded", "TEXT"),
    ],
    "chords": [
        ("component_id", "INTEGER"),
        ("step", "INTEGER"),
        ("accidental", "INTEGER"),
        ("quality", "TEXT"),
        ("inversion", "INTEGER"),
        ("applied_to", "INTEGER"),
        ("custom_text", "TEXT"),
        ("key_id", "INTEGER"),
        ("root", "TEXT"),
        ("roman", "TEXT"),
        ("symbol", "TEXT"),
        ("key", "TEXT"),
    ],
    "keys": [
        ("component_id", "INTEGER"),
        ("step", "INTEGER"),
        ("accidental", "INTEGER"),
        ("mode", "TEXT"),
        ("tonic", "TEXT"),
        ("key", "TEXT"),
    ],
    "categories": [
        ("component_id", "INTEGER"),
        ("category", "TEXT"),
        ("supertype", "TEXT"),
    ],
    "positions": [
        ("component_id", "INTEGER"),
        ("bar", "INTEGER"),
        ("end_bar", "INTEGER"),
        ("beat", "REAL"),
        ("pass", "INTEGER"),
        ("bar_count", "INTEGER"),
        ("bar_label", "TEXT"),
        ("bar_beat_count", "INTEGER"),
        ("downbeat", "INTEGER"),
    ],
    "measures": [
        ("file_id", "INTEGER"),
        ("count", "INTEGER"),
        ("number", "INTEGER"),
        ("label", "TEXT"),
        ("start", "REAL"),
        ("end", "REAL"),
        ("beats", "INTEGER"),
        ("pass", "INTEGER"),
    ],
    "fields": [
        ("scope", "TEXT"),
        ("owner_id", "INTEGER"),
        ("name", "TEXT"),
        ("value", "TEXT"),
    ],
}

# data-model.md's "Indexes", and components (timeline_id) for TQL's lookups of
# a timeline's levels and rows (TimeLineAnnotator/project-management#144)
INDEXES = [
    ("categories", ["category"]),
    ("categories", ["component_id"]),
    ("components", ["file_id", "timeline_id", "start"]),
    ("components", ["timeline_id"]),
    ("fields", ["name"]),
    ("fields", ["scope", "owner_id"]),
    ("hierarchies", ["parent_id"]),
]


def make():
    con = sqlite3.connect(":memory:")
    create_schema(con)
    return con


def test_tables_and_columns():
    con = make()
    tables = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert tables == set(COLUMNS)
    for table, columns in COLUMNS.items():
        found = [(r[1], r[2]) for r in con.execute(f'PRAGMA table_info("{table}")')]
        assert found == columns, table


@pytest.mark.parametrize("table", ["files", "timelines", "components"])
def test_the_index_keys_are_integer_primary_keys(table):
    # an alias of the rowid: a text id can't be stored as a key
    con = make()
    pk = [r[1] for r in con.execute(f"PRAGMA table_info({table})") if r[5]]
    assert pk == ["id"]
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(f"INSERT INTO {table} (id) VALUES ('f1:t1')")


def test_the_schema_has_version_1():
    # the version of the names show SQL makes visible
    assert make().execute("PRAGMA user_version").fetchone() == (1,)


def test_indexes():
    con = make()
    found = []
    for table in COLUMNS:
        for row in con.execute(f"PRAGMA index_list({table})"):
            if row[3] == "c":
                found.append(
                    (
                        table,
                        [r[2] for r in con.execute(f"PRAGMA index_info({row[1]})")],
                    )
                )
    assert sorted(found) == INDEXES


def test_positions_are_found_by_component_through_the_primary_key():
    # data-model.md's index positions (component_id) is the primary key
    con = make()
    pk = [r[1] for r in con.execute("PRAGMA table_info(positions)") if r[5]]
    assert pk == ["component_id"]
    plan = con.execute(
        "EXPLAIN QUERY PLAN SELECT bar FROM positions WHERE component_id = 1"
    ).fetchall()
    assert "USING INTEGER PRIMARY KEY" in plan[0][3]


def test_a_timeline_lookup_uses_an_index():
    # TQL looks up a timeline's levels and rows by timeline_id alone
    con = make()
    plan = con.execute(
        "EXPLAIN QUERY PLAN SELECT id FROM components WHERE timeline_id = 1"
    ).fetchall()
    assert "INDEX components_by_timeline_id" in plan[0][3]


def test_every_kind_table_exists_and_is_keyed_by_component():
    con = make()
    assert KIND_TABLES == {
        "hierarchy": "hierarchies",
        "range": "ranges",
        "chord": "chords",
        "key": "keys",
    }
    for table in KIND_TABLES.values():
        columns = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        assert columns and columns[0] == "component_id", table
