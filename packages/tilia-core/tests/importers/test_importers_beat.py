"""Beats from a CSV. The tests ported from TiLiA's `test_beats_from_csv.py` keep its
names and CSV text, and compare the measure table where it compares metric
positions. A value that isn't one reads as the rules read it, not as TiLiA's importer
does (TimeLineAnnotator/project-management#298)."""

import copy
import json

import pytest
from import_docs import component, document, timeline

from tilia_core import build, importers, rules, tla
from tilia_core.importers import beat
from tilia_core.importers._results import ImportFailed
from tilia_core.timemap import pattern, time_map_for
from tilia_core.tla.model import UnknownKind

ASSUMED = {"denominator": 4, "units": "1", "assumed": True}


@pytest.fixture
def imported(tmp_path):
    """Writes a CSV, and imports it into a new beat timeline."""

    def run(data, *, beat_pattern="4", media_length=60.0, time_unit="seconds"):
        path = tmp_path / "beats.csv"
        path.write_text(data, encoding="utf-8", newline="")
        doc = document(media_length=media_length, time_unit=time_unit)
        target = doc.timelines[
            build.add_timeline(doc, "beat", "Measures", beat_pattern=beat_pattern)
        ]
        return beat.import_beats(doc, target.id, path), target

    return run


def times(target):
    return [component.attrs["time"] for component in target.components.values()]


def bars(target):
    """Each measure's number and how many beats it has."""
    return [(row.number, len(row.beats)) for row in target.measures.rows]


def forced(target):
    return [row.number for row in target.measures.rows if row.force_display]


def marks(target):
    """The marks stored, by their beats' times."""
    return {
        component.attrs["time"]: component.attrs["measure"]
        for component in target.components.values()
        if "measure" in component.attrs
    }


def beat_units(target):
    """The beat units stored, with their beats' times."""
    return [
        (component.attrs["time"], component.attrs["beat_unit"])
        for component in target.components.values()
        if "beat_unit" in component.attrs
    ]


def messages(result):
    return [(p.line, p.column, p.message, p.skipped) for p in result.problems]


def test_by_time(imported):
    data = "time\n5\n10\n15\n20"

    result, target = imported(data)

    assert times(target) == [5, 10, 15, 20]
    assert result.problems == []
    assert result.rows == 4
    assert result.created == list(target.components)


def test_component_creation_fail_reason_gets_into_errors(imported):
    data = "time\n101"

    result, target = imported(data, media_length=100)

    assert messages(result) == [
        (2, "time", "Time '01:41.0' is bigger than media time '01:40.0'", True)
    ]
    assert not target.components


def test_with_measure_number(imported):
    data = "time,measure\n5,1\n10,\n15,\n20,\n25,\n30,8"

    _, target = imported(data)

    assert bars(target) == [(1, 4), (8, 2)]
    assert forced(target) == [1, 8]
    # The number on the second row of a measure is the measure's, on its downbeat.
    assert marks(target) == {
        5: {"force_display": True},
        25: {"number": 8, "force_display": True},
    }


def test_with_measure_number_non_monotonic(imported):
    data = "time,measure\n1,1\n2,10\n3,2\n4,11\n5,"

    _, target = imported(data, beat_pattern="1")

    assert bars(target) == [(1, 1), (10, 1), (2, 1), (11, 1), (12, 1)]
    assert forced(target) == [1, 10, 2, 11]


def test_with_is_first_in_measure(imported):
    data = "time,is_first_in_measure\n0,True\n5,\n10,\n15,\n20,\n25,True\n30,\n35,True"

    _, target = imported(data)

    assert bars(target) == [(1, 5), (2, 2), (3, 1)]
    assert forced(target) == []


def test_with_measure_numbers_in_rows_with_is_first_in_measure_false(imported):
    data = "time,is_first_in_measure,measure\n0,True,1\n2,False,8"

    _, target = imported(data)

    assert bars(target) == [(1, 2)]
    assert forced(target) == [1]


