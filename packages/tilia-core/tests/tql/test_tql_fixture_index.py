import examples
import fixture_index
import pytest
from fake_timemap import FakeTimeMap

FIXTURES = examples.load()["fixtures"]

TABLES = [
    "files",
    "timelines",
    "components",
    "hierarchies",
    "ranges",
    "chords",
    "keys",
    "categories",
    "positions",
    "measures",
    "fields",
]

# files, timelines, components, hierarchies, ranges, chords, keys,
# categories, positions, measures, fields
COUNTS = {
    "exposition": (1, 2, 13, 9, 0, 0, 0, 13, 0, 0, 0),
    "sonata": (1, 5, 179, 11, 0, 0, 2, 17, 179, 40, 0),
    "pop": (1, 4, 149, 19, 2, 0, 0, 21, 149, 32, 0),
    "strophic": (1, 2, 9, 9, 0, 0, 0, 9, 0, 0, 0),
    "harmony": (1, 2, 20, 3, 0, 14, 3, 3, 0, 0, 1),
    "repeat": (1, 2, 103, 7, 0, 0, 0, 7, 103, 24, 0),
    "recipe": (1, 3, 5, 2, 0, 0, 0, 5, 0, 0, 0),
    "scripts": (1, 1, 4, 4, 0, 0, 0, 4, 0, 0, 0),
}


def count(index, table):
    return index.connection().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def rows(index, sql, *args):
    return index.connection().execute(sql, args).fetchall()


def one(index, sql, *args):
    return rows(index, sql, *args)[0]


def test_every_fixture_is_counted():
    assert set(COUNTS) == set(FIXTURES)


@pytest.mark.parametrize("name", sorted(COUNTS))
def test_row_counts(name):
    index = fixture_index.build_index(FIXTURES[name])
    assert tuple(count(index, t) for t in TABLES) == COUNTS[name]
    assert index.generation == 1


def test_roles_and_authors_of_exposition():
    index = fixture_index.build_index(FIXTURES["exposition"])
    assert rows(
        index, "SELECT name, role, author, ordinal FROM timelines ORDER BY ordinal"
    ) == [("Form (Caplin)", "form", "Caplin", 1), ("Cadences", "cadences", None, 2)]


def test_roles_of_harmony_and_sonata():
    index = fixture_index.build_index(FIXTURES["harmony"])
    assert one(index, "SELECT role, kind FROM timelines WHERE name = 'Harmony'") == (
        "harmony",
        "harmony",
    )
    index = fixture_index.build_index(FIXTURES["sonata"])
    assert rows(index, "SELECT name, kind, role FROM timelines ORDER BY ordinal")[
        2:
    ] == [
        ("Fermatas", "marker", None),
        ("Harmony", "harmony", "harmony"),
        ("Beats", "beat", None),
    ]
    assert one(index, "SELECT time_map FROM files") == (
        one(index, "SELECT id FROM timelines WHERE kind = 'beat'")[0],
    )


def test_hierarchy_parents_of_exposition():
    index = fixture_index.build_index(FIXTURES["exposition"])
    sql = (
        "SELECT p.label, h.depth FROM components c "
        "JOIN hierarchies h ON h.component_id = c.id "
        "LEFT JOIN components p ON p.id = h.parent_id "
        "WHERE c.label = ? AND c.start = ?"
    )
    assert one(index, sql, "continuation", 4) == ("MT", 3)
    assert one(index, sql, "exposition", 0) == (None, 1)


def test_harmony_components():
    index = fixture_index.build_index(FIXTURES["harmony"])
    sql = (
        'SELECT c.label, c."end", ch.key, k.label FROM components c '
        "JOIN chords ch ON ch.component_id = c.id "
        "LEFT JOIN components k ON k.id = ch.key_id WHERE c.start = ?"
    )
    assert one(index, sql, 9) == ("G7", 10, "c", "c")
    assert one(index, sql, 3)[0] == "G7/B"
    assert one(index, sql, 18)[:2] == ("Eb", 24)
    assert rows(index, "SELECT label FROM components WHERE kind = 'key'") == [
        ("C",),
        ("c",),
        ("Eb",),
    ]
    assert rows(index, "SELECT name, value FROM fields") == [("composer", "Mozart")]


