import sqlite3

from tilia_core.index_schema import create_schema

COLUMNS = {
    "files": ["id", "path", "media_length", "time_unit", "time_map"],
    "timelines": [
        "id",
        "file_id",
        "kind",
        "name",
        "name_folded",
        "ordinal",
        "role",
        "author",
    ],
    "components": [
        "id",
        "file_id",
        "timeline_id",
        "kind",
        "start",
        "end",
        "label",
        "label_folded",
        "color",
        "comments",
    ],
    "hierarchies": ["component_id", "level", "parent_id", "depth"],
    "ranges": ["component_id", "row_id", "row", "row_folded"],
    "chords": [
        "component_id",
        "step",
        "accidental",
        "quality",
        "inversion",
        "applied_to",
        "custom_text",
        "key_id",
        "root",
        "roman",
        "symbol",
        "key",
    ],
    "keys": ["component_id", "step", "accidental", "mode", "tonic", "key"],
    "categories": ["component_id", "category"],
    "positions": [
        "component_id",
        "bar",
        "end_bar",
        "beat",
        "pass",
        "bar_count",
        "bar_label",
        "bar_beat_count",
        "downbeat",
    ],
    "measures": ["file_id", "count", "number", "label", "start", "end", "beats"],
    "fields": ["scope", "owner_id", "name", "value"],
}


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
        found = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
        assert found == columns, table


def test_indexes():
    con = make()
    found = []
    for table in ("components", "categories"):
        for row in con.execute(f"PRAGMA index_list({table})"):
            if row[3] == "c":
                found.append(
                    (
                        table,
                        [r[2] for r in con.execute(f"PRAGMA index_info({row[1]})")],
                    )
                )
    assert sorted(found) == [
        ("categories", ["category"]),
        ("categories", ["component_id"]),
        ("components", ["file_id", "timeline_id", "start"]),
        ("components", ["label_folded"]),
    ]
