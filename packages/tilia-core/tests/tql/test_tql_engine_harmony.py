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
            "UPDATE chords SET custom_text = 'N.C.' WHERE component_id = "
            "(SELECT id FROM components WHERE uuid LIKE '%c2')"
        )
        got = tql.run(index, "/N\\.C/ IN harmony")
        assert [c.start for m in got.matches for c in m.slots[0]] == [1]

    def test_an_exact_literal_that_is_no_chord_matches_custom_text(self):
        index = fixture_index.build_index(HARMONY)
        con = index.connection()
        con.execute(
            "UPDATE chords SET custom_text = 'N.C.' WHERE component_id = "
            "(SELECT id FROM components WHERE uuid LIKE '%c2')"
        )
        got = tql.run(index, '"N.C." IN harmony')
        assert [c.start for m in got.matches for c in m.slots[0]] == [1]

    def test_a_label_wildcard_still_takes_any_chord(self):
        assert len(run(HARMONY, "* IN harmony").matches) == 14
        # [label = *] is allowed on chords and keys, unlike [label = V7]
        assert len(run(HARMONY, "*[label = *] IN harmony").matches) == 14
        assert len(run(HARMONY, "*[label = *] IN keys").matches) == 3


class TestLabelConditions:
    """A label condition on chords tests the symbol, the Roman numeral and the
    custom text alike, whatever the chord's display_mode (Felipe, 2026-10-27)."""

    def test_a_regular_expression_on_the_label_finds_symbol_and_numeral(self):
        assert starts(HARMONY, "*[label ~ /^V7$/] IN harmony") == [1, 9, 17]
        assert starts(HARMONY, "*[label ~ /^G7/] IN harmony") == [1, 3, 9]
        assert starts(HARMONY, "* IN harmony WHERE label = /^V65$/") == [3]
        assert starts(HARMONY, "* IN harmony WHERE label = /^G7\\/B$/") == [3]

    def test_not_equal_holds_where_none_of_the_three_matches(self):
        # Eb@16 and Eb@18 are I in E-flat major: their numeral matches
        assert starts(HARMONY, "*[label != /^(I|C)$/] IN harmony") == [
            1,
            3,
            6,
            8,
            9,
            14,
            17,
        ]

    def test_the_custom_text_is_a_label_too(self):
        index = fixture_index.build_index(HARMONY)
        index.connection().execute(
            "UPDATE chords SET custom_text = 'dom' WHERE component_id LIKE '%c2'"
        )
        got = tql.run(index, "*[label ~ dom] IN harmony")
        assert [c.start for m in got.matches for c in m.slots[0]] == [1]

    def test_the_display_mode_plays_no_part(self):
        index = fixture_index.build_index(HARMONY)
        con = index.connection()
        con.execute("UPDATE components SET label = 'shown' WHERE kind = 'chord'")
        got = tql.run(index, "*[label ~ /^(V7|Bb7)$/] IN harmony")
        assert [c.start for m in got.matches for c in m.slots[0]] == [1, 9, 17]
        got = tql.run(index, "V7 IN harmony WHERE $1.label ~ /shown/")
        assert got.matches == []


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
            "UPDATE chords SET custom_text = 'N.C.' WHERE component_id = "
            "(SELECT id FROM components WHERE uuid LIKE '%c2')"
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
        # a chord on a phrase's last boundary is that phrase's last chord too: the
        # i at 8 ends the first phrase, the Eb at 16 (an I in E-flat) the second
        got = run(HARMONY, "phrase[ENDS WITH I IN harmony] IN form")
        assert [c.start for m in got.matches for c in m.slots[0]] == [8, 16]

    def test_a_key_condition_on_chords_in_brackets(self):
        assert starts(HARMONY, '*[key = "Eb"] IN harmony') == [16, 17, 18]
        assert starts(HARMONY, '*[key = "Eb"] IN keys') == [16]

    def test_a_label_condition_on_chords_matches_as_the_step(self):
        step = starts(HARMONY, "V7 IN harmony")
        assert step
        for text in ("*[label = V7] IN harmony", "* IN harmony WHERE label = V7"):
            assert starts(HARMONY, text) == step


