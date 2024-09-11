import os
from pathlib import Path

from tests.parsers.csv.common import assert_in_errors, call_patched_import_by_measure_func, \
    call_patched_import_by_time_func


def test_markers_by_measure_from_csv(beat_tlui, marker_tlui):
    beat_tl = beat_tlui.timeline
    marker_tl = marker_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)
    beat_tlui.create_beat(time=3)
    beat_tlui.create_beat(time=4)

    beat_tl.recalculate_measures()

    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "measure,fraction,label,comments\n1,0,first,a\n2,0.5,second,b\n3,1,third,c"

    call_patched_import_by_measure_func(marker_tl, beat_tl, data)
    markers = sorted(marker_tl)

    assert markers[0].time == 1
    assert markers[1].time == 2.5
    assert markers[2].time == 4


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

    call_patched_import_by_measure_func(marker_tl, beat_tl, data)

    markers = sorted(marker_tl)

    assert markers[0].time == 1
    assert markers[1].time == 2
    assert markers[2].time == 3


def test_markers_by_measure_from_csv_fails_if_no_measure_column(beat_tlui, marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "label,comments\nfirst,a\nsecond,b\nthird,c"

    call_patched_import_by_measure_func(marker_tlui.timeline, beat_tlui.timeline, data)
    assert marker_tlui.is_empty


def test_markers_by_time_from_csv(marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time,label,comments\n1,first,a\n5,second,b\n10,third,c"

    call_patched_import_by_time_func(marker_tlui.timeline, data)
    markers = sorted(marker_tlui.timeline)

    assert markers[0].time == 1
    assert markers[0].label == "first"
    assert markers[0].comments == "a"

    assert markers[1].time == 5
    assert markers[1].label == "second"
    assert markers[1].comments == "b"

    assert markers[2].time == 10
    assert markers[2].label == "third"
    assert markers[2].comments == "c"


def test_markers_by_time_from_csv_fails_if_no_time_column(marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "label,comments\nfirst,a\nsecond,b\nthird,c"

    call_patched_import_by_time_func(marker_tlui.timeline, data)

    assert marker_tlui.is_empty


def test_markers_by_time_from_csv_outputs_error_if_bad_time_value(marker_tlui):
    data = "time\nnonsense"
    errors = call_patched_import_by_time_func(marker_tlui.timeline, data)

    assert "nonsense" in errors[0]


def test_markers_by_time_from_csv_outputs_error_if_time_out_of_bound(
    marker_tlui, tilia_state
):
    tilia_state.duration = 100
    data = "time\n999"
    errors = call_patched_import_by_time_func(marker_tlui.timeline, data)

    assert "999" in errors[0]


def test_markers_by_measure_from_csv_outputs_error_if_bad_measure_value(
    marker_tlui, beat_tlui
):
    data = "measure\nnonsense"
    errors = call_patched_import_by_measure_func(marker_tlui.timeline, beat_tlui.timeline, data)

    assert "nonsense" in errors[0]


def test_markers_by_measure_from_csv_outputs_error_if_bad_fraction_value(
    marker_tlui, beat_tlui
):
    beat_tl = beat_tlui.timeline
    marker_tl = marker_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)

    data = "measure,fraction\n1,nonsense"
    errors = call_patched_import_by_measure_func(marker_tl, beat_tl, data)

    assert "nonsense" in errors[0]

    assert sorted(marker_tl)[0].time == 1


def test_component_creation_fail_reason_gets_into_errors(
    marker_tl, beat_tlui, tilia_state
):

    tilia_state.duration = 100
    data = "time\n101"

    errors = call_patched_import_by_time_func(marker_tl, data)

    assert_in_errors("101", errors)
