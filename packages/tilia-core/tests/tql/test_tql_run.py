"""tql.run on sequence patterns: lanes, literals, results, rows and keys."""

import sqlite3

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import compile as tql_compile
from tilia_core.tql import sqlfuncs
from tilia_core.tql.syntax import Lane

FIXTURES = examples.load()["fixtures"]


def index_of(name):
    return fixture_index.build_index(FIXTURES[name])


def lane_names(name, lane):
    index = index_of(name)
    specs = tql_compile.resolve_lanes(index.connection(), "f1", lane)
    return [s.description for s in specs]


def bare(text):
    return Lane(text, False)


def quoted(text):
    return Lane(text, True)


def starts(result):
    return [[(c.label, c.start) for s in m.slots for c in s] for m in result.matches]


# --------------------------------------------------------------------------- #
# Lanes
# --------------------------------------------------------------------------- #
class TestLanes:
    def test_no_lane_is_every_hierarchy_level_range_row_and_marker_timeline(self):
        assert lane_names("pop", None) == [
            "Form (A) · level 1",
            "Form (A) · level 2",
            "Form (B) · level 1",
            "Instruments · solo",
        ]
        assert lane_names("sonata", None) == [
            "Form (Caplin) · level 1",
            "Form (Caplin) · level 2",
            "Form (Caplin) · level 3",
            "Form (Caplin) · level 4",
            "Cadences",
            "Fermatas",
        ]

    def test_role(self):
        assert lane_names("pop", bare("form")) == [
            "Form (A) · level 1",
            "Form (A) · level 2",
            "Form (B) · level 1",
        ]
        assert lane_names("sonata", bare("cadences")) == ["Cadences"]
        assert lane_names("sonata", bare("cadence")) == ["Cadences"]

    def test_harmony_roles_take_their_own_lane(self):
        assert lane_names("sonata", bare("harmony")) == ["Harmony · chords"]
        assert lane_names("sonata", bare("keys")) == ["Harmony · keys"]

    def test_kind_words(self):
        assert lane_names("sonata", bare("markers")) == ["Cadences", "Fermatas"]
        assert lane_names("sonata", bare("marker")) == ["Cadences", "Fermatas"]
        assert lane_names("pop", bare("ranges")) == ["Instruments · solo"]
        assert lane_names("pop", bare("range")) == ["Instruments · solo"]
        assert lane_names("pop", bare("beats")) == ["Beats"]
        assert lane_names("pop", bare("beat")) == ["Beats"]
        assert lane_names("harmony", bare("chords")) == ["Harmony · chords"]
        assert lane_names("harmony", bare("key")) == ["Harmony · keys"]
        assert len(lane_names("pop", bare("hierarchies"))) == 3
        assert len(lane_names("pop", bare("hierarchy"))) == 3

    @pytest.mark.parametrize("word", ["bars", "bar", "measures", "measure"])
    def test_bars_are_not_yet_there(self, word):
        with pytest.raises(NotImplementedError):
            lane_names("pop", bare(word))

    def test_quoted_name_keeps_its_case(self):
        assert lane_names("pop", quoted("Form (A)")) == [
            "Form (A) · level 1",
            "Form (A) · level 2",
        ]
        assert lane_names("pop", quoted("form (a)")) == []

    def test_bare_word_ignores_case(self):
        assert lane_names("sonata", bare("FERMATAS")) == ["Fermatas"]
        assert lane_names("sonata", bare("fermatas")) == ["Fermatas"]

    def test_wildcard(self):
        assert lane_names("pop", quoted("Form (*)")) == [
            "Form (A) · level 1",
            "Form (A) · level 2",
            "Form (B) · level 1",
        ]
        assert lane_names("pop", quoted("*(B)")) == ["Form (B) · level 1"]

    def test_range_rows(self):
        assert lane_names("pop", bare("solo")) == ["Instruments · solo"]
        assert lane_names("pop", bare("SOLO")) == ["Instruments · solo"]
        assert lane_names("pop", quoted("solo")) == ["Instruments · solo"]
        assert lane_names("pop", quoted("Solo")) == []
        assert lane_names("pop", quoted("so*")) == ["Instruments · solo"]

    def test_a_timeline_name_gives_all_its_lanes(self):
        assert lane_names("sonata", bare("harmony")) != lane_names(
            "sonata", quoted("Harmony")
        )
        assert lane_names("sonata", quoted("Harmony")) == [
            "Harmony · chords",
            "Harmony · keys",
        ]

    def test_unknown_lane_is_empty(self):
        assert lane_names("pop", bare("nothing")) == []


