import os
from pathlib import Path
from typing import Literal
from unittest.mock import patch, mock_open

from PyQt6.QtWidgets import QFileDialog

from tests.parsers.csv.common import assert_in_errors
from tilia.ui import actions
from tilia.ui.actions import TiliaAction
from tilia.ui.format import format_media_time
from tilia.ui.ui_import import on_import_to_timeline


def patch_import(by: Literal["time", "measure"], tl, data) -> tuple[str, list[str]]:
    status = ""
    errors = []

    def mock_import(timeline_uis, tlkind):
        nonlocal status, errors
        status, errors = on_import_to_timeline(timeline_uis, tlkind)
        return status, errors

    with (
        patch(
            "tilia.ui.ui_import._get_by_time_or_by_measure_from_user",
            return_value=(True, by),
        ),
        patch.object(QFileDialog, "exec", return_value=True),
        patch.object(QFileDialog, "selectedFiles", return_value=[Path()]),
        patch("tilia.ui.qtui.on_import_to_timeline", side_effect=mock_import),
        patch("builtins.open", mock_open(read_data=data)),
    ):
        actions.trigger(TiliaAction.IMPORT_CSV_MARKER_TIMELINE)
    return status, errors


def test_markers_by_measure_from_csv(beat_tlui, marker_tlui):
    beat_tl = beat_tlui.timeline
    marker_tl = marker_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)
    beat_tlui.create_beat(time=3)
    beat_tlui.create_beat(time=4)

    beat_tl.recalculate_measures()

    data = "measure,fraction,label,comments\n1,0,first,a\n2,0.5,second,b\n3,1,third,c"

    patch_import("measure", marker_tl, data)

    assert marker_tl[0].time == 1
    assert marker_tl[1].time == 2.5
    assert marker_tl[2].time == 4


def test_markers_by_measure_from_csv_multiple_measures_with_number(
    beat_tlui, marker_tlui
):
    beat_tl = beat_tlui.timeline
    marker_tl = marker_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)
    beat_tlui.create_beat(time=3)

    beat_tl.measure_numbers = [1, 1, 1]

    beat_tl.recalculate_measures()

    data = "measure\n1"

    patch_import("measure", marker_tl, data)

    assert marker_tl[0].time == 1
    assert marker_tl[1].time == 2
    assert marker_tl[2].time == 3


def test_markers_by_measure_from_csv_fails_if_no_measure_column(beat_tlui, marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "label,comments\nfirst,a\nsecond,b\nthird,c"

    patch_import("measure", marker_tlui.timeline, data)

    assert marker_tlui.is_empty


def test_markers_by_time_from_csv(marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time,label,comments\n1,first,a\n5,second,b\n10,third,c"
    marker_tl = marker_tlui.timeline
    patch_import("time", marker_tl, data)

    assert marker_tl[0].time == 1
    assert marker_tl[0].label == "first"
    assert marker_tl[0].comments == "a"

    assert marker_tl[1].time == 5
    assert marker_tl[1].label == "second"
    assert marker_tl[1].comments == "b"

    assert marker_tl[2].time == 10
    assert marker_tl[2].label == "third"
    assert marker_tl[2].comments == "c"


def test_markers_by_time_from_csv_fails_if_no_time_column(marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "label,comments\nfirst,a\nsecond,b\nthird,c"

    patch_import("time", marker_tlui.timeline, data)

    assert marker_tlui.is_empty


def test_markers_by_time_from_csv_outputs_error_if_bad_time_value(marker_tlui):
    data = "time\nnonsense"

    status, errors = patch_import("time", marker_tlui.timeline, data)

    assert status == "success"
    assert_in_errors("nonsense", errors)


def test_markers_by_time_from_csv_outputs_error_if_time_out_of_bound(
    marker_tlui, tilia_state
):
    tilia_state.duration = 100
    data = "time\n999"

    status, errors = patch_import("time", marker_tlui.timeline, data)

    assert status == "success"
    assert format_media_time(999) in errors[0]


def test_markers_by_measure_from_csv_outputs_error_if_bad_measure_value(
    marker_tlui, beat_tlui
):
    data = "measure\nnonsense"
    status, errors = patch_import("measure", marker_tlui.timeline, data)

    assert status == "success"
    assert_in_errors("nonsense", errors)


def test_markers_by_measure_from_csv_outputs_error_if_bad_fraction_value(
    marker_tlui, beat_tlui
):
    beat_tl = beat_tlui.timeline
    marker_tl = marker_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)

    data = "measure,fraction\n1,nonsense"
    status, errors = patch_import("measure", marker_tl, data)

    assert status == "success"
    assert_in_errors("nonsense", errors)

    assert marker_tl[0].time == 1


def test_component_creation_fail_reason_gets_into_errors(
    marker_tl, beat_tlui, tilia_state
):

    tilia_state.duration = 100
    data = "time\n101"

    status, errors = patch_import("time", marker_tl, data)

    assert_in_errors(format_media_time(101), errors)
