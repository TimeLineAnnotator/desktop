from pathlib import Path
from typing import Literal
from unittest.mock import mock_open, patch

import pytest
from PySide6.QtWidgets import QFileDialog

from tests.mock import Serve
from tilia.parsers.csv.range import import_by_measure, import_by_time
from tilia.requests import Get, Post, post
from tilia.ui import commands


def _trigger_import_through_command(by: Literal["time", "measure"], data):
    """Run the `timelines.import.range` command, patching every interactive
    dialog the import flow consults so it executes headlessly. Returns
    `(success, errors)` — errors are captured from `tilia.errors.display`
    calls the import flow makes when validation fails or partially succeeds."""
    post(Post.APP_STATE_RECORD, "test state")
    errors: list[str] = []

    def capture(_error_kind, message):
        errors.extend(message.split("\n"))

    with (
        Serve(Get.FROM_USER_YES_OR_NO, True),
        patch(
            "tilia.ui.timelines.collection.import_."
            "_get_by_time_or_by_measure_from_user",
            return_value=(True, by),
        ),
        patch.object(QFileDialog, "exec", return_value=True),
        patch.object(QFileDialog, "selectedFiles", return_value=[Path()]),
        patch("builtins.open", mock_open(read_data=data)),
        patch("tilia.errors.display", side_effect=capture),
    ):
        success = commands.execute("timelines.import.range")
    return success, errors


@pytest.fixture
def populated_beat_tl(beat_tlui):
    beat_tl = beat_tlui.timeline
    beat_tl.beat_pattern = [1]
    for t in (1, 2, 3, 4, 5):
        beat_tlui.create_beat(time=t)
    beat_tl.recalculate_measures()
    return beat_tl


class TestImportByTime:
    def test_basic(self, range_tlui):
        data = "start,end,row,label\n0,1,RowA,first\n1,2,RowB,second"
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert errors == []
        assert range_tlui[0].get_data("start") == 0
        assert range_tlui[0].get_data("end") == 1
        assert range_tlui[0].get_data("label") == "first"
        assert range_tlui[1].get_data("label") == "second"

    def test_auto_creates_rows_by_name(self, range_tlui):
        data = "start,end,row\n0,1,Verses\n1,2,Choruses"
        _trigger_import_through_command("time", data)
        names = [r.name for r in range_tlui.timeline.rows]
        assert "Verses" in names
        assert "Choruses" in names

    def test_reuses_row_for_duplicate_name(self, range_tlui):
        data = "start,end,row\n0,1,Existing\n1,2,Existing"
        _trigger_import_through_command("time", data)
        rows = range_tlui.timeline.rows
        # Two CSV entries with the same row name produce a single row.
        assert len([r for r in rows if r.name == "Existing"]) == 1
        existing = next(r for r in rows if r.name == "Existing")
        assert all(e.get_data("row_id") == existing.id for e in range_tlui)

    def test_propagates_color_and_comments(self, range_tlui):
        data = (
            "start,end,row,color,comments\n"
            "0,1,A,#abcdef,note one\n"
            "1,2,A,,note two"
        )
        _trigger_import_through_command("time", data)
        assert range_tlui[0].get_data("color") == "#abcdef"
        assert range_tlui[0].get_data("comments") == "note one"
        assert range_tlui[1].get_data("color") is None
        assert range_tlui[1].get_data("comments") == "note two"

    def test_missing_required_column_fails(self, range_tlui):
        data = "start,end,label\n0,1,first"
        success, errors = _trigger_import_through_command("time", data)
        assert success is False
        assert "row" in errors[0]

    def test_bad_start_value_yields_error(self, range_tlui):
        data = "start,end,row\nnonsense,1,A"
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert any("nonsense" in e for e in errors)
        assert len(range_tlui) == 0

    def test_bad_end_value_yields_error(self, range_tlui):
        data = "start,end,row\n0,nonsense,A"
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert any("nonsense" in e for e in errors)
        assert len(range_tlui) == 0

    def test_empty_row_name_skipped(self, range_tlui):
        data = "start,end,row\n0,1,\n1,2,A"
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert any("row name is empty" in e for e in errors)
        assert len(range_tlui) == 1

    def test_skips_blank_lines(self, range_tlui):
        data = "start,end,row\n0,1,A\n\n2,3,A"
        _trigger_import_through_command("time", data)
        assert len(range_tlui) == 2