# --------------------------------------------------------------------------- #
# Literals, against the candidate SQL
# --------------------------------------------------------------------------- #
LITERALS = {
    "length": 20,
    "grammar": "de Clercq",
    "timelines": [
        {
            "name": "Form (X)",
            "kind": "hierarchy",
            "units": [
                ["verse", 1, 0, 1],
                ["verse.modern", 1, 1, 2],
                ["bridge.modern", 1, 2, 3],
                ["Chorus", 1, 3, 4],
                ["verse/chorus", 1, 4, 5],
                ["verse 2", 1, 5, 6],
                ["it's", 1, 6, 7],
                ["verse_", 1, 7, 8],
                ["Straße", 1, 8, 9],
                ["", 1, 9, 10],
                ["100%", 1, 10, 11],
            ],
        }
    ],
}


def matched(query_text):
    index = fixture_index.build_index(LITERALS)
    con = index.connection()
    sqlfuncs.register(con)
    unit = tql.parse(query_text + " IN form").pattern.seq.steps[0].item
    sql, params = tql_compile.candidate_statement(unit, "f1")
    ids = {r[0] for r in con.execute(sql, params)}
    rows = con.execute("SELECT id, label FROM components ORDER BY start").fetchall()
    return [label for cid, label in rows if cid in ids]


class TestLiterals:
    def test_word_matches_its_category_and_subtypes(self):
        assert matched("verse") == ["verse", "verse.modern", "verse/chorus", "verse 2"]

    def test_word_ignores_case(self):
        assert matched("CHORUS") == ["Chorus", "verse/chorus"]
        assert matched("strasse") == ["Straße"]

    def test_subtype_matches_only_itself(self):
        assert matched("verse.modern") == ["verse.modern"]
        assert matched("bridge.modern") == ["bridge.modern"]

    def test_supertype_does_not_match_subtype_only_label(self):
        assert matched("bridge") == ["bridge.modern"]
        assert "bridge.modern" not in matched("bridge.classic")

    def test_underscore_and_percent_are_not_wildcards(self):
        assert matched("verse_") == ["verse_"]
        assert matched("100%") == ["100%"]
        assert "verse 2" not in matched("verse_")

    def test_both_needs_two_categories(self):
        assert matched("verse/chorus") == ["verse/chorus"]
        assert matched("verse/verse") == []

    def test_exact_label(self):
        assert matched('"verse"') == ["verse"]
        assert matched('"chorus"') == []
        assert matched('"Chorus"') == ["Chorus"]
        assert matched('"it\'s"') == ["it's"]

    def test_regex_is_case_sensitive(self):
        assert matched("/^ver/") == [
            "verse",
            "verse.modern",
            "verse/chorus",
            "verse 2",
            "verse_",
        ]
        assert matched("/^chorus/") == []
        assert matched("/chorus/") == ["verse/chorus"]

    def test_regex_can_ignore_case(self):
        assert matched("/(?i)^chorus/") == ["Chorus"]

    def test_not(self):
        got = matched("NOT verse")
        assert "verse" not in got and "verse 2" not in got
        assert "" in got and "Chorus" in got

    def test_not_regex_keeps_unlabelled(self):
        assert "" in matched("NOT /e/")

    def test_or(self):
        assert matched("Chorus OR bridge.modern") == [
            "bridge.modern",
            "Chorus",
            "verse/chorus",
        ]

    def test_wildcard_matches_an_unlabelled_unit(self):
        got = matched("*")
        assert len(got) == 11 and "" in got

    def test_positions_are_for_later(self):
        unit = tql.parse("verse[bar = 1] IN form").pattern.seq.steps[0].item
        with pytest.raises(NotImplementedError, match="positions"):
            tql_compile.candidate_statement(unit, "f1")

    def test_a_simple_comparison_is_in_the_candidate_statement(self):
        unit = tql.parse("verse[level = 1] IN form").pattern.seq.steps[0].item
        sql, params = tql_compile.candidate_statement(unit, "f1")
        assert "hierarchies" in sql and params[-1] == 1.0

    def test_candidate_statement_shape(self):
        unit = tql.parse("verse IN form").pattern.seq.steps[0].item
        sql, params = tql_compile.candidate_statement(unit, "f1")
        assert sql.startswith("SELECT c.id FROM components c WHERE c.file_id = ? AND (")
        assert params[0] == "f1"
        assert "'verse'" not in sql


