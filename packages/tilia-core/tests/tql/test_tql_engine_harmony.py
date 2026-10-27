"""Chords and keys in the engine (tql.md §5, §7.2): a literal in a chords lane is
a chord, in a keys lane a key; the chord and key fields compare as music."""

import gc
import sqlite3
import weakref

import examples
import fixture_index
import pytest

from tilia_core import tql

FIXTURES = examples.load()["fixtures"]
HARMONY = FIXTURES["harmony"]


def harmony_fixture(keys, chords, length=10):
    return {
        "length": length,
        "timelines": [
            {"name": "Harmony", "kind": "harmony", "keys": keys, "chords": chords}
        ],
    }


# C major, then G minor. The chords: V65, I, V/V and V in C; V in G minor.
PROTOTYPE = harmony_fixture(
    [[0, "C", "major"], [3, "G", "minor"]],
    [
        [0.5, "G", "dominant-seventh", 1],
        [1.0, "C", "major"],
        [1.5, "D", "major", 0, 4],
        [2.0, "G", "major"],
        [3.5, "D", "major"],
    ],
    length=5,
)


def run(fix, text):
    return tql.run(fixture_index.build_index(fix), text)


def labels(fix, text):
    """Each match's units by name: a chord by its Roman numeral, as the
    prototype's checks print it (its label is its symbol), a key by its label."""
    index = fixture_index.build_index(fix)
    con = index.connection()

    def name(c):
        if c.kind != "chord":
            return c.label
        sql = "SELECT roman FROM chords WHERE component_id = ?"
        return con.execute(sql, (c.id,)).fetchone()[0]

    got = tql.run(index, text).matches
    return [tuple(name(c) for s in m.slots for c in s) for m in got]


def starts(fix, text):
    return [c.start for m in run(fix, text).matches for s in m.slots for c in s]


class TestPrototypeChecks:
    def test_inversion_figure_then_tonic(self):
        assert labels(PROTOTYPE, "V65 THEN I IN harmony") == [("V65", "I")]

    def test_seventh_takes_any_inversion(self):
        assert labels(PROTOTYPE, "V7 THEN I IN harmony") == [("V65", "I")]

    def test_a_condition_on_the_inversion(self):
        assert labels(PROTOTYPE, "V7[inversion = 0] IN harmony") == []
        assert labels(PROTOTYPE, "V7[inversion = 1] IN harmony") == [("V65",)]

    def test_symbol_with_a_bass(self):
        assert labels(PROTOTYPE, "G7/B IN harmony") == [("V65",)]

    def test_applied_chord(self):
        assert labels(PROTOTYPE, "V/V THEN V IN harmony") == [("V/V", "V")]

    def test_numeral_is_read_in_the_key_in_force(self):
        assert labels(PROTOTYPE, "V IN harmony") == [("V",), ("V",)]
        assert starts(PROTOTYPE, "V IN harmony") == [2.0, 3.5]
        assert labels(PROTOTYPE, 'V IN harmony WHERE key = "g"') == [("V",)]
        assert starts(PROTOTYPE, 'V IN harmony WHERE key = "g"') == [3.5]

    def test_keys(self):
        assert labels(PROTOTYPE, '* IN keys WHERE key = "g"') == [("g",)]
        assert labels(PROTOTYPE, "g IN keys") == [("g",)]
        assert labels(PROTOTYPE, "G IN keys") == []

    def test_roman_field(self):
        assert labels(PROTOTYPE, '* IN harmony WHERE roman = "V/V"') == [("V/V",)]


