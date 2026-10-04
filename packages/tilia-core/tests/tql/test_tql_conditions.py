"""Conditions (tql.md §7): fields in brackets and in ``WHERE``, the value forms,
the case rules, ``$n``, captures, queries of only ``WHERE``, and the names and
lanes a query may use, on the examples' fixtures and on small ones built here."""

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import compile as tql_compile
from tilia_core.tql.syntax import TQLError

FIXTURES = examples.load()["fixtures"]


def hierarchy(name, units):
    return {"name": name, "kind": "hierarchy", "units": units}


def markers(name, units):
    return {"name": name, "kind": "marker", "units": units}


# Verse 1 and verse are both the category verse; Chorus and chorus both chorus.
SONG = {
    "name": "song",
    "length": 100,
    "grammar": "de Clercq",
    "fields": {"title": "Song", "composer": "Mozart", "genre": ["rock", "pop"]},
    "timelines": [
        hierarchy(
            "Form (Ana)",
            [
                ["Verse 1", 1, 0, 10, "pink"],
                ["verse", 1, 10, 20, "#FFC0CB"],
                ["Chorus", 1, 20, 30, "red"],
                ["chorus", 1, 30, 40],
                ["A", 2, 0, 20],
                ["B", 2, 20, 40],
            ],
        ),
        markers("Cadences", [["PAC", 5], ["HC", 35], ["late", 95]]),
        {
            "name": "Layers",
            "kind": "range",
            "rows": ["solo"],
            "units": [["solo", "S", 2, 8]],
        },
        {
            "name": "Harmony",
            "kind": "harmony",
            "keys": [[0, "C", "major"], [20, "Eb", "major"]],
            "chords": [
                [0, "C", "major"],
                [10, "G", "dominant-seventh"],
                [12, "G", "dominant-seventh", 1],
                [20, "Eb", "major"],
            ],
        },
    ],
}
OTHER = {
    "name": "other",
    "length": 50,
    "fields": {"title": "Other", "composer": "Bach"},
    "timelines": [
        hierarchy("Form (Ben)", [["verse", 1, 0, 10], ["bridge", 1, 10, 20]])
    ],
}
BARE = {
    "name": "bare",
    "length": 50,
    "timelines": [hierarchy("Form (Cy)", [["verse", 1, 0, 10]])],
}
AUTHORS = {
    "name": "authors",
    "length": 10,
    "timelines": [
        hierarchy("Form (de Clercq)", [["verse", 1, 0, 10]]),
        hierarchy("Form (de Clercq, alt 2)", [["verse", 1, 0, 10]]),
        hierarchy("Form (Covach)", [["verse", 1, 0, 10]]),
    ],
}


def build(*fixtures):
    index = fixture_index.build_index(*(fixtures or (SONG,)))
    con = index.connection()
    # the user-set fields no fixture can hold yet
    con.execute(
        "UPDATE components SET comments = 'needs review' WHERE id = 'song:t1:c2'"
    )
    con.executemany(
        "INSERT INTO fields VALUES ('component', 'song:t1:c2', 'tags', ?)",
        [("draft",), ("hold",)],
    )
    return index


def run(text, *fixtures):
    return tql.run(build(*fixtures), text)


def units(text, *fixtures):
    """The first step's units of every match, as label@start, sorted."""
    got = run(text, *fixtures)
    return sorted(f"{c.label}@{c.start:g}" for m in got.matches for c in m.slots[0])


def starts(text, *fixtures):
    got = run(text, *fixtures)
    return sorted(c.start for m in got.matches for c in m.slots[0])


def error(text, *fixtures):
    with pytest.raises(TQLError) as info:
        run(text, *fixtures)
    return info.value