# --------------------------------------------------------------------------- #
# Matches
# --------------------------------------------------------------------------- #
class TestRun:
    def test_a_unit_on_several_levels_is_reported_once(self):
        index = index_of("exposition")
        assert starts(tql.run(index, "TR IN form")) == [[("TR", 8)]]
        assert len(tql.run(index, "* IN form").matches) == 9

    def test_the_highest_level_is_the_match_lane(self):
        index = index_of("exposition")
        (m,) = tql.run(index, "TR IN form").matches
        assert m.lane == "Form (Caplin) · level 2"

    def test_text_and_parsed_query_agree(self):
        index = index_of("pop")
        a = tql.run(index, "verse THEN chorus IN form")
        b = tql.run(index, tql.parse("verse THEN chorus IN form"))
        assert [m.key for m in a.matches] == [m.key for m in b.matches]

    def test_action_is_ignored(self):
        index = index_of("pop")
        con = index.connection()
        before = con.execute("SELECT count(*) FROM categories").fetchone()
        a = tql.run(index, 'verse THEN chorus IN form -> TAG "x"')
        b = tql.run(index, "verse THEN chorus IN form")
        assert len(a.matches) == len(b.matches) == 3
        assert con.execute("SELECT count(*) FROM categories").fetchone() == before

    def test_marks_and_is_target(self):
        index = index_of("pop")
        result = tql.run(index, "verse+ THEN @chorus IN form")
        first = result.matches[0]
        assert [c.label for c in first.slots[0]] == ["verse", "verse"]
        assert first.marks == [[False, False], [True]]
        assert first.is_target(1, 1) is False
        assert first.is_target(2, 0) is True
        row = result.rows[0]
        assert row["label"] == "chorus"
        assert row["ids"] == "f1:t1:c6"
        assert (row["start"], row["end"]) == (40, 56)
        assert row["$1.label"] == "verse → verse"

    def test_without_at_every_unit_is_a_target(self):
        index = index_of("pop")
        m = tql.run(index, "verse+ THEN chorus IN form").matches[0]
        assert m.marks is None
        assert all(
            m.is_target(n + 1, k) for n, s in enumerate(m.slots) for k in range(len(s))
        )

    def test_a_match_whose_marked_steps_took_nothing_is_dropped(self):
        index = index_of("pop")
        got = tql.run(index, "chorus THEN @verse? THEN bridge IN form")
        assert got.matches == []
        got = tql.run(index, "chorus THEN @verse? THEN @bridge IN form")
        assert len(got.matches) == 2

    def test_whole_lane_modes(self):
        index = index_of("pop")
        assert len(tql.run(index, "STARTS WITH intro IN form").matches) == 2
        assert starts(tql.run(index, "ENDS WITH bridge IN form")) == [[("bridge", 120)]]

    def test_ranges(self):
        index = index_of("pop")
        got = tql.run(index, "solo IN ranges")
        assert starts(got) == [[("solo", 76)], [("solo", 92)]]
        assert got.rows[0]["lane"] == "solo"
        assert got.rows[0]["timeline"] == "Instruments"
        assert got.rows[0]["$1.timeline"] == "Instruments · solo"

    def test_markers_are_points(self):
        index = index_of("sonata")
        got = tql.run(index, "HC THEN PAC IN cadences")
        assert starts(got) == [[("HC", 128), ("PAC", 157)]]
        assert got.rows[0]["lane"] is None
        assert got.rows[0]["$1.timeline"] == "Cadences"

    def test_max_matches(self):
        index = index_of("exposition")
        got = tql.run(index, "* IN form", max_matches=3)
        assert len(got.matches) == 3 and got.stopped == "max_matches"
        assert tql.run(index, "* IN form").stopped is None

    def test_time_limit_and_cancel_are_accepted(self):
        index = index_of("exposition")
        got = tql.run(index, "* IN form", time_limit=5.0, cancel=lambda: False)
        assert len(got.matches) == 9

    def test_matches_are_ordered_by_file_then_start(self):
        index = fixture_index.build_index(FIXTURES["pop"], FIXTURES["strophic"])
        got = tql.run(index, "verse THEN chorus IN form")
        files = [r["file"] for r in got.rows]
        assert files == sorted(files)
        by_file = {}
        for r in got.rows:
            by_file.setdefault(r["file"], []).append(r["start"])
        assert all(v == sorted(v) for v in by_file.values())
        assert set(files) == {"f1", "f2"}

    def test_title_comes_from_the_file_field(self):
        fixture = dict(FIXTURES["exposition"], fields={"title": "Sonata"})
        got = tql.run(fixture_index.build_index(fixture), "TR IN form")
        assert got.rows[0]["title"] == "Sonata"
        assert tql.run(index_of("exposition"), "TR IN form").rows[0]["title"] is None

    def test_generation_and_explain(self):
        index = index_of("exposition")
        got = tql.run(index, "TR IN form")
        assert got.generation == index.generation
        assert got.explain == tql.explain(tql.parse("TR IN form"))
        assert got.grain == "match" and got.warnings == []

    @pytest.mark.parametrize(
        "text",
        [
            "verse THEN chorus IN form WITHIN 2 bars",
            "verse[bar = 1] IN form",
            "verse IN form WHERE level = 1 AND bar = 1",
        ],
    )
    def test_later_parts_say_so(self, text):
        with pytest.raises(NotImplementedError):
            tql.run(index_of("exposition"), text)

    def test_chord_literals_are_for_the_harmony_part(self):
        with pytest.raises(NotImplementedError, match="harmony"):
            tql.run(index_of("harmony"), "V7 THEN I IN harmony")

    def test_wildcard_over_chords(self):
        got = tql.run(index_of("harmony"), "* THEN * IN chords")
        assert got.matches