def test_with_measure_number_and_is_first_in_csv(imported):
    data = (
        "time,is_first_in_measure,measure\n"
        "0,,\n5,,\n10,,\n15,,\n20,True,\n25,True,10\n30,,\n35,True,"
    )

    _, target = imported(data)

    assert bars(target) == [(1, 4), (2, 1), (10, 2), (11, 1)]
    assert forced(target) == [10]


def test_with_optional_params_not_sorted(imported):
    data = "time,is_first_in_measure,measure\n0,,\n10,,\n5,,\n15,True,"

    with pytest.raises(ImportFailed) as failed:
        imported(data)

    assert failed.value.message == (
        "Time is not sorted in ascending order. Please sort before importing."
    )


def test_with_empty_is_first_in_measure(imported):
    data = "time,is_first_in_measure\n0,\n5,\n10,\n15,\n20,\n25,\n30,\n35,"

    _, target = imported(data)

    assert bars(target) == [(1, 8)]


def test_with_invalid_is_first_in_measure(imported):
    data = "time,is_first_in_measure\n0,\n5,\n10,\n15,\n20,not_valid\n25,True\n30,\n35,"

    result, target = imported(data)

    assert bars(target) == [(1, 5), (2, 3)]
    assert result.problems == []


class TestBeatUnitColumns:
    def test_rows_with_values_get_beat_units(self, imported):
        data = "time,denominator,units\n0,8,3\n1,,\n2,4,2+3\n3,,\n4,,1\n5,,"

        result, target = imported(data, beat_pattern="2")

        assert result.problems == []
        assert beat_units(target) == [
            (0, {"denominator": 8, "units": "3"}),
            (2, {"denominator": 4, "units": "2+3"}),
            (4, {"denominator": 4, "units": "1"}),
        ]

    def test_empty_values_carry_over(self, imported):
        data = "time,denominator,units\n0,8,\n1,,1/2"

        _, target = imported(data, beat_pattern="1")

        assert beat_units(target) == [
            (0, {"denominator": 8, "units": "1"}),
            (1, {"denominator": 8, "units": "1/2"}),
        ]

    def test_only_one_of_the_columns(self, imported):
        data = "time,units\n0,2+3"

        _, target = imported(data)

        assert beat_units(target) == [(0, {"denominator": 4, "units": "2+3"})]

    def test_invalid_values_are_reported(self, imported):
        data = "time,denominator,units\n0,0,1\n1,4,2+\n2,8,1\n3,129,1"

        result, target = imported(data)

        assert messages(result) == [
            (2, "denominator", "0 is not a valid denominator.", False),
            (3, "units", "2+ is not a valid units.", False),
            (5, "denominator", "129 is not a valid denominator.", False),
        ]
        assert {problem.path.name for problem in result.problems} == {"beats.csv"}
        # The first beat keeps its default beat unit; only the valid row adds one.
        assert times(target) == [0, 1, 2, 3]
        assert beat_units(target) == [
            (0, ASSUMED),
            (2, {"denominator": 8, "units": "1"}),
        ]

    def test_without_the_columns(self, imported):
        _, target = imported("time\n0\n1")

        assert beat_units(target) == [(0, ASSUMED)]

    def test_values_from_the_file_are_not_assumed(self, imported):
        _, target = imported("time,denominator\n0,4\n1,")

        assert beat_units(target) == [(0, {"denominator": 4, "units": "1"})]

    def test_units_are_stored_in_their_canonical_form(self, imported):
        _, target = imported('time,units\n0,"2 + 3"\n1,\n')

        assert beat_units(target) == [(0, {"denominator": 4, "units": "2+3"})]

    def test_a_value_that_isnt_a_whole_number_is_not_a_denominator(self, imported):
        result, target = imported("time,denominator\n0,4.0\n1,abc")

        assert messages(result) == [
            (2, "denominator", "4.0 is not a valid denominator.", False),
            (3, "denominator", "abc is not a valid denominator.", False),
        ]
        assert beat_units(target) == [(0, ASSUMED)]

    def test_a_row_that_repeats_the_unit_in_force_changes_nothing(self, imported):
        data = "time,denominator,units\n0,4,1\n1,4,1\n2,,\n3,,1\n4,8,1\n5,8,1"

        result, target = imported(data)

        assert result.problems == []
        assert beat_units(target) == [
            (0, {"denominator": 4, "units": "1"}),
            (4, {"denominator": 8, "units": "1"}),
        ]

    def test_a_row_that_gives_the_default_on_a_later_beat_is_not_a_repeat(
        self, imported
    ):
        # Nobody set the first beat's: the row's is the first one set.
        _, target = imported("time,denominator,units\n0,,\n1,4,1")

        assert beat_units(target) == [
            (0, ASSUMED),
            (1, {"denominator": 4, "units": "1"}),
        ]

    def test_a_skipped_row_gives_nothing_to_carry_over(self, imported):
        data = "time,denominator,units\n0,8,3\n0,4,1\n1,,2"

        result, target = imported(data)

        assert beat_units(target) == [
            (0, {"denominator": 8, "units": "3"}),
            (1, {"denominator": 8, "units": "2"}),
        ]
        assert [problem.line for problem in result.problems] == [3]

    def test_a_skipped_row_doesnt_report_its_beat_unit(self, imported):
        result, _ = imported("time,denominator\n0,4\n0,abc")

        assert messages(result) == [
            (
                3,
                "time",
                "There is already a beat component at the selected position.",
                True,
            )
        ]

    def test_the_first_beat_kept_gets_the_default(self, imported):
        _, target = imported("time\nabc\n1\n2")

        assert beat_units(target) == [(1, ASSUMED)]

    def test_the_table_has_each_measures_unit_in_force(self, imported):
        data = "time,denominator,units\n0,4,1\n1,,\n2,8,3\n3,,"

        _, target = imported(data, beat_pattern="2")

        in_force = [row.beat_unit for row in target.measures.rows]
        assert in_force == [
            tla.BeatUnit(denominator=4, units="1"),
            tla.BeatUnit(denominator=8, units="3"),
        ]


