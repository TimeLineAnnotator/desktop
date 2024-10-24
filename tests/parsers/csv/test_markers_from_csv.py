import os
from pathlib import Path
from unittest.mock import patch, mock_open

from tests.parsers.csv.common import assert_in_errors
from tilia.parsers.csv.marker import (
    import_by_time,
    import_by_measure,
)
from tilia.ui.format import format_media_time


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

    with patch("builtins.open", mock_open(read_data=data)):
        import_by_measure(
            marker_tl,
            beat_tl,
            Path("parsers", "test_markers_by_measure_from_csv.csv").resolve(),
        )

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

    with patch("builtins.open", mock_open(read_data=data)):
        import_by_measure(marker_tl, beat_tl, Path())

    markers = sorted(marker_tl)

    assert markers[0].time == 1
    assert markers[1].time == 2
    assert markers[2].time == 3


def test_markers_by_measure_from_csv_fails_if_no_measure_column(beat_tlui, marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "label,comments\nfirst,a\nsecond,b\nthird,c"

    with patch("builtins.open", mock_open(read_data=data)):
        import_by_measure(
            beat_tlui.timeline,
            marker_tlui.timeline,
            Path("parsers", "test_markers_from_csv_raises_error.csv").resolve(),
        )

    assert marker_tlui.is_empty


def test_markers_by_time_from_csv(marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time,label,comments\n1,first,a\n5,second,b\n10,third,c"

    with patch("builtins.open", mock_open(read_data=data)):
        import_by_time(
            marker_tlui.timeline,
            Path("parsers", "test_markers_by_time_from_csv.csv").resolve(),
        )

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

    with patch("builtins.open", mock_open(read_data=data)):
        import_by_time(
            marker_tlui.timeline,
            Path(),
        )

    assert marker_tlui.is_empty


def test_markers_by_time_from_csv_outputs_error_if_bad_time_value(marker_tlui):
    data = "time\nnonsense"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = import_by_time(marker_tlui.timeline, Path())

    assert "nonsense" in errors[0]


def test_markers_by_time_from_csv_outputs_error_if_time_out_of_bound(
    marker_tlui, tilia_state
):
    tilia_state.duration = 100
    data = "time\n999"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = import_by_time(marker_tlui.timeline, Path())

    assert format_media_time(999) in errors[0]


def test_markers_by_measure_from_csv_outputs_error_if_bad_measure_value(
    marker_tlui, beat_tlui
):
    data = "measure\nnonsense"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = import_by_measure(marker_tlui.timeline, beat_tlui.timeline, Path())

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
    with patch("builtins.open", mock_open(read_data=data)):
        errors = import_by_measure(marker_tlui.timeline, beat_tlui.timeline, Path())

    assert "nonsense" in errors[0]

    assert sorted(marker_tl)[0].time == 1


def test_component_creation_fail_reason_gets_into_errors(
    marker_tl, beat_tlui, tilia_state
):

    tilia_state.duration = 100
    data = "time\n101"

    with patch("builtins.open", mock_open(read_data=data)):
        errors = import_by_time(
            marker_tl,
            Path(),
        )

    assert_in_errors(format_media_time(101), errors)
