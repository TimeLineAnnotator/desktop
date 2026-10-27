"""The tables' reference page, ``docs/index-tables.md``, against the schema,
both ways (SC-006; FR-040)."""

import re
import sqlite3
from pathlib import Path

from tilia_core.corpus.schema import create_schema

PAGE = Path(__file__).resolve().parents[2] / "docs" / "index-tables.md"
HEADER = "| Column | Type | What it holds | From |"
SECTION = re.compile(r"^## `(\w+)`\s*$")


def documented() -> dict[str, list[tuple[str, str]]]:
    """Each table the page documents, with its columns and types in order. A
    section is a ``## `table` `` heading followed by one Markdown table with
    the page's four columns; every cell is filled in."""
    tables: dict[str, list[tuple[str, str]]] = {}
    current = None
    lines = PAGE.read_text(encoding="utf-8").splitlines()
    for n, line in enumerate(lines):
        heading = SECTION.match(line)
        if heading:
            current = heading.group(1)
            assert current not in tables, f"{current} is documented twice"
            tables[current] = []
            continue
        if line.startswith("| ") and current is not None:
            if line == HEADER or set(line) <= set("|- "):
                continue
            cells = [c.strip() for c in line.strip("|").split(" | ")]
            assert len(cells) == 4 and all(cells), f"line {n + 1}: {line}"
            column = re.fullmatch(r"`(\w+)`", cells[0])
            assert column, f"line {n + 1}: the column isn't `name`"
            tables[current].append((column.group(1), cells[1]))
        elif line.startswith("|"):
            raise AssertionError(f"line {n + 1}: a table outside a table's section")
    return tables


def in_the_schema() -> dict[str, list[tuple[str, str]]]:
    con = sqlite3.connect(":memory:")
    create_schema(con)
    names = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY rowid"
        )
    ]
    return {
        name: [(r[1], r[2]) for r in con.execute(f"PRAGMA table_info({name})")]
        for name in names
    }


def test_every_table_of_the_schema_is_on_the_page_and_no_other():
    assert set(documented()) == set(in_the_schema())


def test_every_column_and_type_is_on_the_page_in_order_and_no_other():
    page, schema = documented(), in_the_schema()
    for table, columns in schema.items():
        assert page[table] == columns, table


def test_every_tables_section_has_the_pages_header():
    text = PAGE.read_text(encoding="utf-8")
    sections = [s for s in text.split("\n## ")[1:] if s.startswith("`")]
    assert len(sections) == len(in_the_schema())
    for section in sections:
        assert HEADER in section, section.splitlines()[0]


def test_the_page_lists_the_indexes_of_the_schema():
    con = sqlite3.connect(":memory:")
    create_schema(con)
    text = PAGE.read_text(encoding="utf-8").split("\n## Indexes\n", 1)[1]
    for table, sql in con.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
    ):
        columns = sql[sql.index("(") + 1 : sql.rindex(")")]
        assert f"`{table} ({columns})`" in text, sql


def test_the_page_says_reads_run_side_by_side():
    assert "Reads run side by side" in PAGE.read_text(encoding="utf-8")