class TestGrouping:
    """Spec, User Story 5, and how the columns are read."""

    def test_time_only_is_grouped_by_the_timelines_pattern(self, imported):
        _, target = imported("time\n0\n1\n2\n3\n4\n5\n6\n7\n8")

        assert bars(target) == [(1, 4), (2, 4), (3, 1)]
        assert sorted(marks(target)) == [0, 4, 8]

    def test_the_pattern_cycles(self, imported):
        _, target = imported("time\n0\n1\n2\n3\n4\n5\n6", beat_pattern="2 3")

        assert bars(target) == [(1, 2), (2, 3), (3, 2)]

    def test_a_pattern_with_groups_is_expanded(self, imported):
        _, target = imported("time\n0\n1\n2\n3\n4\n5\n6", beat_pattern="2[2] 3")

        assert bars(target) == [(1, 2), (2, 2), (3, 3)]

    def test_downbeats_are_the_rows_marked_true_with_any_case(self, imported):
        data = "time,is_first_in_measure\n0,TRUE\n1,false\n2,true\n3,0\n4,True"

        _, target = imported(data)

        assert sorted(marks(target)) == [0, 2, 4]

    def test_marks_hold_only_the_numbers_that_dont_follow(self, imported):
        data = (
            "time,is_first_in_measure,measure\n"
            "0,True,0\n1,True,\n2,True,\n3,True,7\n4,True,8\n5,True,8\n"
        )

        _, target = imported(data)

        assert marks(target) == {
            0: {"number": 0, "force_display": True},
            1: {},
            2: {},
            3: {"number": 7, "force_display": True},
            4: {"force_display": True},
            5: {"number": 8, "force_display": True},
        }
        assert [row.number for row in target.measures.rows] == [0, 1, 2, 7, 8, 8]

    def test_the_first_measure_has_no_number_when_it_is_1(self, imported):
        _, target = imported("time\n0\n1")

        assert marks(target) == {0: {}}

    @pytest.mark.parametrize(
        "header, rows",
        [
            ("is_first_in_measure,time", "True,0\n,1\nTrue,2"),
            ("is_first_in_measure,measure,time", "True,,0\n,,1\nTrue,,2"),
        ],
    )
    def test_is_first_in_measure_is_read_in_any_column(self, imported, header, rows):
        _, target = imported(f"{header}\n{rows}")

        assert bars(target) == [(1, 2), (2, 1)]

    def test_measure_is_read_in_any_column(self, imported):
        _, target = imported("measure,time\n5,0\n,1", beat_pattern="1")

        assert bars(target) == [(5, 1), (6, 1)]
        assert forced(target) == [5]

    def test_a_measure_number_is_read_as_a_whole_number(self, imported):
        result, target = imported("time,measure\n0,1.5\n1,", beat_pattern="1")

        assert messages(result) == [(2, "measure", "1.5 is not a valid measure.", True)]
        assert times(target) == [1]

    def test_a_measure_below_0_breaks_a_rule(self, imported):
        result, target = imported("time,measure\n0,-1\n1,0", beat_pattern="1")

        assert messages(result) == [(2, "measure", "-1 is not a valid measure.", True)]
        assert bars(target) == [(0, 1)]

    def test_a_number_the_grouping_doesnt_read_isnt_reported(self, imported):
        data = "time,is_first_in_measure,measure\n0,True,\n1,False,abc\n2,,-1"

        result, target = imported(data)

        assert result.problems == []
        assert bars(target) == [(1, 3)]