def test_chords_are_labelled_by_their_symbols():
    # A chord's label is its symbol, TiLiA's default display, whatever its
    # display_mode (Felipe, 2026-10-27); the Roman numeral is a field.
    index = fixture_index.build_index(FIXTURES["harmony"])
    labels = rows(
        index,
        "SELECT c.label, ch.roman, ch.symbol FROM components c "
        "JOIN chords ch ON ch.component_id = c.id",
    )
    assert labels
    assert all(label == symbol != roman for label, roman, symbol in labels)


def test_a_list_field_gives_one_row_per_item():
    fixture = {**FIXTURES["recipe"], "fields": {"Tags": ["draft", "cooking"]}}
    index = fixture_index.build_index(fixture)
    assert rows(index, "SELECT name, value FROM fields ORDER BY value") == [
        ("tags", "cooking"),
        ("tags", "draft"),
    ]


def test_chord_before_the_first_key_has_no_key():
    fixture = {
        "length": 8,
        "timelines": [
            {
                "name": "H",
                "kind": "harmony",
                "keys": [[4, "D", "major"]],
                "chords": [[0, "C", "major"], [4, "D", "major"]],
            }
        ],
    }
    index = fixture_index.build_index(fixture)
    assert rows(index, "SELECT key, key_id FROM chords ORDER BY step, accidental") == [
        (None, None),
        ("D", "f1:t1:k1"),
    ]


def test_categories_of_pop():
    index = fixture_index.build_index(FIXTURES["pop"])
    assert one(
        index,
        "SELECT cat.category FROM components c JOIN categories cat "
        "ON cat.component_id = c.id WHERE c.label = 'chorus?'",
    ) == ("chorus",)
    assert one(index, "SELECT COUNT(*) FROM categories WHERE category = 'chorus'") == (
        5,
    )


def test_supertypes_come_from_the_grammar_only():
    # de Clercq marks a subtype with a dot; with no grammar a dot is part of
    # the label, and no category has a supertype
    def fixture(grammar):
        f = {
            "length": 10,
            "timelines": [
                {
                    "name": "Form (A)",
                    "kind": "hierarchy",
                    "units": [["bridge.modern", 1, 0, 5], ["I. Allegro", 1, 5, 10]],
                }
            ],
        }
        return {**f, "grammar": grammar} if grammar else f

    sql = "SELECT category, supertype FROM categories ORDER BY 1"
    with_grammar = fixture_index.build_index(fixture("de Clercq"))
    assert rows(with_grammar, sql) == [("bridge.modern", "bridge"), ("i. allegro", "i")]
    without = fixture_index.build_index(fixture(None))
    assert rows(without, sql) == [("bridge.modern", None), ("i. allegro", None)]


def test_categories_without_grammar_are_whole_labels():
    index = fixture_index.build_index(FIXTURES["scripts"])
    assert rows(index, "SELECT DISTINCT category FROM categories ORDER BY 1") == [
        ("strasse",),
        ("主歌",),
        ("副歌",),
    ]


def test_color_of_pop():
    index = fixture_index.build_index(FIXTURES["pop"])
    assert rows(
        index, "SELECT start, color FROM components WHERE color IS NOT NULL"
    ) == [(72, "#ffc0cb")]


def test_ranges_of_pop():
    index = fixture_index.build_index(FIXTURES["pop"])
    assert rows(index, "SELECT row, row_folded FROM ranges") == [("solo", "solo")] * 2
    assert one(index, "SELECT COUNT(DISTINCT row_id) FROM ranges") == (1,)


POSITION = (
    "SELECT p.bar, p.end_bar, p.beat, p.pass, p.bar_count, p.bar_label, "
    "p.bar_beat_count, p.downbeat FROM components c "
    "JOIN positions p ON p.component_id = c.id "
    "WHERE c.label = ? AND c.start = ? AND c.kind = 'hierarchy'"
)


