"""Result.stats: counts, durations, positions and transitions of the targets."""

import csv

import examples
import fixture_index
import pytest

from tilia_core import tql

FIXTURES = examples.load()["fixtures"]

SUBTYPES = {
    "name": "subtypes",
    "length": 40,
    "fields": {"title": "Sub"},
    "timelines": [
        {
            "name": "Form (A)",
            "kind": "hierarchy",
            "units": [
                ["bridge.modern", 1, 0, 10],
                ["bridge.classic", 1, 10, 20],
                ["bridge", 1, 20, 30],
                ["verse", 1, 30, 40],
            ],
        }
    ],
}


def index_of(name):
    return fixture_index.build_index(FIXTURES[name])


def run(name, query):
    return tql.run(index_of(name), query)


def subtypes():
    index = fixture_index.build_index(SUBTYPES)
    con = index.connection()
    for label, cid in con.execute(
        "SELECT label, id FROM components WHERE label LIKE 'bridge%'"
    ).fetchall():
        con.execute("INSERT INTO categories VALUES (?, ?)", (cid, label))
    return tql.run(index, "bridge* IN form")


class TestCounts:
    def test_by_label_is_the_default(self):
        table = run("pop", "chorus IN form").stats("counts")
        assert table.columns == ["label", "matches", "files"]
        assert table.rows == [("chorus", 4, 1), ("chorus?", 1, 1)]

    def test_by_one_key(self):
        table = run("pop", "chorus IN form").stats("counts", by="timeline")
        assert table.columns == ["timeline", "matches", "files"]
        assert table.rows == [("Form (A)", 3, 1), ("Form (B)", 2, 1)]

    def test_by_two_keys(self):
        table = run("pop", "chorus IN form").stats("counts", ["label", "timeline"])
        assert table.columns == ["label", "timeline", "matches", "files"]
        assert table.rows == [
            ("chorus", "Form (A)", 3, 1),
            ("chorus", "Form (B)", 1, 1),
            ("chorus?", "Form (B)", 1, 1),
        ]

    def test_files_are_counted(self):
        index = fixture_index.build_index(FIXTURES["pop"], FIXTURES["strophic"])
        table = tql.run(index, "chorus IN form").stats("counts")
        assert table.rows[0][0] == "chorus"
        assert table.rows[0][2] == 2

    def test_by_category(self):
        table = run("pop", "chorus IN form").stats("counts", "category")
        assert table.rows == [("chorus", 5, 1)]

    def test_category_counts_a_target_once_per_category(self):
        table = run("pop", "* IN form").stats("counts", "category")
        assert dict((r[0], r[1]) for r in table.rows)["chorus"] == 5

    def test_subtypes_are_categories_of_their_own(self):
        table = subtypes().stats("counts", "category")
        assert table.rows == [
            ("bridge", 1, 1),
            ("bridge.classic", 1, 1),
            ("bridge.modern", 1, 1),
        ]

    def test_fold_subtypes(self):
        result = subtypes()
        table = result.stats("counts", "category", fold_subtypes=True)
        assert table.rows == [("bridge", 3, 1)]

    def test_only_targets_are_counted(self):
        table = run("pop", "verse THEN @chorus IN form").stats("counts")
        assert table.rows == [("chorus", 3, 1)]

    def test_a_target_held_by_several_matches_counts_once(self):
        result = run("pop", "verse THEN @chorus IN form")
        assert len(result.matches) == 3
        result = run("pop", "@* THEN @* IN form")
        counts = result.stats("counts", "timeline").rows
        total = sum(r[1] for r in counts)
        ids = {c.id for m in result.matches for s in m.slots for c in s}
        assert total == len(ids)


class TestKeys:
    def test_file(self):
        table = run("pop", "chorus IN form").stats("counts", "file")
        assert table.rows == [("f1", 5, 1)]

    def test_tl_field(self):
        table = run("pop", "chorus IN form").stats("counts", "tl.author")
        assert table.rows == [("A", 3, 1), ("B", 2, 1)]

    def test_file_field(self):
        result = tql.run(index_of("harmony"), "* IN harmony")
        table = result.stats("counts", "file.composer")
        assert table.rows == [("Mozart", len(result.matches), 1)]

    def test_component_field(self):
        table = run("pop", "chorus IN form").stats("counts", "color")
        assert table.rows == [("#ffc0cb", 1, 1), (None, 4, 1)]

    def test_level(self):
        table = run("pop", "* IN form").stats("counts", "level")
        assert [r[0] for r in table.rows] == [1, 2]

    def test_unknown_name_is_refused(self):
        result = run("pop", "chorus IN form")
        with pytest.raises(ValueError, match="counts.*durations.*positions"):
            result.stats("sums")

    def test_unknown_key_is_refused(self):
        result = run("pop", "chorus IN form")
        with pytest.raises(ValueError, match="unknown key 'nope'.*category"):
            result.stats("counts", "nope")
        with pytest.raises(ValueError, match="file.composer|file.id"):
            result.stats("counts", "file.nope")
        with pytest.raises(ValueError, match="tl.author"):
            result.stats("counts", "tl.nope")

    def test_too_many_keys_are_refused(self):
        result = run("pop", "chorus IN form")
        with pytest.raises(ValueError):
            result.stats("counts", ["label", "file", "timeline"])
        with pytest.raises(ValueError):
            result.stats("durations", ["label", "file"])
        with pytest.raises(ValueError):
            result.stats("transitions", "label")