# --------------------------------------------------------------------------- #
# Label and parent are matched as a step
# --------------------------------------------------------------------------- #
class TestLabelAndParentAsStep:
    def test_a_bare_word_is_a_category(self):
        assert units("*[label = verse] IN form") == ["Verse 1@0", "verse@10"]

    def test_a_quoted_label_is_the_whole_label_with_its_case(self):
        assert units('*[label = "Verse 1"] IN form') == ["Verse 1@0"]
        assert units('*[label = "verse 1"] IN form') == []

    def test_not_equal_means_none_of_the_units(self):
        assert units("*[label != verse] IN form") == [
            "A@0",
            "B@20",
            "Chorus@20",
            "chorus@30",
        ]
        assert units("*[NOT label = verse] IN form") == units(
            "*[label != verse] IN form"
        )

    def test_a_regular_expression_searches_the_label(self):
        assert units("*[label = /^V/] IN form") == ["Verse 1@0"]
        assert units("*[label ~ /^V/] IN form") == ["Verse 1@0"]
        assert units("*[label ~ /(?i)^V/] IN form") == ["Verse 1@0", "verse@10"]
        assert units("*[label != /^V/] IN form") == [
            "A@0",
            "B@20",
            "Chorus@20",
            "chorus@30",
            "verse@10",
        ]

    def test_parent_is_matched_as_a_step(self):
        assert units("*[parent = A] IN form") == ["Verse 1@0", "verse@10"]
        assert units("*[parent = b] IN form") == ["Chorus@20", "chorus@30"]
        assert units('*[parent = "a"] IN form') == []
        assert units("*[parent = *] IN form") == [
            "Chorus@20",
            "Verse 1@0",
            "chorus@30",
            "verse@10",
        ]

    def test_a_unit_without_a_parent_has_none_of_them(self):
        assert units("*[parent != A] IN form") == [
            "A@0",
            "B@20",
            "Chorus@20",
            "chorus@30",
        ]

    def test_the_example_of_the_worked_table(self):
        got = run("continuation[parent = ST] IN form", FIXTURES["exposition"])
        assert [c.start for m in got.matches for c in m.slots[0]] == [14, 18]

    @pytest.mark.parametrize(
        "query, starts",
        [
            ("V7[label = V7] IN harmony", [1, 3, 9, 17]),
            ("*[label = V65] IN harmony", [3]),
            ("* IN harmony WHERE label = V7", [1, 3, 9, 17]),
            ("* IN keys WHERE $1.label = c", [8]),
            ("*[label = c] IN keys", [8]),
            ("*[label != V7] IN harmony", [0, 2, 4, 6, 7, 8, 10, 14, 16, 18]),
        ],
    )
    def test_a_label_in_a_chords_or_keys_lane_matches_as_the_step_would(
        self, query, starts
    ):
        got = run(query, FIXTURES["harmony"])
        assert [c.start for m in got.matches for c in m.slots[0]] == starts


