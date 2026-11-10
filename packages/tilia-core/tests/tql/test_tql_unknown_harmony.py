"""A chord quality or key mode the index doesn't know (a newer TiLiA, or a
hand-edited file; TimeLineAnnotator/project-management#383, point 2): the
component is indexed with its stored fields; its Roman numeral, symbol and
label stay empty; it matches only ``quality = <name>`` (``mode = <name>`` for
a key) and ``*``; and a result that looks in its lane warns once per file,
naming it."""

import fixture_index

from tilia_core import tql


def harmony_fixture(keys, chords, length=10):
    return {
        "length": length,
        "timelines": [
            {"name": "Harmony", "kind": "harmony", "keys": keys, "chords": chords}
        ],
    }


# C major; a G chord of an unknown quality twice, then a C major triad.
UNKNOWN_QUALITY = harmony_fixture(
    [[0, "C", "major"]],
    [[0.5, "G", "made-up-quality"], [1.0, "G", "made-up-quality"], [2.0, "C", "major"]],
)

# A key on C of an unknown mode; a G major and a C major triad in it.
UNKNOWN_MODE = harmony_fixture(
    [[0, "C", "made-up-mode"]],
    [[0.5, "G", "major"], [1.0, "C", "major"]],
)


def chord_rows(index):
    con = index.connection()
    return con.execute(
        "SELECT ch.quality, ch.roman, ch.symbol, c.label FROM chords ch "
        "JOIN components c ON c.id = ch.component_id ORDER BY c.start"
    ).fetchall()


def key_rows(index):
    con = index.connection()
    return con.execute(
        "SELECT k.mode, k.tonic, k.key, c.label FROM keys k "
        "JOIN components c ON c.id = k.component_id ORDER BY c.start"
    ).fetchall()


def starts(result):
    return [c.start for m in result.matches for s in m.slots for c in s]


class TestUnknownQuality:
    def test_indexed_with_its_stored_fields_and_no_labels(self):
        index = fixture_index.build_index(UNKNOWN_QUALITY)
        rows = chord_rows(index)
        assert rows[0] == ("made-up-quality", None, None, "")
        assert rows[1] == ("made-up-quality", None, None, "")
        assert rows[2][0] == "major" and rows[2][2] == "C"

    def test_matches_by_its_quality_and_by_any(self):
        index = fixture_index.build_index(UNKNOWN_QUALITY)
        assert starts(tql.run(index, "*[quality = made-up-quality] IN harmony")) == [
            0.5,
            1.0,
        ]
        assert starts(tql.run(index, "* IN harmony")) == [0.5, 1.0, 2.0]

    def test_no_literal_matches_it(self):
        index = fixture_index.build_index(UNKNOWN_QUALITY)
        for literal in ("G", "V", "G7", "V7"):
            assert starts(tql.run(index, f"{literal} IN harmony")) == []

    def test_a_result_warns_once_per_file_naming_the_quality(self):
        index = fixture_index.build_index(UNKNOWN_QUALITY)
        warnings = tql.run(index, "* IN harmony").warnings
        found = [w for w in warnings if "made-up-quality" in w]
        assert len(found) == 1
        assert "unknown chord quality" in found[0]

    def test_a_query_on_another_lane_doesnt_warn(self):
        fix = harmony_fixture([[0, "C", "major"]], [[0.5, "G", "made-up-quality"]])
        fix["timelines"].append(
            {"name": "Cadences", "kind": "marker", "units": [["PAC", 1.0]]}
        )
        index = fixture_index.build_index(fix)
        result = tql.run(index, "PAC IN Cadences")
        assert starts(result) == [1.0]
        assert not [w for w in result.warnings if "made-up-quality" in w]


class TestUnknownMode:
    def test_indexed_with_its_stored_fields_and_no_label(self):
        index = fixture_index.build_index(UNKNOWN_MODE)
        assert key_rows(index) == [("made-up-mode", "C", None, "")]

    def test_matches_by_its_mode_and_by_any(self):
        index = fixture_index.build_index(UNKNOWN_MODE)
        assert starts(tql.run(index, "*[mode = made-up-mode] IN keys")) == [0.0]
        assert starts(tql.run(index, "* IN keys")) == [0.0]

    def test_no_key_literal_matches_it(self):
        index = fixture_index.build_index(UNKNOWN_MODE)
        for literal in ("C", "c"):
            assert starts(tql.run(index, f"{literal} IN keys")) == []

    def test_its_chords_keep_their_symbols_but_have_no_roman_numerals(self):
        index = fixture_index.build_index(UNKNOWN_MODE)
        rows = chord_rows(index)
        assert [(r[1], r[2]) for r in rows] == [(None, "G"), (None, "C")]
        assert starts(tql.run(index, "G IN harmony")) == [0.5]
        assert starts(tql.run(index, "V IN harmony")) == []
        assert starts(tql.run(index, "I IN harmony")) == []

    def test_a_result_warns_once_per_file_naming_the_mode(self):
        index = fixture_index.build_index(UNKNOWN_MODE)
        warnings = tql.run(index, "* IN keys").warnings
        found = [w for w in warnings if "made-up-mode" in w]
        assert len(found) == 1
        assert "unknown key mode" in found[0]