class TestTimelineAttributes:
    def test_the_measures_come_from_an_import(self, imported):
        _, target = imported("time\n0\n1")

        assert target.attrs["measure_source"] == "import"
        assert target.measures.source == "import"
        assert [row.source for row in target.measures.rows] == ["import"]

    def test_the_pattern_is_the_bars_found(self, imported):
        _, target = imported("time\n0\n1\n2\n3\n4\n5\n6\n7\n8\n9")

        assert target.attrs["beat_pattern"] == "2[4] 2"

    def test_the_pattern_with_downbeats_is_the_bars_found(self, imported):
        data = "time,is_first_in_measure\n0,True\n1,\n2,\n3,True\n4,\n5,True"

        _, target = imported(data)

        assert target.attrs["beat_pattern"] == "3 2 1"

    def test_with_no_beat_the_pattern_stays(self, imported):
        result, target = imported("time\n", beat_pattern="3")

        assert result.rows == 0
        assert target.attrs["beat_pattern"] == "3"
        assert target.attrs["measure_source"] == "import"
        assert target.measures.rows == []

    def test_a_pattern_that_wouldnt_parse_isnt_stored(self, imported, monkeypatch):
        # More bars than a pattern can say: the file would keep it, unreadable.
        monkeypatch.setattr(pattern, "MAX_BARS", 3)

        _, target = imported("time\n0\n1\n2\n3", beat_pattern="1")

        assert bars(target) == [(1, 1), (2, 1), (3, 1), (4, 1)]
        assert target.attrs["beat_pattern"] == "1"