# --------------------------------------------------------------------------- #
# The stored fields of a unit
# --------------------------------------------------------------------------- #
class TestUnitFields:
    def test_times_and_duration(self):
        assert starts("*[start >= 20] IN form") == [20, 20, 30]
        assert starts("*[end <= 10] IN form") == [0]
        assert starts("*[start = 10] IN form") == [10]
        assert starts("*[duration > 10] IN form") == [0, 20]
        assert starts("*[duration = 10] IN form") == [0, 10, 20, 30]
        assert starts("*[time = 5] IN markers") == [5]
        assert starts("*[time > 1:30] IN markers") == [95]

    def test_a_range_includes_both_ends(self):
        assert units("*[start = 10..20] IN form") == ["B@20", "Chorus@20", "verse@10"]
        assert units("*[start != 10..20] IN form") == [
            "A@0",
            "Verse 1@0",
            "chorus@30",
        ]

    def test_level_and_depth(self):
        assert units("*[level = 2] IN form") == ["A@0", "B@20"]
        assert units("*[depth = 1] IN form") == ["A@0", "B@20"]
        assert units("*[depth = 2] IN form") == [
            "Chorus@20",
            "Verse 1@0",
            "chorus@30",
            "verse@10",
        ]

    def test_not_holds_for_a_unit_without_the_field_too(self):
        assert units("*[NOT level = 1] IN markers") == ["HC@35", "PAC@5", "late@95"]
        assert units("*[level != 1] IN markers") == []

    def test_row_is_a_range_unit_s(self):
        assert units("*[row = solo] IN ranges") == ["S@2"]
        assert units("*[row = SOLO] IN ranges") == ["S@2"]
        assert units('*[row = "SOLO"] IN ranges') == []

    def test_colours_compare_as_colours(self):
        assert units("*[color = pink] IN form") == ["Verse 1@0", "verse@10"]
        assert units('*[color = "#FFC0CB"] IN form') == ["Verse 1@0", "verse@10"]
        assert units("*[color = red] IN form") == ["Chorus@20"]
        assert units("*[color != pink] IN form") == ["Chorus@20"]
        assert units("*[NOT color = pink] IN form") == [
            "A@0",
            "B@20",
            "Chorus@20",
            "chorus@30",
        ]
        assert units("*[color = *] IN form") == ["Chorus@20", "Verse 1@0", "verse@10"]
        assert units("*[color != *] IN form") == ["A@0", "B@20", "chorus@30"]

    def test_a_colour_can_be_searched_as_text(self):
        assert units("*[color ~ /^#ff/] IN form") == [
            "Chorus@20",
            "Verse 1@0",
            "verse@10",
        ]

    def test_comments(self):
        assert units("*[comments = *] IN form") == ["verse@10"]
        assert units("*[comments != *] IN form") != units("*[comments = *] IN form")
        assert units("*[comments ~ /review/] IN form") == ["verse@10"]
        assert units('*[comments = "needs review"] IN form') == ["verse@10"]
        assert units('*[comments = "Needs review"] IN form') == []

    def test_tags_are_several_values(self):
        assert units("*[tags = draft] IN form") == ["verse@10"]
        assert units("*[tags = hold] IN form") == ["verse@10"]
        assert units("*[tags = Draft] IN form") == ["verse@10"]
        assert units('*[tags = "Draft"] IN form') == []
        assert units("*[tags != draft] IN form") == [
            "A@0",
            "B@20",
            "Chorus@20",
            "Verse 1@0",
            "chorus@30",
        ]
        assert units("*[tags = *] IN form") == ["verse@10"]

    def test_chord_fields_as_stored(self):
        assert starts("*[inversion = 1] IN harmony") == [12]
        assert starts("*[applied_to = 0] IN harmony") == [0, 10, 12, 20]
        assert starts('*[quality = "dominant-seventh"] IN harmony') == [10, 12]
        assert starts('*[quality != "dominant-seventh"] IN harmony') == [0, 20]

    def test_key_fields_as_stored(self):
        got = run("* IN keys")
        keys = {c.start: c.label for m in got.matches for c in m.slots[0]}
        assert starts(f'*[key = "{keys[0]}"] IN keys') == [0]
        assert starts(f'*[key != "{keys[0]}"] IN keys') == [20]
        assert starts("*[mode = major] IN keys") == [0, 20]

    def test_a_field_a_unit_lacks_never_matches(self):
        assert units("*[inversion = 1] IN markers") == []
        assert units("*[row = solo] IN form") == []


class TestTimelineAndFileFields:
    def test_timeline_fields(self):
        assert units('*[tl.name = "Form (Ana)"] IN form') == units("* IN form")
        assert units("*[tl.author = Ana] IN form") == units("* IN form")
        assert units("*[tl.author = ana] IN form") == units("* IN form")
        assert units('*[tl.author = "ana"] IN form') == []
        assert units("*[tl.kind = hierarchy] IN form") == units("* IN form")
        assert units("*[tl.role = form] IN form") == units("* IN form")
        assert units("*[tl.ordinal = 1] IN form") == units("* IN form")
        assert units("*[tl.ordinal > 1] IN form") == []
        assert units('*[tl.id = "song:t1"] IN form') == units("* IN form")
        assert units("*[tl.name ~ /^Form/] IN form") == units("* IN form")
        assert units("*[NOT tl.role = form] IN form") == []

    def test_file_fields(self):
        assert units("*[file.composer = Mozart] IN form") == units("* IN form")
        assert units("*[file.composer = mozart] IN form") == units("* IN form")
        assert units('*[file.composer = "mozart"] IN form') == []
        assert units("*[file.id = song] IN form") == units("* IN form")
        assert units("*[file.title = Song] IN form") == units("* IN form")
        assert units("*[file.composer = Bach] IN form") == []

    def test_a_file_field_with_several_values_matches_any_of_them(self):
        assert units("*[file.genre = rock] IN form") == units("* IN form")
        assert units("*[file.genre = pop] IN form") == units("* IN form")
        assert units("*[file.genre != pop] IN form") == []
        assert units("*[file.genre != jazz] IN form") == units("* IN form")

    def test_across_files(self):
        got = run("verse IN form WHERE file.composer = Bach", SONG, OTHER)
        assert [r["file"] for r in got.rows] == ["other"]

    def test_author_is_matched_exactly(self):
        got = run('WHERE tl.author = "de Clercq"', AUTHORS)
        assert [r["timeline"] for r in got.rows] == ["Form (de Clercq)"]
        got = run("WHERE tl.author ~ /^de Clercq/", AUTHORS)
        assert [r["timeline"] for r in got.rows] == [
            "Form (de Clercq)",
            "Form (de Clercq, alt 2)",
        ]
        got = run('WHERE tl.author = "de clercq"', AUTHORS)
        assert got.rows == []
        got = run('WHERE author = "Covach"', AUTHORS)
        assert [r["timeline"] for r in got.rows] == ["Form (Covach)"]


