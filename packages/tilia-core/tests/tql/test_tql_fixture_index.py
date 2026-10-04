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
    assert one(index, sql, 9) == ("V7", 10, "c", "c")
    assert one(index, sql, 3)[0] == "V65"
    assert one(index, sql, 18)[:2] == ("I", 24)
    assert rows(index, "SELECT label FROM components WHERE kind = 'key'") == [
        ("C",),
        ("c",),
        ("Eb",),
    ]
    assert rows(index, "SELECT name, value FROM fields") == [("composer", "Mozart")]


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
    assert tm.measures()[16] == (64.0, 68.0, 9, "9")


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