class TestABadPattern:
    """A pattern that doesn't parse counts as "4" (#310 (a beat pattern that doesn't
    parse), answered by Anne on 2026-10-14)."""

    @staticmethod
    def run(tmp_path, data, value):
        path = tmp_path / "beats.csv"
        path.write_text(data, encoding="utf-8", newline="")
        doc = document()
        target = doc.timelines[build.add_timeline(doc, "beat", "Measures")]
        target.attrs["beat_pattern"] = value
        return beat.import_beats(doc, target.id, path), target

    @pytest.mark.parametrize(
        "value, error",
        [
            ("abc", "Unexpected 'a'."),
            ("", "Enter at least one bar length."),
            ("10[", "Unclosed '['."),
            ("4 0", "Bar lengths must be at least 1."),
        ],
    )
    def test_the_beats_are_grouped_by_4_and_the_report_names_it(
        self, tmp_path, value, error
    ):
        result, target = self.run(tmp_path, "time\n0\n1\n2\n3\n4", value)

        assert bars(target) == [(1, 4), (2, 1)]
        assert result.notes == [
            f"Invalid beat pattern '{value}': {error} Using '4' instead."
        ]
        assert result.problems == []
        assert target.attrs["beat_pattern"] == "4 1"

    def test_a_pattern_that_isnt_text_doesnt_parse(self, tmp_path):
        result, target = self.run(tmp_path, "time\n0\n1\n2\n3\n4", [4, 3])

        assert bars(target) == [(1, 4), (2, 1)]
        assert len(result.notes) == 1
        assert "[4, 3]" in result.notes[0]

    def test_with_downbeats_the_pattern_isnt_read(self, tmp_path):
        data = "time,is_first_in_measure\n0,True\n1,\n2,True"

        result, target = self.run(tmp_path, data, "abc")

        assert bars(target) == [(1, 2), (2, 1)]
        assert result.notes == []

    def test_with_no_beat_nothing_is_grouped(self, tmp_path):
        result, target = self.run(tmp_path, "time\n", "abc")

        assert result.notes == []
        assert target.attrs["beat_pattern"] == "abc"

    def test_a_pattern_that_parses_gives_no_note(self, imported):
        result, _ = imported("time\n0\n1", beat_pattern="2")

        assert result.notes == []

    @pytest.mark.parametrize("attrs", [{}, {"beat_pattern": None}])
    def test_no_pattern_is_the_formats_default(self, tmp_path, attrs):
        path = tmp_path / "beats.csv"
        path.write_text("time\n0\n1\n2\n3\n4", encoding="utf-8")
        target = timeline("beat", attrs=attrs)
        doc = document(timelines=[target])

        result = beat.import_beats(doc, target.id, path)

        assert bars(target) == [(1, 4), (2, 1)]
        assert result.notes == []


