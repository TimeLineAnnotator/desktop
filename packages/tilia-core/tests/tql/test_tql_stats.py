"""Result.stats: counts, durations, positions and transitions of the targets."""

import csv
import threading

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import stats

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


# (name, by, the column that counts targets)
TABLES = [
    pytest.param("counts", None, "matches", id="counts-one-key"),
    pytest.param("counts", ["label", "level"], "matches", id="counts-two-keys"),
    pytest.param("durations", None, "n", id="durations"),
    pytest.param("positions", None, "n", id="positions"),
    pytest.param("transitions", None, "n", id="transitions"),
]
CUT_AT = 3


def exposition(**limits):
    return tql.run(index_of("exposition"), "* IN form", **limits)


def counted(table, column):
    return sum(row[table.columns.index(column)] for row in table.rows)


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

    def test_a_statistics_table_of_a_cut_result_returns_its_reason(self, tmp_path):
        table = exposition(max_matches=CUT_AT).stats("counts")
        assert table.to_csv(tmp_path / "t.csv") == "max_matches"

    def test_a_statistics_table_of_a_complete_result_returns_none(self, tmp_path):
        table = exposition().stats("counts")
        assert table.to_csv(tmp_path / "t.csv") is None

    def test_a_cut_table_is_written_as_it_is(self, tmp_path):
        table = exposition(max_matches=CUT_AT).stats("counts")
        path = tmp_path / "t.csv"
        table.to_csv(path)
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data
        with open(path, encoding="utf-8", newline="") as f:
            lines = list(csv.reader(f))
        assert lines == [list(table.columns)] + [
            [str(v) for v in row] for row in table.rows
        ]
        assert "max_matches" not in path.read_text(encoding="utf-8")

    def test_a_sql_table_cut_by_max_rows_returns_its_reason(self, tmp_path):
        table = tql.sql(index_of("pop"), "SELECT id FROM components", max_rows=2)
        assert table.stopped == "max_rows" and len(table.rows) == 2
        path = tmp_path / "t.csv"
        assert table.to_csv(path) == "max_rows"
        assert len(path.read_text(encoding="utf-8").splitlines()) == 3

    def test_a_sql_table_that_is_whole_returns_none(self, tmp_path):
        table = tql.sql(index_of("pop"), "SELECT id FROM components LIMIT 2")
        assert table.stopped is None
        assert table.to_csv(tmp_path / "t.csv") is None

    def test_a_table_built_by_hand_returns_its_reason(self, tmp_path):
        table = tql.Table(["a"], [(1,)], stopped="time_limit")
        assert table.to_csv(tmp_path / "t.csv") == "time_limit"
        assert tql.Table(["a"], [(1,)]).to_csv(tmp_path / "u.csv") is None

    def test_none_is_empty_and_text_is_nfc(self, tmp_path):
        table = tql.Table(["a", "b"], [(None, "Straśe")])
        path = tmp_path / "t.csv"
        table.to_csv(path)
        assert path.read_text(encoding="utf-8") == "a,b\n,Straśe\n"


@pytest.mark.parametrize("name, by, column", TABLES)
class TestStopped:
    """A table carries the reason its result stopped, if it did."""

    def test_a_result_cut_by_max_matches(self, name, by, column):
        result = exposition(max_matches=CUT_AT)
        assert result.stopped == "max_matches"
        assert result.stats(name, by).stopped == "max_matches"

    def test_a_complete_result(self, name, by, column):
        result = exposition()
        assert result.stopped is None
        assert result.stats(name, by).stopped is None

    def test_a_result_that_is_not_reached_by_its_limit(self, name, by, column):
        result = exposition(max_matches=100)
        assert result.stopped is None
        assert result.stats(name, by).stopped is None

    def test_a_run_cancelled_before_it_started(self, name, by, column):
        cancel = threading.Event()
        cancel.set()
        result = exposition(cancel=cancel)
        assert result.stopped == "cancelled" and result.matches == []
        table = result.stats(name, by)
        assert table.stopped == "cancelled"
        assert table.rows == []

    def test_a_run_stopped_by_its_time_limit(self, name, by, column):
        result = exposition(time_limit=0)
        assert result.stopped == "time_limit"
        assert result.stats(name, by).stopped == "time_limit"

    def test_the_table_counts_only_the_matches_found(self, name, by, column):
        result = exposition(max_matches=CUT_AT)
        complete = exposition()
        assert len(result.matches) == CUT_AT < len(complete.matches)
        table = result.stats(name, by)
        full = complete.stats(name, by)
        assert table.columns == full.columns
        assert counted(table, column) < counted(full, column)
        if name != "transitions":  # the targets are the 3 units found
            assert counted(table, column) == CUT_AT


def test_the_labels_counted_are_those_of_the_matches_found():
    result = exposition(max_matches=CUT_AT)
    found = sorted(m.slots[0][0].label for m in result.matches)
    table = result.stats("counts")
    assert [r[0] for r in table.rows] == sorted(set(found))
    assert table.stopped == "max_matches"


def test_transitions_pair_the_units_found_in_a_lane():
    fixture = {
        "length": 5,
        "timelines": [
            {
                "name": "Form (X)",
                "kind": "hierarchy",
                "units": [[label, 1, i, i + 1] for i, label in enumerate("abcde")],
            }
        ],
    }
    index = fixture_index.build_index(fixture)
    result = tql.run(index, "* IN form", max_matches=CUT_AT)
    found = sorted(
        (m.slots[0][0] for m in result.matches), key=lambda c: (c.start, c.id)
    )
    assert len(found) == CUT_AT
    table = result.stats("transitions")
    assert table.stopped == "max_matches"
    assert table.rows == sorted(
        (a.label, b.label, 1) for a, b in zip(found, found[1:], strict=False)
    )
    assert len(table.rows) == CUT_AT - 1
    assert len(tql.run(index, "* IN form").stats("transitions").rows) == 4


def test_table_docstring_names_every_reason_stopped_can_hold():
    for reason in ("max_rows", "max_matches", "time_limit", "cancelled"):
        assert f'"{reason}"' in stats.Table.__doc__


def test_table_docstring_says_what_a_table_of_stats_carries():
    doc = " ".join(stats.Table.__doc__.split())
    assert "Result.stats" in doc
    assert "carries the reason its result stopped for" in doc
    assert "counts only the matches that were found" in doc