class TestDurations:
    def test_seconds_and_bars(self):
        table = run("pop", "chorus IN form").stats("durations")
        assert table.columns == [
            "label",
            "n",
            "min",
            "median",
            "mean",
            "max",
            "n_bars",
            "min_bars",
            "median_bars",
            "mean_bars",
            "max_bars",
        ]
        assert table.rows == [
            ("chorus", 4, 16.0, 16.0, 16.0, 16.0, 4, 4.0, 4.0, 4.0, 4.0),
            ("chorus?", 1, 16.0, 16.0, 16.0, 16.0, 1, 4.0, 4.0, 4.0, 4.0),
        ]

    def test_median_and_mean(self):
        table = run("pop", "verse IN form").stats("durations")
        # verse: 16, 16, 32, 16, 16 seconds
        assert table.rows[0][:6] == ("verse", 5, 16.0, 16.0, 19.2, 32.0)

    def test_points_are_left_out(self):
        table = run("sonata", "* IN cadences").stats("durations")
        assert all(r[1] == 0 and r[2] is None for r in table.rows)

    def test_files_without_a_time_map_warn(self):
        result = run("scripts", "主歌 IN form")
        table = result.stats("durations")
        assert table.rows == [
            ("主歌", 2, 10.0, 10.0, 10.0, 10.0, 0, None, None, None, None)
        ]
        assert any("time map" in w for w in result.warnings)


class TestPositions:
    def test_tenths(self):
        table = run("pop", "chorus IN form").stats("positions")
        assert table.columns == ["label", "from_pct", "to_pct", "n"]
        assert table.rows == [
            ("chorus", 30, 40, 2),
            ("chorus", 50, 60, 1),
            ("chorus", 80, 90, 1),
            ("chorus?", 80, 90, 1),
        ]

    def test_a_start_at_the_end_is_in_the_last_tenth(self):
        fixture = {
            "length": 10,
            "timelines": [
                {"name": "Cadences", "kind": "marker", "units": [["x", 10], ["x", 0]]}
            ],
        }
        result = tql.run(fixture_index.build_index(fixture), "x")
        assert result.stats("positions").rows == [("x", 0, 10, 1), ("x", 90, 100, 1)]

    def test_files_without_a_media_length_warn(self):
        index = fixture_index.build_index(FIXTURES["pop"])
        index.connection().execute("UPDATE files SET media_length = NULL")
        result = tql.run(index, "chorus IN form")
        assert result.stats("positions").rows == []
        assert any("media length" in w for w in result.warnings)


class TestTransitions:
    def test_adjacent_pairs_by_lane(self):
        table = run("pop", "chorus OR verse OR bridge IN form").stats("transitions")
        assert table.columns == ["from", "to", "n"]
        rows = {(a, b): n for a, b, n in table.rows}
        assert rows[("verse", "chorus")] == 3
        assert rows[("chorus", "bridge")] == 1
        assert rows[("verse", "verse")] == 1
        assert ("verse", "intro") not in rows

    def test_lanes_are_not_mixed(self):
        table = run("pop", "* IN form").stats("transitions")
        rows = {(a, b): n for a, b, n in table.rows}
        assert rows[("A", "A")] == 1  # level 2 of Form (A)
        assert ("A", "intro") not in rows
        assert rows[("intro", "verse")] == 2  # once per timeline

    def test_rows_are_sorted(self):
        table = run("pop", "* IN form").stats("transitions")
        assert table.rows == sorted(table.rows)


class TestTableCsv:
    def test_round_trip(self, tmp_path):
        table = run("pop", "chorus IN form").stats("counts", "timeline")
        path = tmp_path / "t.csv"
        table.to_csv(path)
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data
        with open(path, encoding="utf-8", newline="") as f:
            lines = list(csv.reader(f))
        assert lines == [
            ["timeline", "matches", "files"],
            ["Form (A)", "3", "1"],
            ["Form (B)", "2", "1"],
        ]

    def test_none_is_empty_and_text_is_nfc(self, tmp_path):
        table = tql.Table(["a", "b"], [(None, "Straśe")])
        path = tmp_path / "t.csv"
        table.to_csv(path)
        assert path.read_text(encoding="utf-8") == "a,b\n,Straśe\n"