class TestImportByMeasure:
    def test_basic(self, range_tlui, populated_beat_tl):
        data = "start,end,row,label\n1,2,A,first\n3,4,B,second"
        success, errors = _trigger_import_through_command("measure", data)
        assert success
        assert errors == []
        assert range_tlui[0].get_data("start") == 1
        assert range_tlui[0].get_data("end") == 2
        assert range_tlui[0].get_data("label") == "first"
        assert range_tlui[1].get_data("start") == 3
        assert range_tlui[1].get_data("end") == 4
        assert range_tlui[1].get_data("label") == "second"

    def test_auto_creates_rows(self, range_tlui, populated_beat_tl):
        data = "start,end,row\n1,2,Verses\n3,4,Choruses"
        _trigger_import_through_command("measure", data)
        names = [r.name for r in range_tlui.timeline.rows]
        assert "Verses" in names
        assert "Choruses" in names

    def test_with_fractions(self, range_tlui, populated_beat_tl):
        data = "start,end,start_fraction,end_fraction,row\n1,2,0.5,0.5,A"
        _trigger_import_through_command("measure", data)
        assert len(range_tlui) == 1
        # Beats at 1,2 → measure 1 starts at 1, measure 2 starts at 2;
        # fraction 0.5 within measure 1 (length 1) gives 1.5; within
        # measure 2 (length 1, end-side) gives 2.5.
        assert range_tlui[0].get_data("start") == 1.5
        assert range_tlui[0].get_data("end") == 2.5

    def test_missing_required_column_fails(self, range_tlui, populated_beat_tl):
        data = "start,end,label\n1,2,A"
        success, errors = _trigger_import_through_command("measure", data)
        assert success is False
        assert "row" in errors[0]

    def test_bad_start_value_yields_error(self, range_tlui, populated_beat_tl):
        data = "start,end,row\nnonsense,2,A"
        success, errors = _trigger_import_through_command("measure", data)
        assert success
        assert any("nonsense" in e for e in errors)

    def test_bad_fraction_value_yields_error(self, range_tlui, populated_beat_tl):
        data = "start,end,start_fraction,row\n1,2,nonsense,A"
        success, errors = _trigger_import_through_command("measure", data)
        assert success
        assert any("nonsense" in e for e in errors)
        # Despite the bad fraction the range is still created with fraction=0.
        assert len(range_tlui) == 1

    def test_unknown_measure_yields_error(self, range_tlui, populated_beat_tl):
        data = "start,end,row\n99,100,A"
        success, errors = _trigger_import_through_command("measure", data)
        assert success
        assert any("99" in e for e in errors)
        assert len(range_tlui) == 0


class TestImportReplacesExistingRows:
    def test_drops_pre_existing_rows(self, range_tlui):
        commands.execute("timeline.range.add_row", name="OldRow")
        commands.execute("timeline.range.add_range", start=0, end=1)

        data = "start,end,row\n0,1,Verses\n1,2,Choruses"
        _trigger_import_through_command("time", data)

        names = [r.name for r in range_tlui.timeline.rows]
        assert "OldRow" not in names
        assert names == ["Verses", "Choruses"]

    def test_creates_default_row_when_import_yields_none(self, range_tlui):
        commands.execute("timeline.range.add_row", name="OldRow")
        commands.execute("timeline.range.add_range", start=0, end=1)

        # All CSV rows fail validation (empty row name) → zero rows imported.
        data = "start,end,row\n0,1,\n1,2,"
        _trigger_import_through_command("time", data)

        rows = range_tlui.timeline.rows
        assert len(rows) == 1
        assert rows[0].name  # any non-empty default name