# --------------------------------------------------------------------------- #
# SQL and Python give the same answer
# --------------------------------------------------------------------------- #
CONDITIONS = [
    "level = 2",
    "level != 2",
    "level < 2",
    "level >= 1",
    "depth = 1",
    "start >= 10",
    "end <= 20",
    "start != 20",
    "duration = 10",
    "duration != 10",
    "start = 10..20",
    "start != 10..20",
    "color = pink",
    "color != pink",
    "color = *",
    "color != *",
    'color = "#ff0000"',
    "NOT level = 2",
    "NOT color = pink",
    "NOT start = 10..20",
    "NOT color = *",
    "level = *",
    "level != *",
]


class TestSqlAndPythonAgree:
    @pytest.mark.parametrize("cond", CONDITIONS)
    def test_bracket_and_where(self, cond):
        in_brackets = units(f"*[{cond}] IN form")
        in_where = units(f"* IN form WHERE {cond}")
        assert in_brackets == in_where

    @pytest.mark.parametrize("cond", CONDITIONS)
    def test_markers_and_chords_without_the_field(self, cond):
        for lane in ("markers", "harmony"):
            assert units(f"*[{cond}] IN {lane}") == units(f"* IN {lane} WHERE {cond}")

    def test_a_simple_comparison_is_in_the_sql_with_its_value_bound(self):
        got = run("*[level = 2] IN form")
        assert "hierarchies" in got.sql and "level" in got.sql
        text = tql_compile.candidate_statement(
            tql.parse("*[level = 2] IN form").pattern.seq.steps[0].item, "song"
        )
        assert "level" not in text[0].split("?")[-1]
        assert 2.0 in text[1]

    def test_run_writes_nothing(self):
        index = build()
        con = index.connection()
        before = (
            con.total_changes,
            con.execute("SELECT count(*) FROM sqlite_master").fetchone(),
        )
        tql.run(index, "*[level = 2 AND color = *] IN form")
        tql.run(index, "WHERE file.composer = Mozart")
        tql.run(index, "verse THEN chorus IN form WHERE $1.color = pink")
        after = (
            con.total_changes,
            con.execute("SELECT count(*) FROM sqlite_master").fetchone(),
        )
        temp = con.execute("SELECT count(*) FROM sqlite_temp_master").fetchone()
        assert before == after and temp == (0,)


class TestAnd:
    def test_conditions_join_with_and(self):
        assert units("*[level = 1 AND color = pink] IN form") == [
            "Verse 1@0",
            "verse@10",
        ]
        assert units("*[level = 1 AND start >= 10 AND color = pink] IN form") == [
            "verse@10"
        ]
        assert units("*[level = 1 AND tags = draft AND start = 10] IN form") == [
            "verse@10"
        ]


# --------------------------------------------------------------------------- #
# Value forms
# --------------------------------------------------------------------------- #
class TestValues:
    def test_a_regular_expression_is_case_sensitive(self):
        assert units("*[comments ~ /Review/] IN form") == []
        assert units("*[comments ~ /(?i)Review/] IN form") == ["verse@10"]

    def test_a_bare_word_after_a_tilde_is_a_pattern(self):
        assert units("*[comments ~ rev] IN form") == ["verse@10"]

    def test_the_number_of_a_numeric_field_is_checked(self):
        text = "*[start > soon] IN form"
        err = error(text)
        assert "is a number" in err.msg and err.pos == text.index("soon")