def phrases(chords, keys=((0, "C", "major"),), markers=()):
    """Form (X) with ``phrase`` over 0-8 s and ``next`` over 8-16 s, Harmony and
    the markers Cadences."""
    return {
        "length": 16,
        "timelines": [
            {
                "name": "Form (X)",
                "kind": "hierarchy",
                "units": [["phrase", 1, 0, 8], ["next", 1, 8, 16]],
            },
            {
                "name": "Harmony",
                "kind": "harmony",
                "keys": [list(k) for k in keys],
                "chords": [list(c) for c in chords],
            },
            {"name": "Cadences", "kind": "marker", "units": [list(m) for m in markers]},
        ],
    }


I_V_I = [(0, "C", "major"), (4, "G", "major"), (8, "C", "major")]


def where(fix, text):
    """The matches of ``text`` as ``"phrase@0 | I@8"`` strings, sorted."""
    got = run(fix, text)
    return sorted(
        " | ".join(", ".join(f"{c.label}@{c.start:g}" for c in s) for s in m.slots)
        for m in got.matches
    )


class TestChordsOnBoundaries:
    """A chord or key counts where it begins, like a marker: one on a unit's end,
    within the tolerance, is in that unit too, and still in the next."""

    def test_a_chord_on_the_end_of_a_phrase_ends_it(self):
        fix = phrases(I_V_I)
        assert where(fix, "phrase[ENDS WITH I IN harmony] IN form") == ["phrase@0"]
        assert where(fix, "phrase[ENDS WITH V IN harmony] IN form") == []

    def test_and_starts_the_next(self):
        fix = phrases(I_V_I)
        assert where(fix, "next[STARTS WITH I IN harmony] IN form") == ["next@8"]
        assert where(fix, "phrase[STARTS WITH I IN harmony] IN form") == ["phrase@0"]

    def test_in_the_sentence_form_and_in_brackets(self):
        fix = phrases(I_V_I)
        assert where(fix, "I IN harmony DURING phrase IN form") == [
            "C@0 | phrase@0",
            "C@8 | phrase@0",
        ]
        assert where(fix, "phrase IN form CONTAINS I IN harmony") == [
            "phrase@0 | C@0",
            "phrase@0 | C@8",
        ]
        assert where(fix, "phrase[CONTAINS I IN harmony] IN form") == ["phrase@0"]
        assert where(fix, "next IN form CONTAINS I IN harmony") == ["next@8 | C@8"]
        assert where(fix, "next[CONSISTS OF I IN harmony] IN form") == ["next@8"]

    @pytest.mark.parametrize("time, inside", [(8.05, True), (8.1, True), (8.2, False)])
    def test_up_to_the_tolerance_after_the_end(self, time, inside):
        fix = phrases([(0, "C", "major"), (time, "G", "major")])
        found = ["phrase@0"] if inside else []
        assert where(fix, "phrase[CONTAINS V IN harmony] IN form") == found
        assert where(fix, "phrase[ENDS WITH V IN harmony] IN form") == found
        assert bool(where(fix, "V IN harmony DURING phrase IN form")) == inside

    def test_a_key_on_the_end_of_a_phrase_is_in_it_too(self):
        fix = phrases([(0, "C", "major")], keys=[(0, "C", "major"), (8, "G", "major")])
        assert where(fix, "phrase[CONTAINS G IN keys] IN form") == ["phrase@0"]
        assert where(fix, "phrase[ENDS WITH G IN keys] IN form") == ["phrase@0"]
        assert where(fix, "next[STARTS WITH G IN keys] IN form") == ["next@8"]
        assert where(fix, "G IN keys DURING phrase IN form") == ["G@8 | phrase@0"]

    def test_a_chord_rings_on_past_the_end_of_its_unit(self):
        # V starts at 4, in the phrase, and lasts until 12
        fix = phrases([(0, "C", "major"), (4, "G", "major"), (12, "C", "major")])
        assert where(fix, "phrase[ENDS WITH V IN harmony] IN form") == ["phrase@0"]
        assert where(fix, "V IN harmony DURING phrase IN form") == ["G@4 | phrase@0"]

    def test_a_chord_at_the_time_of_a_marker_is_during_it(self):
        fix = phrases(I_V_I, markers=[("PAC", 8), ("HC", 4.05), ("EC", 6)])
        assert where(fix, "I IN harmony DURING PAC IN cadences") == ["C@8 | PAC@8"]
        assert where(fix, "PAC IN cadences CONTAINS I IN harmony") == ["PAC@8 | C@8"]
        assert where(fix, "V IN harmony DURING HC IN cadences") == ["G@4 | HC@4.05"]
        assert where(fix, "HC IN cadences CONTAINS V IN harmony") == ["HC@4.05 | G@4"]
        assert where(fix, "V IN harmony DURING EC IN cadences") == []
        assert where(fix, "*[DURING PAC IN cadences] IN harmony") == ["C@8"]
        assert where(fix, "PAC[STARTS WITH I IN harmony] IN cadences") == ["PAC@8"]
        assert where(fix, "PAC[CONTAINS V IN harmony] IN cadences") == []


