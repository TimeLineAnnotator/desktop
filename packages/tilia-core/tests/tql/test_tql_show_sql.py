"""``Result.sql``: the statements a run executed, with their values inline and
comments naming the parts of the query, each runnable as shown through
``tql.sql``."""

import re
import sqlite3

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql.syntax import TQLError

DATA = examples.load()
FIXTURES = DATA["fixtures"]
RUNNABLE = [e for e in DATA["examples"] if not e.writes or e.query]


def index_of(name):
    return fixture_index.build_index(FIXTURES[name])


def blocks(text):
    """``(comment lines, statement)`` pairs of ``Result.sql``; a comment with no
    statement after it (a Python stage) has an empty statement."""
    out = []
    comments, lines = [], []
    for line in text.splitlines():
        if lines:
            lines.append(line)
            if sqlite3.complete_statement("\n".join(lines)):
                out.append((comments, "\n".join(lines)))
                comments, lines = [], []
        elif line.startswith("--"):
            comments.append(line)
        elif line.strip():
            lines.append(line)
            if sqlite3.complete_statement(line):
                out.append((comments, line))
                comments, lines = [], []
        elif comments:  # a blank line after a comment alone: a Python stage
            out.append((comments, ""))
            comments = []
    assert not lines, "a statement is not closed by ;"
    if comments:
        out.append((comments, ""))
    return out


def statements(text):
    return [s for _, s in blocks(text) if s]


def shown_rows(index, text):
    """Every value of every row the shown statements return."""
    seen = set()
    for statement in statements(text):
        seen.update(v for row in tql.sql(index, statement).rows for v in row)
    return seen


def component_ids(result):
    return {c.id for m in result.matches for slot in m.slots for c in slot}


class TestShownStatementsRun:
    def test_every_example_shows_statements_that_run_and_return_what_the_run_used(
        self,
    ):
        checked = 0
        for ex in DATA["examples"]:
            index = index_of(ex.fixture)
            try:
                got = tql.run(index, ex.query)
            except NotImplementedError:
                continue
            rows = shown_rows(index, got.sql)
            used = {
                c.id
                for m in got.matches
                for slot in m.slots
                for c in slot
                if c.kind != "bar"
            }
            assert used <= rows, (ex.query, used - rows)
            checked += 1
        assert checked > 20

    def test_a_label_filter_shows_one_statement_naming_its_unit(self):
        index = index_of("exposition")
        got = tql.run(index, "PAC IN cadences")
        (comments, statement), *_ = blocks(got.sql)
        assert comments == ["-- $1: PAC IN cadences"]
        assert "'pac'" in statement and "c.file_id = 'f1'" in statement
        assert statement.endswith(";")
        rows = tql.sql(index, statement).rows
        assert [c.id for m in got.matches for s in m.slots for c in s] == [
            r[0] for r in rows
        ]

    def test_statements_are_separated_by_a_blank_line_and_end_with_a_semicolon(self):
        got = tql.run(index_of("exposition"), "continuation THEN @ST IN form")
        for part in got.sql.split("\n\n"):
            lines = part.splitlines()
            assert lines[0].startswith("--")
            assert lines[-1].startswith("--") or lines[-1].endswith(";")

    def test_each_unit_of_a_sequence_names_its_number(self):
        got = tql.run(index_of("pop"), "verse THEN chorus IN form")
        comments = [c for cs, s in blocks(got.sql) if s for c in cs]
        assert comments == ["-- $1: verse IN form", "-- $2: chorus IN form"]

    def test_a_python_stage_is_a_comment_after_the_statements_it_reads(self):
        got = tql.run(index_of("pop"), "verse THEN chorus IN form")
        parts = blocks(got.sql)
        comments, statement = parts[-1]
        assert statement == ""
        assert comments == [
            "-- verse THEN chorus IN form: the units above, in time order per "
            "lane; THEN is matched in Python."
        ]
        assert all(s for _, s in parts[:-1])

    def test_where_is_a_python_stage_too(self):
        got = tql.run(index_of("pop"), "verse IN form WHERE start > 10")
        assert "-- WHERE start > 10:" in got.sql
        assert "Python" in got.sql.split("-- WHERE")[1]

    def test_values_are_inline_and_quoted_as_sqlite_does(self):
        index = index_of("pop")
        got = tql.run(index, 'verse THEN "it\'s" IN form')
        assert "?" not in got.sql
        assert "'it''s'" in got.sql
        assert "c.file_id = 'f1'" in got.sql
        shown_rows(index, got.sql)

    def test_a_statement_that_ran_once_per_file_is_shown_once_per_file(self):
        index = fixture_index.build_index(FIXTURES["sonata"], FIXTURES["exposition"])
        got = tql.run(index, "PAC IN cadences")
        files = [
            re.search(r"c\.file_id = '(\w+)'", s).group(1) for s in statements(got.sql)
        ]
        assert files == ["f1", "f2"]

    def test_bookkeeping_reads_are_not_shown(self):
        got = tql.run(index_of("exposition"), "PAC IN cadences")
        assert "FROM timelines" not in got.sql
        assert "FROM positions" not in got.sql
        assert "FROM fields" not in got.sql