# --------------------------------------------------------------------------- #
# WHERE
# --------------------------------------------------------------------------- #
class TestWhereOneUnit:
    def test_a_bare_name_is_the_unit_s(self):
        assert units("* IN form WHERE level = 2") == ["A@0", "B@20"]
        assert units("* IN form WHERE NOT level = 2") == [
            "Chorus@20",
            "Verse 1@0",
            "chorus@30",
            "verse@10",
        ]
        assert units("* IN form WHERE label = verse") == ["Verse 1@0", "verse@10"]

    def test_a_bare_name_is_the_timeline_s_or_the_file_s(self):
        assert units("* IN form WHERE author = Ana") == units("* IN form")
        assert units("* IN form WHERE author = Ben") == []
        assert units("* IN form WHERE composer = Mozart") == units("* IN form")
        assert units("* IN form WHERE kind = hierarchy") == units("* IN form")
        assert units("* IN form WHERE NOT composer = Mozart") == []

    def test_a_prefix_names_the_scope(self):
        assert units("* IN form WHERE tl.name ~ /Ana/ AND file.composer = Mozart") == (
            units("* IN form")
        )

    def test_a_unit_s_own_name_is_the_relation_s_left_unit(self):
        got = run("PAC IN cadences DURING * IN form WHERE time = 5")
        assert [(c.label, c.start) for m in got.matches for c in m.slots[1]] == [
            ("Verse 1", 0),
            ("A", 0),
        ]
        assert run("PAC IN cadences DURING * IN form WHERE time = 6").matches == []

    def test_every_condition_must_hold(self):
        assert units("* IN form WHERE level = 1 AND start >= 20") == [
            "Chorus@20",
            "chorus@30",
        ]


class TestWhereSequences:
    def test_n_holds_when_any_unit_the_step_took_does(self):
        text = "verse+ IN form WHERE $1.label = "
        assert len(run(text + '"Verse 1"').matches) == 1
        assert len(run(text + '"verse"').matches) == 1
        assert len(run(text + "chorus").matches) == 0
        assert len(run("verse+ IN form WHERE $1.start = 10").matches) == 1
        assert len(run("verse+ IN form WHERE $1.start = 5").matches) == 0

    def test_not_equal_holds_when_none_does(self):
        text = "verse+ IN form WHERE $1.label != "
        assert len(run(text + '"Verse 1"').matches) == 0
        assert len(run(text + chr(34) + "verse" + chr(34)).matches) == 0
        assert len(run(text + "chorus").matches) == 1
        assert len(run("verse+ IN form WHERE $1.start != 10").matches) == 0
        assert len(run("verse+ IN form WHERE $1.start != 5").matches) == 1

    def test_a_quoted_label_keeps_its_case(self):
        assert (
            len(run('verse THEN chorus IN form WHERE $2.label = "Chorus"').matches) == 1
        )
        assert (
            len(run('verse THEN chorus IN form WHERE $2.label = "chorus"').matches) == 0
        )
        assert (
            len(run("verse THEN chorus IN form WHERE $2.label = chorus").matches) == 1
        )

    def test_zero_is_any_unit_of_the_match(self):
        base = "verse THEN chorus IN form WHERE "
        assert len(run(base + "$0.color = red").matches) == 1
        assert len(run(base + "$0.color = pink").matches) == 1
        assert len(run(base + "$0.color = blue").matches) == 0
        assert len(run(base + "$0.color != blue").matches) == 1
        assert len(run(base + "$0.color != red").matches) == 0
        assert len(run(base + "$1.color = red").matches) == 0
        assert len(run(base + "$2.color = red").matches) == 1

    def test_two_units_fields_compare_ignoring_case(self):
        got = run("chorus THEN chorus IN form WHERE $1.label = $2.label")
        assert len(got.matches) == 1
        got = run("chorus THEN chorus IN form WHERE $1.label != $2.label")
        assert len(got.matches) == 0
        got = run("verse THEN chorus IN form WHERE $1.label != $2.label")
        assert len(got.matches) == 1
        got = run("verse THEN chorus IN form WHERE $1.start < $2.start")
        assert len(got.matches) == 1
        got = run("verse THEN chorus IN form WHERE $1.start >= $2.start")
        assert len(got.matches) == 0

    def test_a_bare_name_is_a_timeline_s_or_a_file_s(self):
        base = "verse THEN chorus IN form WHERE "
        assert len(run(base + "composer = Mozart").matches) == 1
        assert len(run(base + "author = Ana").matches) == 1
        assert len(run(base + 'tl.name = "Form (Ana)"').matches) == 1
        assert len(run(base + "author = Ben").matches) == 0

    def test_a_step_that_took_nothing_never_matches(self):
        got = run("verse THEN intro? IN form WHERE $2.label = x")
        assert got.matches == []

    def test_the_timeline_of_a_step(self):
        got = run('verse THEN chorus IN form WHERE $2.tl.name = "Form (Ana)"')
        assert len(got.matches) == 1