# --------------------------------------------------------------------------- #
# Rows and keys
# --------------------------------------------------------------------------- #
class TestRows:
    def test_columns_and_values(self):
        got = tql.run(index_of("pop"), "verse THEN chorus IN form")
        assert [m.slots[0][0].start for m in got.matches] == [8, 24, 56]
        row = got.rows[0]
        assert list(row) == [
            "file",
            "title",
            "timeline",
            "lane",
            "ids",
            "label",
            "start",
            "end",
            "bar",
            "beat",
            "$1.label",
            "$1.timeline",
            "$1.start",
            "$1.end",
            "$1.bar",
            "$1.ids",
            "$2.label",
            "$2.timeline",
            "$2.start",
            "$2.end",
            "$2.bar",
            "$2.ids",
        ]
        assert row["file"] == "f1"
        assert row["title"] is None
        assert row["timeline"] == "Form (B)"
        assert row["lane"] == "level 1"
        assert row["ids"] == "f1:t2:c2 f1:t2:c3"
        assert row["label"] == "verse → chorus"
        assert (row["start"], row["end"]) == (8, 56)
        assert (row["bar"], row["beat"]) == (3, 1)
        assert row["$1.label"] == "verse"
        assert row["$1.timeline"] == "Form (B) · level 1"
        assert (row["$1.start"], row["$1.end"], row["$1.bar"]) == (8, 40, 3)
        assert row["$1.ids"] == "f1:t2:c2"
        assert row["$2.label"] == "chorus"
        assert (row["$2.start"], row["$2.end"], row["$2.bar"]) == (40, 56, 11)
        assert row["$2.ids"] == "f1:t2:c3"

    def test_a_repeating_step_joins_its_units(self):
        got = tql.run(index_of("pop"), "verse+ THEN chorus IN form")
        row = got.rows[0]
        assert row["$1.label"] == "verse → verse"
        assert row["$1.ids"].count(" ") == 1
        assert (row["$1.start"], row["$1.end"]) == (8, 40)

    def test_no_time_map_means_no_position(self):
        got = tql.run(index_of("exposition"), "TR IN form")
        assert got.rows[0]["bar"] is None and got.rows[0]["beat"] is None
        assert got.rows[0]["$1.bar"] is None

    def test_an_optional_step_may_hold_none(self):
        got = tql.run(index_of("pop"), "bridge THEN bridge? THEN chorus IN form")
        assert len(got.matches) == 2  # one per analyst
        for m, row in zip(got.matches, got.rows, strict=True):
            assert m.slots[1] == []
            assert row["$2.label"] == "" and row["$2.start"] is None
            assert row["$2.bar"] is None and row["$2.ids"] == ""

    def test_keys_are_stable_across_runs(self):
        a = tql.run(index_of("pop"), "verse THEN chorus IN form")
        b = tql.run(index_of("pop"), "verse THEN chorus IN form")
        assert [m.key for m in a.matches] == [m.key for m in b.matches]
        assert a.matches[0].key == "f1|f1:t2/f1:t2:c2;f1:t2/f1:t2:c3"
        assert len({m.key for m in a.matches}) == 3

    def test_key_with_several_units_in_a_step(self):
        m = tql.run(index_of("pop"), "verse+ THEN chorus IN form").matches[0]
        assert m.key == "f1|f1:t1/f1:t1:c4,f1:t1/f1:t1:c5;f1:t1/f1:t1:c6"