class TestChordLiterals:
    def test_symbols_are_absolute(self):
        assert starts(HARMONY, "G7 IN harmony") == [1, 3, 9]

    def test_a_seventh_takes_every_inversion(self):
        assert starts(HARMONY, "V7 IN harmony") == [1, 3, 9, 17]

    def test_a_figure_names_one_inversion(self):
        assert starts(HARMONY, "V65 IN harmony") == [3]

    def test_qualities_are_exact(self):
        assert starts(HARMONY, "V IN harmony") == [6, 14]

    def test_case_matters(self):
        assert starts(HARMONY, "i IN harmony") == [8]
        assert starts(HARMONY, "I IN harmony") == [0, 2, 4, 7, 10, 16, 18]

    def test_a_chord_before_any_key_is_read_in_c_major(self):
        fix = harmony_fixture(
            [[5, "G", "major"]], [[0, "C", "major"], [6, "D", "major"]]
        )
        assert starts(fix, "I IN harmony") == [0]
        assert starts(fix, "V IN harmony") == [6]

    def test_quoted_augmented_triad(self):
        fix = harmony_fixture(
            [[0, "C", "major"]], [[0, "C", "major"], [1, "E", "augmented"]]
        )
        assert starts(fix, '"III+" IN harmony') == [1]
        assert starts(fix, "IIIaug IN harmony") == [1]

    def test_a_regular_expression_searches_the_names(self):
        assert starts(HARMONY, "/^V7$/ IN harmony") == [1, 9, 17]
        assert starts(HARMONY, "/^G7/ IN harmony") == [1, 3, 9]
        assert starts(HARMONY, "/^Bb7$/ IN harmony") == [17]

    def test_a_regular_expression_never_searches_the_key(self):
        # #104 R3: a regular expression in a chords lane searches the chord's
        # label only; the V7 of C major at 1 and the Bb7 of E-flat major at 17
        # are not found by their key
        assert starts(HARMONY, "/^C$/ IN harmony") == [0, 2, 4, 7, 10]
        assert starts(HARMONY, "/^Eb$/ IN harmony") == [16, 18]
        assert starts(HARMONY, "/^Eb$/ IN keys") == [16]

    def test_a_regular_expression_searches_custom_text(self):
        index = fixture_index.build_index(HARMONY)
        con = index.connection()
        con.execute(
            "UPDATE chords SET custom_text = 'N.C.' WHERE component_id LIKE '%c2'"
        )
        got = tql.run(index, "/N\\.C/ IN harmony")
        assert [c.start for m in got.matches for c in m.slots[0]] == [1]

    def test_an_exact_literal_that_is_no_chord_matches_custom_text(self):
        index = fixture_index.build_index(HARMONY)
        con = index.connection()
        con.execute(
            "UPDATE chords SET custom_text = 'N.C.' WHERE component_id LIKE '%c2'"
        )
        got = tql.run(index, '"N.C." IN harmony')
        assert [c.start for m in got.matches for c in m.slots[0]] == [1]

    def test_a_label_wildcard_still_takes_any_chord(self):
        assert len(run(HARMONY, "* IN harmony").matches) == 14
        # [label = *] is allowed on chords and keys, unlike [label = V7]
        assert len(run(HARMONY, "*[label = *] IN harmony").matches) == 14
        assert len(run(HARMONY, "*[label = *] IN keys").matches) == 3


class TestKeyLiterals:
    def test_lower_case_is_minor(self):
        assert starts(HARMONY, "c IN keys") == [8]

    def test_upper_case_is_major(self):
        assert starts(HARMONY, "C IN keys") == [0]
        assert starts(HARMONY, "Eb IN keys") == [16]

    def test_a_key_in_a_sequence(self):
        assert starts(HARMONY, "C THEN c IN keys") == [0, 8]