class TestCaptures:
    def test_the_groups_of_a_tilde_are_kept_on_the_match(self):
        got = run(r"* IN form WHERE label ~ /^(\w+) (\d)$/")
        assert [m.captures for m in got.matches] == [("Verse", "1")]

    def test_a_timeline_name_is_captured(self):
        got = run(r"* IN form WHERE tl.name ~ /^Form \((.+)\)$/")
        assert {m.captures for m in got.matches} == {("Ana",)}

    def test_a_match_without_a_tilde_has_none(self):
        got = run("* IN form WHERE level = 2")
        assert all(m.captures == () for m in got.matches)

    def test_a_group_that_did_not_take_part_is_empty(self):
        got = run(r"* IN form WHERE label ~ /^(x)?(Verse)/")
        assert [m.captures for m in got.matches] == [("", "Verse")]


# --------------------------------------------------------------------------- #
# A query of only WHERE
# --------------------------------------------------------------------------- #
class TestWhereOnly:
    def test_timelines_when_it_names_timeline_fields(self):
        got = run("WHERE tl.name ~ /^Form/", SONG, OTHER)
        assert got.grain == "timeline"
        assert got.rows == [
            {
                "file": "other",
                "title": "Other",
                "timeline": "Form (Ben)",
                "kind": "hierarchy",
                "role": "form",
                "author": "Ben",
            },
            {
                "file": "song",
                "title": "Song",
                "timeline": "Form (Ana)",
                "kind": "hierarchy",
                "role": "form",
                "author": "Ana",
            },
        ]
        assert all(m.slots == [] for m in got.matches)
        assert [m.file_id for m in got.matches] == ["other", "song"]

    def test_a_bare_timeline_field_lists_timelines(self):
        got = run("WHERE author = Ana", SONG, OTHER)
        assert got.grain == "timeline"
        assert [r["timeline"] for r in got.rows] == ["Form (Ana)"]
        got = run("WHERE role = harmony", SONG, OTHER)
        assert [r["timeline"] for r in got.rows] == ["Harmony"]
        assert got.rows[0]["author"] is None

    def test_a_timeline_row_may_also_ask_about_its_file(self):
        got = run("WHERE tl.kind = hierarchy AND file.composer = Bach", SONG, OTHER)
        assert [r["timeline"] for r in got.rows] == ["Form (Ben)"]

    def test_files_when_it_names_only_file_fields(self):
        got = run("WHERE file.composer = Mozart", SONG, OTHER)
        assert got.grain == "file"
        assert got.rows == [{"file": "song", "title": "Song", "composer": "Mozart"}]
        assert all(m.slots == [] for m in got.matches)
        assert [m.key for m in got.matches] == ["song|file"]

    def test_a_bare_file_field_lists_files(self):
        got = run("WHERE composer = Bach", SONG, OTHER)
        assert got.grain == "file"
        assert got.rows == [{"file": "other", "title": "Other", "composer": "Bach"}]

    def test_a_column_for_each_file_field_it_names(self):
        got = run("WHERE file.genre = rock AND file.composer = Mozart", SONG, OTHER)
        assert got.rows == [
            {
                "file": "song",
                "title": "Song",
                "genre": "rock, pop",
                "composer": "Mozart",
            }
        ]
        got = run("WHERE NOT file.genre = rock", SONG, OTHER)
        assert got.rows == [{"file": "other", "title": "Other", "genre": None}]

    def test_a_file_field_with_a_pattern(self):
        got = run(r"WHERE file.composer ~ /^(M)/", SONG, OTHER)
        assert [r["file"] for r in got.rows] == ["song"]
        assert got.matches[0].captures == ("M",)

    def test_units_otherwise(self):
        got = run("WHERE level = 2", SONG, OTHER)
        assert got.grain == "match"
        assert [(r["file"], r["label"], r["lane"]) for r in got.rows] == [
            ("song", "A", "level 2"),
            ("song", "B", "level 2"),
        ]
        assert set(got.rows[0]) >= {"file", "title", "timeline", "lane", "ids", "label"}
        assert [len(m.slots) for m in got.matches] == [1, 1]

    def test_units_come_from_every_lane_with_labels(self):
        got = run("WHERE start <= 5")
        assert sorted(r["label"] for r in got.rows) == ["A", "PAC", "S", "Verse 1"]
        assert {r["timeline"] for r in got.rows} == {"Form (Ana)", "Cadences", "Layers"}
        got = run("WHERE start = 5")
        assert [r["label"] for r in got.rows] == ["PAC"]

    def test_a_unit_is_listed_once(self):
        got = run("WHERE label = verse")
        assert [r["start"] for r in got.rows] == [0, 10]

    def test_chords_and_keys_when_it_asks_about_harmony(self):
        got = run("WHERE inversion = 1")
        assert [(r["timeline"], r["start"]) for r in got.rows] == [("Harmony", 12)]
        got = run("WHERE tl.kind = harmony AND inversion = 0")
        assert [r["start"] for r in got.rows] == [0, 10, 20]
        assert not run("WHERE level = 1").rows == [] and all(
            r["timeline"] != "Harmony" for r in run("WHERE level = 1").rows
        )

    def test_max_matches(self):
        got = run("WHERE tl.name ~ /./", SONG, OTHER)
        assert len(got.rows) == 5
        got = tql.run(build(SONG, OTHER), "WHERE tl.name ~ /./", max_matches=2)
        assert len(got.rows) == 2 and got.stopped == "max_matches"