class TestRowsNotImported:
    def test_a_time_that_isnt_one(self, imported):
        result, target = imported("time\n0\nabc\n2")

        assert messages(result) == [(3, "time", "abc is not a valid time.", True)]
        assert times(target) == [0, 2]
        assert result.rows == 3
        assert result.created == list(target.components)

    def test_an_empty_time(self, imported):
        result, target = imported("time,measure\n,5\n1,")

        assert messages(result) == [
            (2, "time", "an empty value is not a valid time.", True)
        ]
        assert times(target) == [1]

    def test_a_row_too_short_to_have_a_time(self, imported):
        result, target = imported("measure,time\n5\n,1")

        assert messages(result) == [
            (2, "time", "an empty value is not a valid time.", True)
        ]
        assert times(target) == [1]

    def test_a_time_of_nan_or_infinity_doesnt_upset_the_order(self, imported):
        result, target = imported("time\n1\nnan\n2\ninf\n3")

        assert messages(result) == [
            (3, "time", "nan is not a valid time.", True),
            (5, "time", "inf is not a valid time.", True),
        ]
        assert times(target) == [1, 2, 3]

    def test_two_beats_at_one_time(self, imported):
        result, target = imported("time\n0\n1\n1\n2")

        assert messages(result) == [
            (
                4,
                "time",
                "There is already a beat component at the selected position.",
                True,
            )
        ]
        assert times(target) == [0, 1, 2]

    def test_a_time_below_0_is_refused_not_out_of_order(self, imported):
        result, target = imported("time,measure\n-1,\n0,\n1,")

        assert messages(result) == [
            (2, "time", "Time can't be negative. Got '-00:01.0'", True)
        ]
        assert times(target) == [0, 1]
        assert sorted(marks(target)) == [0]

    def test_the_problems_are_in_row_order(self, imported):
        data = "time,denominator\n0,abc\nabc,\n2,xyz\n200,"

        result, _ = imported(data)

        assert [problem.line for problem in result.problems] == [2, 3, 4, 5]

    def test_a_skipped_row_isnt_counted_in_the_pattern(self, imported):
        result, target = imported("time\n0\nabc\n1\n2\n3\n4")

        assert bars(target) == [(1, 4), (2, 1)]
        assert sorted(marks(target)) == [0, 4]
        assert len(result.skipped) == 1

    def test_a_skipped_rows_number_is_left_out_of_the_pattern(self, imported):
        _, target = imported("time,measure\n0,\n1,\n1,9\n2,\n3,\n4,")

        assert bars(target) == [(1, 4), (2, 1)]
        assert forced(target) == []

    def test_a_skipped_downbeats_mark_moves_to_its_next_beat(self, imported):
        data = "time,is_first_in_measure,measure\n0,True,\n1,,\nabc,True,5\n3,,\n4,,\n5,True,"

        _, target = imported(data)

        assert bars(target) == [(1, 2), (5, 2), (6, 1)]
        assert forced(target) == [5]
        assert sorted(marks(target)) == [0, 3, 5]

    def test_a_downbeat_refused_by_the_rules_moves_its_mark_too(self, imported):
        data = "time,is_first_in_measure\n0,True\n1,\n1,True\n2,\n3,True"

        _, target = imported(data)

        assert bars(target) == [(1, 2), (2, 1), (3, 1)]
        assert sorted(marks(target)) == [0, 2, 3]

    def test_a_measure_with_no_beat_left_keeps_the_later_numbers(self, imported):
        _, target = imported(
            "time,is_first_in_measure\n0,True\nabc,True\n2,True\n3,True"
        )

        assert bars(target) == [(1, 1), (3, 1), (4, 1)]
        assert marks(target) == {0: {}, 2: {"number": 3}, 3: {}}
        assert forced(target) == []

    def test_a_measure_past_the_media_is_no_measure(self, imported):
        data = "time,is_first_in_measure\n0,True\n1,\n100,True\n101,"

        result, target = imported(data)

        assert bars(target) == [(1, 2)]
        assert target.attrs["beat_pattern"] == "2"
        assert [problem.line for problem in result.problems] == [4, 5]

    def test_the_first_beat_kept_has_the_first_mark(self, imported):
        _, target = imported("time,is_first_in_measure\nabc,True\n1,\n2,")

        assert bars(target) == [(1, 2)]
        assert sorted(marks(target)) == [1]

    def test_a_row_with_a_bad_number_keeps_its_downbeat(self, imported):
        data = "time,is_first_in_measure,measure\n0,True,\n1,True,abc\n2,,\n3,True,"

        result, target = imported(data)

        assert messages(result) == [(3, "measure", "abc is not a valid measure.", True)]
        assert bars(target) == [(1, 1), (2, 1), (3, 1)]

    def test_every_row_refused_leaves_no_beat(self, imported):
        result, target = imported("time\nabc\nxyz")

        assert not target.components
        assert target.measures.rows == []
        assert len(result.skipped) == 2


class TestOutOfOrder:
    @pytest.mark.parametrize(
        "data",
        ["time\n0\n2\n1", "time,measure\n0,\n2,\n1,", "time\n5\n-1\n6"],
    )
    def test_the_import_fails(self, imported, data):
        with pytest.raises(ImportFailed, match="not sorted in ascending order"):
            imported(data)

    def test_a_row_that_would_be_skipped_counts(self, imported):
        with pytest.raises(ImportFailed, match="not sorted"):
            imported("time,measure\n5,abc\n1,")

    def test_a_row_past_the_media_counts(self, imported):
        with pytest.raises(ImportFailed, match="not sorted"):
            imported("time\n200\n1")

    def test_str_names_the_file(self, imported):
        with pytest.raises(ImportFailed) as failed:
            imported("time\n2\n1")

        assert str(failed.value) == (
            "beats.csv: Time is not sorted in ascending order."
            " Please sort before importing."
        )