class TestWarnings:
    def test_a_word_that_is_no_chord_warns_and_matches_nothing(self):
        got = run(HARMONY, "Xyz IN harmony")
        assert got.matches == []
        assert any("'Xyz' is not a chord" in w for w in got.warnings)

    def test_a_word_that_is_no_key_warns(self):
        got = run(HARMONY, "Xyz IN keys")
        assert got.matches == []
        assert any("'Xyz' is not a key" in w for w in got.warnings)

    def test_a_good_query_does_not_warn(self):
        assert run(HARMONY, "V7 IN harmony").warnings == []

    def test_a_regular_expression_beside_another_literal_warns(self):
        message = "a regular expression in a harmony lane must stand alone"
        for text in ("V7//x/ IN harmony", "/x//y IN harmony", "/x//y IN keys"):
            got = run(HARMONY, text)
            assert got.matches == [], text
            assert got.warnings == [message], text

    def test_warnings_do_not_carry_over_between_runs(self):
        index = fixture_index.build_index(HARMONY)
        assert tql.run(index, "Xyz IN harmony").warnings
        assert tql.run(index, "V7 IN harmony").warnings == []

    def test_a_label_over_other_lanes_does_not_warn(self):
        assert run(FIXTURES["sonata"], "Xyz IN form").warnings == []

    def test_a_lane_of_both_kinds_warns_only_for_a_literal_that_is_neither(self):
        # IN "Harmony" names the chords and the keys: a good chord is no key,
        # and a good key no chord, and neither warns
        got = run(HARMONY, 'V IN "Harmony"')
        assert starts(HARMONY, 'V IN "Harmony"') == [6, 14]
        assert got.warnings == []
        assert run(HARMONY, 'c IN "Harmony"').warnings == []
        got = run(HARMONY, 'Xyz IN "Harmony"')
        assert got.matches == []
        assert len(got.warnings) == 2
        assert any("'Xyz' is not a chord" in w for w in got.warnings)
        assert any("'Xyz' is not a key" in w for w in got.warnings)

    def test_an_exact_literal_that_matches_custom_text_does_not_warn(self):
        assert any("'N.C.' is not a chord" in w for w in run(HARMONY, '"N.C." IN harmony').warnings)
        index = fixture_index.build_index(HARMONY)
        con = index.connection()
        con.execute(
            "UPDATE chords SET custom_text = 'N.C.' WHERE component_id LIKE '%c2'"
        )
        got = tql.run(index, '"N.C." IN harmony')
        assert [c.start for m in got.matches for c in m.slots[0]] == [1]
        assert got.warnings == []

    def test_a_warning_names_the_literal_once(self):
        assert run(HARMONY, "Xyz IN keys").warnings == [
            "'Xyz' is not a key: write C (major), c (minor), Eb, f#"
        ]

    def test_the_warnings_pass_resolves_no_lane_it_cannot_warn_on(self, monkeypatch):
        # the search resolves the lanes of every file once; the warnings pass
        # must not do it again for a query whose literals are all chords or
        # keys, and once per lane and file, not per unit, for one that can warn
        from tilia_core.tql import compile as tql_compile

        index = fixture_index.build_index(HARMONY)
        calls = [0]
        resolve = tql_compile.resolve_lanes

        def counted(*args, **kwargs):
            calls[0] += 1
            return resolve(*args, **kwargs)

        monkeypatch.setattr(tql_compile, "resolve_lanes", counted)

        def count(text):
            calls[0] = 0
            tql.run(index, text)
            return calls[0]

        assert count("phrase THEN phrase THEN phrase IN form") == count("phrase IN form")
        assert count("V7 THEN I THEN V7 IN harmony") == count("V7 IN harmony")
        assert count("Xyz THEN Xyz THEN Xyz IN harmony") == count("Xyz IN harmony")


class TestSql:
    def test_chord_matching_is_in_the_sql(self):
        got = run(HARMONY, "V7 IN harmony")
        assert "tql_chord('V7'," in got.sql

    def test_key_matching_is_in_the_sql(self):
        assert "tql_key('c'," in run(HARMONY, "c IN keys").sql

    def test_run_writes_nothing(self):
        index = fixture_index.build_index(HARMONY)
        con = index.connection()
        before = con.total_changes
        tql.run(index, "V7 THEN I IN harmony")
        assert con.total_changes == before

    def test_a_dropped_connection_is_freed(self):
        # SQLite's references to the functions are hidden from the garbage
        # collector, so a function that held the connection would keep it open.
        class Connection(sqlite3.Connection):  # sqlite3's own takes no weakref
            pass

        con = sqlite3.connect(":memory:", factory=Connection)
        fixture_index.build_index(HARMONY).connection().backup(con)
        index = fixture_index.FixtureIndex(con, {})
        assert tql.run(index, "V7 IN harmony").matches
        tql.run(index, "c IN keys")
        freed = weakref.ref(con)
        del index, con
        gc.collect()
        assert freed() is None


class TestMixedLanes:
    def test_labelled_units_keep_label_matching(self):
        got = run(HARMONY, "phrase")
        assert [c.start for m in got.matches for c in m.slots[0]] == [0, 8, 16]

    def test_a_lane_of_both_kinds(self):
        fix = {
            "length": 10,
            "timelines": [
                {
                    "name": "Harmony",
                    "kind": "harmony",
                    "keys": [[0, "C", "major"]],
                    "chords": [[0, "C", "major"], [4, "G", "major"]],
                },
                {"name": "Cadences", "kind": "marker", "units": [["V", 4]]},
            ],
        }
        got = run(fix, "V IN harmony")
        assert [c.start for m in got.matches for c in m.slots[0]] == [4]
        got = run(fix, "V")
        assert [c.kind for m in got.matches for c in m.slots[0]] == ["marker"]