class TestRelations:
    def test_the_sentence_form_is_one_join_with_the_tolerance(self):
        index = index_of("exposition")
        got = tql.run(index, "PAC IN cadences SAME END MT IN form")
        (comments, statement), *rest = blocks(got.sql)
        assert comments[0].startswith("-- $1 SAME END $2")
        assert "FROM components a JOIN components b ON" in statement
        assert "0.1" in statement and "?" not in statement
        assert len([s for _, s in blocks(got.sql) if s]) == 1
        rows = tql.sql(index, statement).rows
        for m in got.matches:
            assert (m.slots[0][0].id, m.slots[1][0].id) in {(r[0], r[2]) for r in rows}

    def test_within_is_written_as_its_amount_in_seconds(self):
        got = tql.run(
            index_of("exposition"), "HC IN cadences BEFORE PAC IN cadences WITHIN 2 s"
        )
        assert "2.0" in got.sql

    def test_a_bracket_relation_is_an_exists_in_its_units_statement(self):
        index = index_of("exposition")
        got = tql.run(index, "ST[CONTAINS PAC IN cadences] IN form")
        (comments, statement), *_ = blocks(got.sql)
        assert comments[0].startswith("-- $1: ST[CONTAINS PAC IN cadences] IN form")
        assert "EXISTS (SELECT 1 FROM components" in statement
        assert "0.1" in statement
        assert shown_rows(index, got.sql) >= component_ids(got)

    def test_an_order_relation_is_a_python_stage(self):
        index = index_of("exposition")
        got = tql.run(index, "ST[STARTS WITH presentation] IN form")
        parts = blocks(got.sql)
        assert any(not s and "Python" in " ".join(c) for c, s in parts)
        assert shown_rows(index, got.sql) >= component_ids(got)

    def test_a_negated_sentence_relation_runs_as_shown(self):
        index = index_of("exposition")
        got = tql.run(index, "* IN form NOT CONTAINS PAC IN cadences")
        assert "NOT EXISTS" in got.sql
        assert shown_rows(index, got.sql) >= component_ids(got)

    def test_the_shown_statement_of_a_unit_is_its_candidates(self):
        index = index_of("exposition")
        got = tql.run(index, "continuation IN form")
        rows = [r[0] for r in tql.sql(index, statements(got.sql)[0]).rows]
        assert sorted(rows) == sorted(
            c.id for m in got.matches for s in m.slots for c in s
        )


def test_showing_sql_changes_nothing_in_the_index():
    index = index_of("exposition")
    got = tql.run(index, "PAC IN cadences SAME END MT IN form")
    con = index.connection()
    changes = con.total_changes
    for statement in statements(got.sql):
        tql.sql(index, statement)
    assert con.total_changes == changes


def test_a_shown_statement_refuses_to_write_when_edited():
    index = index_of("exposition")
    with pytest.raises(TQLError):
        tql.sql(index, "DELETE FROM components;")