class TestJoinedWithNextByTime:
    def test_basic_join(self, range_tlui):
        data = "start,end,row,joined_with_next\n0,1,A,true\n1,2,A,false"
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert errors == []
        assert range_tlui[0].get_data("joined_right") == range_tlui[1].id
        assert range_tlui[1].get_data("joined_right") is None

    def test_chain_of_three(self, range_tlui):
        data = (
            "start,end,row,joined_with_next\n"
            "0,1,A,true\n"
            "1,2,A,true\n"
            "2,3,A,false"
        )
        _trigger_import_through_command("time", data)
        assert range_tlui[0].get_data("joined_right") == range_tlui[1].id
        assert range_tlui[1].get_data("joined_right") == range_tlui[2].id
        assert range_tlui[2].get_data("joined_right") is None

    def test_join_only_within_same_row(self, range_tlui):
        # A.next is true but the next CSV entry lives on a different row;
        # the join should hop to the next A entry, not the B entry.
        data = (
            "start,end,row,joined_with_next\n"
            "0,1,A,true\n"
            "0,1,B,false\n"
            "1,2,A,false"
        )
        _trigger_import_through_command("time", data)
        rows = range_tlui.timeline.rows
        row_a = next(r for r in rows if r.name == "A")
        row_b = next(r for r in rows if r.name == "B")
        a_elems = [e for e in range_tlui if e.get_data("row_id") == row_a.id]
        b_elems = [e for e in range_tlui if e.get_data("row_id") == row_b.id]
        assert a_elems[0].get_data("joined_right") == a_elems[1].id
        assert b_elems[0].get_data("joined_right") is None

    def test_default_is_unjoined(self, range_tlui):
        data = "start,end,row\n0,1,A\n1,2,A"
        _trigger_import_through_command("time", data)
        for e in range_tlui:
            assert e.get_data("joined_right") is None

    def test_join_target_uses_temporal_order_not_csv_order(self, range_tlui):
        # CSV is *not* sorted by start. The flagged range (start=0) must
        # join to the start=1 range, not whichever happens to come next
        # in the CSV.
        data = "start,end,row,joined_with_next\n" "1,2,A,false\n" "0,1,A,true\n"
        _trigger_import_through_command("time", data)
        assert range_tlui[0].get_data("joined_right") == range_tlui[1].id
        assert range_tlui[1].get_data("joined_right") is None

    def test_invalid_boolean_reports_error(self, range_tlui):
        data = "start,end,row,joined_with_next\n0,1,A,maybe\n1,2,A,false"
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert any("joined_with_next" in e and "maybe" in e for e in errors)
        assert range_tlui[0].get_data("joined_right") is None


class TestJoinedWithNextByMeasure:
    def test_basic_join(self, range_tlui, populated_beat_tl):
        data = "start,end,row,joined_with_next\n1,2,A,true\n2,3,A,false"
        success, errors = _trigger_import_through_command("measure", data)
        assert success
        assert errors == []
        assert range_tlui[0].get_data("joined_right") == range_tlui[1].id


class TestJoinValidation:
    def test_flag_on_last_range_reports_error(self, range_tlui):
        data = "start,end,row,joined_with_next\n0,1,A,false\n1,2,A,true"
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert any("last range" in e and "'A'" in e for e in errors)
        # Ranges still created; only the join is dropped.
        assert len(range_tlui) == 2
        assert range_tlui[-1].get_data("joined_right") is None

    def test_gap_between_joined_ranges_reports_error(self, range_tlui):
        data = "start,end,row,joined_with_next\n0,10,A,true\n20,30,A,false"
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert any("must equal" in e for e in errors)
        assert range_tlui[0].get_data("joined_right") is None

    def test_overlap_between_joined_ranges_reports_error(self, range_tlui):
        data = "start,end,row,joined_with_next\n0,10,A,true\n5,15,A,false"
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert any("must equal" in e for e in errors)
        assert range_tlui[0].get_data("joined_right") is None

    def test_only_invalid_join_is_dropped(self, range_tlui):
        # Three ranges on row A: 0→10 (true, ok), 10→20 (true, gap follows),
        # 30→40 (false). Only the second join is invalid.
        data = (
            "start,end,row,joined_with_next\n"
            "0,10,A,true\n"
            "10,20,A,true\n"
            "30,40,A,false"
        )
        success, errors = _trigger_import_through_command("time", data)
        assert success
        assert len(errors) == 1
        assert range_tlui[0].get_data("joined_right") == range_tlui[1].id
        assert range_tlui[1].get_data("joined_right") is None
        assert range_tlui[2].get_data("joined_right") is None

    def test_validation_runs_under_measure_mode(self, range_tlui, populated_beat_tl):
        # Beat fixture creates beats at 1..5 → measures 1..5; measures 1 and
        # 4 leave a gap, so a flagged join across them should fail.
        data = "start,end,row,joined_with_next\n1,2,A,true\n4,5,A,false"
        success, errors = _trigger_import_through_command("measure", data)
        assert success
        assert any("must equal" in e for e in errors)
        assert range_tlui[0].get_data("joined_right") is None


class TestParserDispatch:
    def test_dispatch_by_time(self):
        from tilia.parsers import get_import_function
        from tilia.timelines.range.timeline import RangeTimeline

        assert get_import_function(RangeTimeline, "time") is import_by_time

    def test_dispatch_by_measure(self):
        from tilia.parsers import get_import_function
        from tilia.timelines.range.timeline import RangeTimeline

        assert get_import_function(RangeTimeline, "measure") is import_by_measure