class TestRelationsAndBrackets:
    def test_a_chord_in_a_relation_target(self):
        got = run(HARMONY, "phrase IN form CONTAINS G7 IN harmony")
        assert sorted({c.start for m in got.matches for c in m.slots[0]}) == [0, 8]

    def test_a_chord_in_the_brackets_of_a_phrase(self):
        got = run(HARMONY, "phrase[ENDS WITH I IN harmony] IN form")
        assert [c.start for m in got.matches for c in m.slots[0]] == [0, 16]

    def test_a_key_condition_on_chords_in_brackets(self):
        assert starts(HARMONY, '*[key = "Eb"] IN harmony') == [16, 17, 18]
        assert starts(HARMONY, '*[key = "Eb"] IN keys') == [16]

    def test_a_label_condition_on_chords_says_what_to_write_instead(self):
        for text in ("*[label = V7] IN harmony", "* IN harmony WHERE label = V7"):
            with pytest.raises(NotImplementedError, match="write the chord as a step"):
                run(HARMONY, text)


class TestFieldsAsMusic:
    def test_one_key_written_three_ways(self):
        for written in ('"Cm"', '"C minor"', '"c"', "c"):
            assert starts(HARMONY, f"* IN keys WHERE key = {written}") == [8], written

    def test_a_key_in_brackets(self):
        assert starts(HARMONY, '*[key = "Cm"] IN keys') == [8]
        assert starts(HARMONY, '*[key = "C minor"] IN keys') == [8]

    def test_chords_in_a_key(self):
        assert starts(HARMONY, '* IN harmony WHERE key = "Cm"') == [8, 9, 10, 14]
        assert starts(HARMONY, '* IN harmony WHERE key != "Cm"') == [
            0,
            1,
            2,
            3,
            4,
            6,
            7,
            16,
            17,
            18,
        ]

    def test_the_key_of_all_the_chords(self):
        assert starts(HARMONY, '* IN harmony WHERE key = "Eb"') == [16, 17, 18]

    def test_keys_keep_case(self):
        assert starts(HARMONY, '* IN keys WHERE key = "C"') == [0]
        assert starts(HARMONY, "* IN keys WHERE key = C") == [0]

    def test_tonic_and_mode(self):
        assert starts(HARMONY, "* IN keys WHERE mode = minor") == [8]
        assert starts(HARMONY, "* IN keys WHERE tonic = Eb") == [16]

    def test_chord_fields(self):
        assert starts(HARMONY, "* IN harmony WHERE root = Bb") == [17]
        assert starts(HARMONY, "* IN harmony WHERE quality = minor") == [8]
        assert starts(HARMONY, "* IN harmony WHERE symbol = G7") == [1, 9]
        assert starts(HARMONY, '* IN harmony WHERE symbol = "G7/B"') == [3]
        assert starts(HARMONY, "* IN harmony WHERE roman = V7") == [1, 9, 17]

    def test_applied_to(self):
        assert starts(PROTOTYPE, "* IN harmony WHERE applied_to = 4") == [1.5]
        assert starts(PROTOTYPE, "*[applied_to = 4] IN harmony") == [1.5]

    def test_a_numeral_is_one_numeral_however_written(self):
        fix = harmony_fixture(
            [[0, "C", "major"]],
            [[0, "C", "major"], [1, "B", "diminished-seventh"]],
        )
        for written in ('"vii°7"', '"viio7"'):
            assert starts(fix, f"* IN harmony WHERE roman = {written}") == [1], written
        assert starts(fix, '* IN harmony WHERE roman != "viio7"') == [0]

    def test_text_that_does_not_parse_compares_as_text(self):
        assert starts(HARMONY, '* IN harmony WHERE roman = "zzz"') == []
        assert starts(HARMONY, '* IN harmony WHERE roman != "zzz"') == [
            c.start for m in run(HARMONY, "* IN harmony").matches for c in m.slots[0]
        ]

    def test_a_regular_expression_on_a_field(self):
        assert starts(HARMONY, "* IN harmony WHERE symbol ~ /^Bb/") == [17]

    def test_two_units_compare_as_music(self):
        got = run(HARMONY, "* THEN * IN keys WHERE $1.key != $2.key")
        assert len(got.matches) == 2
        # one key spelled two ways: the index never writes "Cm", so put it there
        fix = harmony_fixture([[0, "C", "minor"], [5, "C", "minor"]], [])
        index = fixture_index.build_index(fix)
        con = index.connection()
        con.execute("UPDATE keys SET key = 'Cm' WHERE component_id LIKE '%k2'")
        assert [r[0] for r in con.execute("SELECT key FROM keys")] == ["c", "Cm"]
        assert len(tql.run(index, "* THEN * IN keys WHERE $1.key = $2.key").matches) == 1
        assert tql.run(index, "* THEN * IN keys WHERE $1.key != $2.key").matches == []