def test_positions_of_repeat():
    index = fixture_index.build_index(FIXTURES["repeat"])
    assert one(index, POSITION, "b2", 44) == (12, 16, 1.0, 1, 12, "12", 4, 1)
    assert one(index, POSITION, "b2", 76)[:2] == (12, 16)
    assert one(index, POSITION, "b2", 76)[3:5] == (2, 20)
    assert one(index, POSITION, "b1", 64)[:1] + one(index, POSITION, "b1", 64)[3:5] == (
        9,
        2,
        17,
    )
    assert one(index, POSITION, "A", 0)[:2] == (1, 8)


def test_measures_and_beats_of_repeat():
    index = fixture_index.build_index(FIXTURES["repeat"])
    assert count(index, "measures") == 24
    assert one(index, "SELECT COUNT(*) FROM components WHERE kind = 'beat'") == (96,)
    assert rows(
        index, 'SELECT count, number, label, start, "end", beats FROM measures'
    )[16] == (17, 9, "9", 64, 68, 4)
    assert one(index, "SELECT MAX(start) FROM components WHERE kind = 'beat'") == (95,)


def test_measures_pass_follows_the_repeats():
    index = fixture_index.build_index(FIXTURES["repeat"])
    got = rows(index, "SELECT number, pass FROM measures ORDER BY count")
    tm = index.time_map("f1")
    seen: dict[int, int] = {}
    want = []
    for number in tm.numbers:
        seen[number] = seen.get(number, 0) + 1
        want.append((number, seen[number]))
    assert got == want
    assert {p for _, p in got} == {1, 2}


def test_measures_pass_is_1_without_repeats():
    index = fixture_index.build_index(FIXTURES["sonata"])
    got = rows(index, "SELECT pass FROM measures")
    assert got and set(got) == {(1,)}


def test_fake_timemap_of_repeat():
    index = fixture_index.build_index(FIXTURES["repeat"])
    tm = index.time_map("f1")
    assert isinstance(tm, FakeTimeMap)
    assert tm.position(4.0, "bar") == 1.0
    assert tm.position(4.0, "beat") == 4.0
    assert tm.position(96.0, "bar") == 24.0
    assert tm.length(0.0, 32.0, "bar") == 8.0
    assert tm.unit_seconds(10.0, "beat") == 1.0
    assert tm.unit_seconds(10.0, "bar") == 4.0
    assert tm.bar(3.95) == 2
    assert tm.beat(3.95) == 1.0
    assert tm.is_downbeat(3.95)
    assert tm.bar(4.5) == 2
    assert tm.beat(4.5) == 1.5
    assert tm.bar(-1.0) is None
    assert tm.bar(96.0) is None
    assert tm.bar(100.0) is None
    assert tm.position(100.0, "bar") is None
    assert tm.unit_seconds(100.0, "bar") is None
    assert tm.end_bar(8.0) == 2
    assert tm.end_bar(96.0) == 16
    assert tm.end_bar(0.0) is None
    assert tm.end_bar(8.0, 4.0) == 2
    # a span whose end snaps back onto its start's downbeat ends in its
    # start's bar (#104, 2026-10-10), the first bar included
    assert tm.end_bar(8.05, 8.0) == 3
    assert tm.end_bar(0.05, 0.0) == 1
    assert tm.measures()[16] == (64.0, 68.0, 9, "9")


def point_and_span_fixture(*units):
    return {
        "length": 8,
        "timelines": [
            {"name": "Form", "kind": "hierarchy", "units": list(units)},
            {
                "name": "Beats",
                "kind": "beats",
                "start": 0,
                "every": 1,
                "beats_per_bar": 4,
                "bars": 2,
            },
        ],
    }