# --------------------------------------------------------------------------- #
# SQL, and what a run leaves behind
# --------------------------------------------------------------------------- #
class TestSql:
    def test_run_writes_nothing(self):
        index = index_of("pop")
        con = index.connection()
        changes = con.total_changes
        master = con.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
        tql.run(index, "verse+ THEN @chorus IN form")
        tql.run(index, "* IN form")
        assert con.total_changes == changes
        assert (
            con.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
            == master
        )

    def test_sql_lists_the_statements_with_their_parameters(self):
        got = tql.run(index_of("pop"), 'verse THEN "it\'s" IN form')
        assert got.sql
        for statement in got.sql.split("\n\n"):
            assert statement.endswith(";")
        assert "?" not in got.sql
        assert "c.file_id = 'f1'" in got.sql
        assert "'it''s'" in got.sql
        assert "'verse'" in got.sql

    def test_numbers_and_null_are_written_as_they_are(self):
        from tilia_core.tql.engine import sql_literal

        assert sql_literal(3) == "3"
        assert sql_literal(2.5) == "2.5"
        assert sql_literal(None) == "NULL"
        assert sql_literal("a'b") == "'a''b'"


class TestSqlFuncs:
    def test_register_twice_is_harmless(self):
        con = sqlite3.connect(":memory:")
        sqlfuncs.register(con)
        sqlfuncs.register(con)
        assert con.execute("SELECT tql_fold('STRASSE')").fetchone() == ("strasse",)

    def test_regexp(self):
        con = sqlite3.connect(":memory:")
        sqlfuncs.register(con)
        q = "SELECT ? REGEXP ?"
        assert con.execute(q, ("Verse", "^V")).fetchone() == (1,)
        assert con.execute(q, ("Verse", "^v")).fetchone() == (0,)
        assert con.execute(q, ("Verse", "(?i)^v")).fetchone() == (1,)
        assert con.execute(q, (None, "x")).fetchone() == (0,)

    def test_regexp_reads_the_text_in_nfc(self):
        con = sqlite3.connect(":memory:")
        sqlfuncs.register(con)
        decomposed = "Sätze"
        assert con.execute("SELECT ? REGEXP ?", (decomposed, "Sätze")).fetchone() == (
            1,
        )

    def test_fold(self):
        con = sqlite3.connect(":memory:")
        sqlfuncs.register(con)
        assert con.execute("SELECT tql_fold('Straße')").fetchone() == ("strasse",)

    def test_color(self):
        con = sqlite3.connect(":memory:")
        sqlfuncs.register(con)
        got = con.execute(
            "SELECT tql_color('Pink'), tql_color('#FFC0CB'), tql_color('f00')"
        )
        assert got.fetchone() == ("#ffc0cb", "#ffc0cb", "#ff0000")