class TestEqualTimes:
    """Of several chords or keys at one time, the first by label (ignoring case)
    ends where it starts, whatever order the file stores them in."""

    CHORDS = [(0, "C", "major"), (0, "G", "major"), (4, "A", "minor")]

    @pytest.mark.parametrize("order", [(0, 1, 2), (1, 0, 2)])
    def test_the_chord_that_lasts_does_not_follow_the_file(self, order):
        chords = [list(self.CHORDS[i]) for i in order]
        got = run(harmony_fixture([[0, "C", "major"]], chords, 16), "* IN harmony")
        assert [(c.label, c.start, c.end) for m in got.matches for c in m.slots[0]] == [
            ("C", 0, 0),
            ("G", 0, 4),
            ("Am", 4, 16),
        ]

    @pytest.mark.parametrize("first", ["D", "G"])
    def test_two_chords_at_one_time_go_by_symbol(self, first):
        # Dm before G, whichever the file stores first. A chord's label is its
        # symbol (sheet I6), a capital root and then no other capital, so case
        # never decides between two chords: the Roman ii and V, which it did
        # decide, are no longer labels
        chords = {"D": (0, "D", "minor"), "G": (0, "G", "major")}
        stored = [list(chords[first]), list(chords["G" if first == "D" else "D"])]
        fix = harmony_fixture([[0, "C", "major"]], stored, 10)
        got = run(fix, "* IN harmony")
        assert [(c.label, c.start, c.end) for m in got.matches for c in m.slots[0]] == [
            ("Dm", 0, 0),
            ("G", 0, 10),
        ]

    @pytest.mark.parametrize(
        "keys",
        [
            [(0, "C", "major"), (0, "G", "major")],
            [(0, "G", "major"), (0, "C", "major")],
        ],
    )
    def test_the_key_that_lasts_is_the_one_in_force(self, keys):
        fix = harmony_fixture([list(k) for k in keys], [[0, "G", "major"]], 10)
        got = run(fix, "* IN keys")
        assert [(c.label, c.start, c.end) for m in got.matches for c in m.slots[0]] == [
            ("C", 0, 0),
            ("G", 0, 10),
        ]
        assert labels(fix, "* IN harmony") == [("I",)]


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
        con.execute(
            "UPDATE keys SET key = 'Cm' WHERE component_id = "
            "(SELECT id FROM components WHERE uuid LIKE '%k2')"
        )
        assert [r[0] for r in con.execute("SELECT key FROM keys")] == ["c", "Cm"]
        assert len(tql.run(index, "* THEN * IN keys WHERE $1.key = $2.key").matches) == 1
        assert tql.run(index, "* THEN * IN keys WHERE $1.key != $2.key").matches == []


class TestShownSqlKeepsToWhatItDoes:
    """A statement reads chords and keys only where the lanes can hold them,
    and labels only where they can hold labelled units."""

    def test_a_join_between_cadences_and_form_does_not_read_chords(self):
        got = tql.run(
            fixture_index.build_index(FIXTURES["exposition"]),
            "PAC IN cadences SAME END ST IN form",
        )
        assert "tql_chord" not in got.sql
        assert "tql_key" not in got.sql and "categories" in got.sql

    def test_chords_and_keys_do_not_read_categories(self):
        got = run(HARMONY, "V7 THEN I IN harmony")
        assert "tql_chord" in got.sql and "categories" not in got.sql

    def test_a_query_without_in_on_a_harmony_file_reads_both(self):
        got = run(HARMONY, "V7")
        assert "tql_chord" in got.sql and "categories" in got.sql

    def test_the_shown_statements_still_return_what_the_run_used(self):
        index = fixture_index.build_index(HARMONY)
        got = tql.run(index, "V7 THEN I IN harmony")
        statements = [
            part.split("\n", 1)[1]
            for part in got.sql.split("\n\n")
            if part.startswith("-- $")
        ]
        used = {c.id for m in got.matches for s in m.slots for c in s}
        shown = {r[0] for text in statements for r in tql.sql(index, text).rows}
        assert used <= shown