def test_a_unit_off_the_map_has_no_positions_row():
    index = fixture_index.build_index(
        point_and_span_fixture(
            ["in", 1, 0, 4], ["late", 1, 9, 10], ["early", 1, -2, -1]
        )
    )
    assert rows(
        index,
        "SELECT c.label FROM components c JOIN positions p ON p.component_id = c.id "
        "WHERE c.kind = 'hierarchy'",
    ) == [("in",)]


def test_a_point_ends_in_its_own_bar():
    # A marker at 4.0 is in bar 2; a span ending at 4.0 ends in bar 1.
    fixture = point_and_span_fixture(["span", 1, 0, 4])
    fixture["timelines"].append(
        {"name": "Marks", "kind": "marker", "units": [["point", 4]]}
    )
    index = fixture_index.build_index(fixture)
    sql = (
        "SELECT p.bar, p.end_bar FROM components c "
        "JOIN positions p ON p.component_id = c.id WHERE c.label = ?"
    )
    assert one(index, sql, "point") == (2, 2)
    assert one(index, sql, "span") == (1, 1)


def test_a_start_just_before_the_end_of_the_map_is_in_the_last_bar():
    # 7.95 snaps to the map's end (8.0) but lies in the last bar, as it would
    # in a real time map; the end itself is off the map.
    fixture = point_and_span_fixture(["span", 1, 4, 7.95])
    fixture["timelines"].append(
        {"name": "Cadences", "kind": "marker", "units": [["PAC", 7.95], ["X", 8.0]]}
    )
    index = fixture_index.build_index(fixture)
    sql = (
        "SELECT p.bar, p.end_bar, p.beat, p.bar_count FROM components c "
        "JOIN positions p ON p.component_id = c.id WHERE c.label = ?"
    )
    assert one(index, sql, "PAC") == (2, 2, 5.0, 2)
    assert one(index, sql, "span") == (2, 2, 1.0, 2)
    assert rows(index, sql, "X") == []
    tm = index.time_map("f1")
    assert tm.bar(7.95) == 2 and tm.bar(8.0) is None and tm.bar(8.05) is None
    assert tm.position(7.95, "bar") == 2.0 == tm.position(8.0, "bar")
    assert tm.length(4.0, 7.95, "bar") == 1.0


def test_no_time_map_in_exposition():
    index = fixture_index.build_index(FIXTURES["exposition"])
    assert index.time_map("f1") is None
    assert one(index, "SELECT time_map FROM files") == (None,)
    assert count(index, "positions") == 0
    assert count(index, "measures") == 0


def test_two_fixtures_make_two_files():
    index = fixture_index.build_index(FIXTURES["exposition"], FIXTURES["repeat"])
    assert rows(index, "SELECT id, path FROM files ORDER BY id") == [
        ("f1", "f1.tla"),
        ("f2", "f2.tla"),
    ]
    assert index.time_map("f1") is None
    assert index.time_map("f2") is not None
    assert one(index, "SELECT COUNT(DISTINCT id), COUNT(*) FROM components") == (
        116,
        116,
    )


def test_fixture_name_is_the_file_id():
    index = fixture_index.build_index({**FIXTURES["recipe"], "name": "song"})
    assert one(index, "SELECT id, path FROM files") == ("song", "song.tla")
    assert one(index, "SELECT COUNT(*) FROM components WHERE id LIKE 'song:%'") == (5,)


def test_chords_at_one_time_are_ordered_by_the_label_stored():
    # C (I) and B diminished (vii°) at 0: by the Roman labels the builder
    # stores, I comes first and ends where it starts, and vii° lasts; by the
    # letter labels (Bdim before C) it would be the other way round
    fixture = {
        "length": 4,
        "timelines": [
            {
                "name": "Harmony",
                "kind": "harmony",
                "keys": [[0, "C", "major"]],
                "chords": [[0, "C", "major"], [0, "B", "diminished"]],
            }
        ],
    }
    index = fixture_index.build_index(fixture)
    assert rows(
        index, "SELECT label, start, \"end\" FROM components WHERE kind = 'chord' "
        "ORDER BY \"end\""
    ) == [("I", 0, 0), ("vii°", 0, 4)]