class TestImportFailed:
    @staticmethod
    def write(tmp_path, data=b"time\n0\n1"):
        path = tmp_path / "beats.csv"
        path.write_bytes(data)
        return path

    def test_no_time_column(self, tmp_path):
        target = timeline("beat")
        doc = document(timelines=[target])
        path = self.write(tmp_path, b"measure\n1")

        with pytest.raises(ImportFailed) as failed:
            beat.import_beats(doc, target.id, path)

        assert failed.value.message == (
            "Column 'time' not found on first row of .csv file."
        )

    def test_no_media_length(self, tmp_path):
        target = timeline("beat")
        doc = document(timelines=[target], media_length=None)

        with pytest.raises(ImportFailed) as failed:
            beat.import_beats(doc, target.id, self.write(tmp_path))

        assert failed.value.message == (
            "No media loaded and no duration set. Load a media file with 'load-media'"
            " or set a duration with 'metadata set-media-length'."
        )

    @pytest.mark.parametrize(
        "kwargs, name",
        [
            ({"name": "Phrases", "ordinal": 3}, "'Phrases'"),
            ({"ordinal": 3}, "3"),
        ],
    )
    def test_a_target_of_another_kind(self, tmp_path, kwargs, name):
        target = timeline("marker", **kwargs)
        doc = document(timelines=[target])

        with pytest.raises(ImportFailed) as failed:
            beat.import_beats(doc, target.id, self.write(tmp_path))

        assert failed.value.message == f"Timeline {name} is not a beat timeline"
        assert not target.components

    def test_a_kind_the_core_doesnt_know_spelled_as_beat(self, tmp_path):
        target = timeline(UnknownKind("beat"))
        doc = document(timelines=[target])

        with pytest.raises(ImportFailed, match="is not a beat timeline"):
            beat.import_beats(doc, target.id, self.write(tmp_path))

    def test_an_id_the_document_doesnt_have(self, tmp_path):
        doc = document()

        with pytest.raises(ImportFailed) as failed:
            beat.import_beats(doc, "nope", self.write(tmp_path))

        assert failed.value.message == "No timeline found with id=nope"

    @pytest.mark.parametrize(
        "data",
        [
            b"",  # empty
            b"\xff\xfetime\n0",  # not UTF-8
            b"measure\n1",  # no time column
            b"time\n2\n1",  # out of order
            b'time\n"' + b"1" * 200_000 + b'"',  # over the csv module's field limit
        ],
    )
    def test_a_failed_import_changes_nothing(self, tmp_path, data):
        doc = document()
        target = doc.timelines[
            build.add_timeline(doc, "beat", "Measures", beat_pattern="3")
        ]
        beat.import_beats(doc, target.id, self.write(tmp_path, b"time\n0\n1\n2\n3"))
        before = copy.deepcopy(target)

        with pytest.raises(ImportFailed):
            beat.import_beats(doc, target.id, self.write(tmp_path, data))

        assert target == before

    def test_a_file_that_cant_be_opened_changes_nothing(self, tmp_path):
        target = timeline("beat")
        doc = document(timelines=[target])
        before = copy.deepcopy(target)

        with pytest.raises(OSError):
            beat.import_beats(doc, target.id, tmp_path / "none.csv")

        assert target == before


class TestReplacing:
    def test_a_second_import_replaces_the_first(self, tmp_path):
        doc = document()
        target = doc.timelines[build.add_timeline(doc, "beat", "Measures")]
        first = tmp_path / "first.csv"
        first.write_text("time,measure\n0,9\n1,\n2,\n3,\n4,", encoding="utf-8")
        second = tmp_path / "second.csv"
        second.write_text("time\n10\n11", encoding="utf-8")

        beat.import_beats(doc, target.id, first)
        result = beat.import_beats(doc, target.id, second)

        assert times(target) == [10, 11]
        assert bars(target) == [(1, 2)]
        assert [row.id for row in target.measures.rows] == [result.created[0]]

    def test_a_component_of_a_kind_the_core_doesnt_know_stays(self, tmp_path):
        note = tla.Component(id="note", kind=UnknownKind("NOTE"), attrs={"time": 5})
        target = timeline("beat", components=[note, component("beat", time=20.0)])
        doc = document(timelines=[target])
        path = tmp_path / "beats.csv"
        path.write_text("time\n0\n1", encoding="utf-8")

        result = beat.import_beats(doc, target.id, path)

        assert list(target.components) == ["note", *result.created]
        assert target.components["note"] is note
        assert [row.beats for row in target.measures.rows] == [result.created]