# --------------------------------------------------------------------------- #
# Warnings
# --------------------------------------------------------------------------- #
class TestWarnings:
    def test_a_file_without_the_field_could_not_answer(self):
        got = run("* IN form WHERE composer = Mozart", SONG, OTHER, BARE)
        assert got.warnings == [
            "1 file without the file field 'composer' could not answer"
        ]
        got = run("WHERE file.composer = Mozart", SONG, OTHER, BARE, AUTHORS)
        assert got.warnings == [
            "2 files without the file field 'composer' could not answer"
        ]

    def test_no_warning_when_every_file_has_it(self):
        assert run("* IN form WHERE composer = Mozart", SONG, OTHER).warnings == []
        assert run("*[level = 1] IN form", SONG, OTHER, BARE).warnings == []


# --------------------------------------------------------------------------- #
# Names the corpus does not have
# --------------------------------------------------------------------------- #
class TestUnknownNames:
    def test_an_unknown_field_in_where(self):
        text = "* IN form WHERE colour = pink"
        err = error(text)
        assert "unknown field 'colour'" in err.msg
        assert err.pos == text.index("colour")
        assert err.end == err.pos + len("colour")

    def test_an_unknown_field_in_brackets(self):
        text = "*[colour = pink] IN form"
        err = error(text)
        assert "'colour' is not a property of a unit" in err.msg
        assert err.pos == text.index("colour")

    def test_a_timeline_field_in_brackets_needs_its_prefix(self):
        err = error("*[name = x] IN form")
        assert "write tl.name" in err.msg
        err = error("*[composer = x] IN form")
        assert "write file.composer" in err.msg

    def test_unknown_prefixed_fields(self):
        text = "* IN form WHERE tl.nope = 1"
        err = error(text)
        assert "unknown timeline field 'nope'" in err.msg and "known:" in err.msg
        assert err.pos == text.index("tl.nope")
        text = "*[file.nope = 1] IN form"
        err = error(text)
        assert "unknown file field 'nope'" in err.msg and "composer" in err.msg
        assert err.pos == text.index("file.nope")

    def test_a_file_field_no_file_has_is_unknown_but_id_and_title_are_not(self):
        assert error("* IN form WHERE file.year = 1")
        assert units("* IN form WHERE file.title = Song")
        assert units("* IN form WHERE file.id = song")

    def test_a_field_of_a_numbered_unit(self):
        text = "verse THEN chorus IN form WHERE $1.colour = pink"
        err = error(text)
        assert "'colour' is not a property of a unit" in err.msg
        assert err.pos == text.index("$1.colour")

    def test_the_right_side_of_a_comparison_is_checked_too(self):
        text = "verse THEN chorus IN form WHERE $1.label = $2.nope"
        err = error(text)
        assert err.pos == text.index("$2.nope")

    def test_analyst_is_called_author(self):
        text = "* IN form WHERE analyst = Ana"
        err = error(text)
        assert "TQL calls it author" in err.msg and err.pos == text.index("analyst")
        err = error("* IN form WHERE tl.analyst = Ana")
        assert "TQL calls it author" in err.msg
        err = error("*[analyst = Ana] IN form")
        assert "TQL calls it author" in err.msg

    def test_the_error_is_raised_before_any_result(self):
        err = error("WHERE colour = pink", SONG, OTHER)
        assert "unknown field" in err.msg

    def test_an_unknown_lane(self):
        text = "verse IN nowhere"
        err = error(text)
        assert "no timeline, role or kind called 'nowhere'" in err.msg
        assert "roles:" in err.msg and "kinds:" in err.msg
        assert err.pos == text.index("nowhere")

    def test_an_unknown_quoted_lane(self):
        text = 'verse IN "Nowhere (*)"'
        err = error(text)
        assert err.pos == text.index('"Nowhere')
        assert err.end == err.pos + len('"Nowhere (*)"')

    def test_a_quoted_lane_keeps_its_case(self):
        err = error('verse IN "form (ana)"')
        assert 'a quoted name keeps its case: "Form (Ana)"' in err.msg

    def test_an_unknown_lane_after_a_relation(self):
        text = "verse IN form DURING * IN nowhere"
        assert error(text).pos == text.index("nowhere")
        text = "verse[DURING * IN nowhere] IN form"
        assert error(text).pos == text.index("nowhere")

    def test_the_lanes_the_corpus_has_are_known(self):
        for lane in (
            "form",
            "cadence",
            "cadences",
            "markers",
            "marker",
            "ranges",
            "hierarchies",
            "harmony",
            "keys",
            "chords",
            "beats",
            "solo",
            "SOLO",
            '"Form (*)"',
            '"Form (Ana)"',
            "layers",
            '"solo"',
        ):
            run(f"* IN {lane}")
        run("* IN bars")