class TestTheMeasureTable:
    def test_a_by_measure_import_finds_its_time_map_without_a_file(self, tmp_path):
        doc = build.new_script_document()
        build.set_media_length(doc, 60.0)
        target = build.add_timeline(doc, "beat", "Measures")
        path = tmp_path / "beats.csv"
        path.write_text("time\n0\n1\n2\n3\n4\n5\n6\n7", encoding="utf-8")

        beat.import_beats(doc, target, path)

        time_map = time_map_for(doc, target)
        assert time_map is not None
        assert time_map.times_of(2, 0.5) == [6.0]

    def test_a_repeated_number_gives_one_time_per_pass(self, tmp_path):
        doc = build.new_script_document()
        build.set_media_length(doc, 60.0)
        target = build.add_timeline(doc, "beat", "Measures", beat_pattern="2")
        path = tmp_path / "beats.csv"
        path.write_text(
            "time,measure\n0,1\n1,\n2,2\n3,\n4,1\n5,\n6,2\n7,", encoding="utf-8"
        )

        beat.import_beats(doc, target, path)

        assert time_map_for(doc, target).times_of(2, 0.0) == [2.0, 6.0]

    def test_the_table_is_the_same_after_writing_and_reading(self, tmp_path):
        doc = build.new_script_document()
        build.set_media_length(doc, 60.0)
        target = build.add_timeline(doc, "beat", "Measures")
        path = tmp_path / "beats.csv"
        path.write_text(
            "time,is_first_in_measure,measure,denominator,units\n"
            "0,True,0,4,1\n"
            "1,True,,,\n"
            "2,,,,\n"
            "3,,,,\n"
            "4,True,,8,3\n"
            "5,,,,\n"
            "6,True,1,,\n"
            "7,,,,\n",
            encoding="utf-8",
        )

        beat.import_beats(doc, target, path)
        read = tla.loads(tla.canonical_bytes(doc))

        assert read.warnings == []
        assert read.timelines[target].measures == doc.timelines[target].measures
        assert read.timelines[target].attrs == doc.timelines[target].attrs
        assert [row.number for row in read.timelines[target].measures.rows] == [
            0,
            1,
            2,
            1,
        ]

    def test_the_file_holds_only_the_numbers_that_dont_follow(self, tmp_path):
        doc = build.new_script_document()
        build.set_media_length(doc, 60.0)
        target = build.add_timeline(doc, "beat", "Measures", beat_pattern="1")
        path = tmp_path / "beats.csv"
        path.write_text("time,measure\n0,0\n1,\n2,\n3,7\n", encoding="utf-8")

        beat.import_beats(doc, target, path)

        written = json.loads(tla.canonical_bytes(doc))
        beats = written["timelines"][target]["components"].values()
        assert [one["measure"] for one in beats] == [
            {"number": 0, "force_display": True},
            {},
            {},
            {"number": 7, "force_display": True},
        ]


def test_the_beats_are_checked_once(imported, monkeypatch):
    calls = []
    check_timeline = rules.check_timeline

    def counted(*args, **kwargs):
        calls.append(args)
        return check_timeline(*args, **kwargs)

    monkeypatch.setattr(rules, "check_timeline", counted)

    imported("time\n0\n1\n2")

    assert len(calls) == 1


def test_a_quarters_document_reads_times_as_they_are(imported):
    result, target = imported(
        "time\n2.5\n16\n16.5", media_length=16, time_unit="quarters"
    )

    assert times(target) == [2.5, 16]
    assert [problem.line for problem in result.problems] == [4]


def test_a_byte_order_mark_doesnt_hide_the_first_column(tmp_path):
    path = tmp_path / "beats.csv"
    path.write_bytes(b"\xef\xbb\xbftime\n0\n")
    target = timeline("beat")
    doc = document(timelines=[target])

    beat.import_beats(doc, target.id, path)

    assert times(target) == [0]


def test_importers_exports_it():
    assert importers.import_beats is beat.import_beats
    assert "import_beats" in importers.__all__