class TestAmbiguousNames:
    def test_a_name_on_two_scopes_needs_a_prefix(self):
        text = "* IN form WHERE id = x"
        err = error(text)
        assert "more than one level" in err.msg
        assert "tl.id or file.id" in err.msg
        assert err.pos == text.index("id")

    def test_in_a_sequence_a_unit_s_field_needs_a_number(self):
        text = "verse THEN chorus IN form WHERE label = x"
        err = error(text)
        assert "in a sequence, 'label' is ambiguous" in err.msg
        assert "$1.label" in err.msg
        assert err.pos == text.index("label = x")

    def test_in_a_sequence_a_prefix_or_a_number_does_it(self):
        assert run("verse THEN chorus IN form WHERE tl.id = x").matches == []
        assert run("verse THEN chorus IN form WHERE $1.label = verse").matches

    def test_in_where_alone_a_shared_name_is_ambiguous_too(self):
        err = error("WHERE id = x")
        assert "more than one level" in err.msg

    def test_a_unit_name_found_on_a_file_too_is_ambiguous(self):
        with pytest.raises(TQLError, match="more than one level"):
            run(
                "* IN form WHERE start = 1",
                {
                    **SONG,
                    "fields": {"start": "x"},
                },
            )

    def test_a_name_only_the_file_has_is_the_file_s(self):
        assert units("* IN form WHERE genre = rock") == units("* IN form")


class TestOnlyWhereAsParsed:
    def test_the_parsed_query_runs_like_its_text(self):
        query = tql.parse("* IN form WHERE level = 2")
        index = build()
        assert [m.key for m in tql.run(index, query).matches] == [
            m.key for m in tql.run(index, "* IN form WHERE level = 2").matches
        ]
