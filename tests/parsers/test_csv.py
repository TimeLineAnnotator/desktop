import os
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
from tilia.parsers.csv import (
    get_params_indices,
    markers_by_measure_from_csv,
    markers_by_time_from_csv,
    hierarchies_by_measure_from_csv,
    hierarchies_by_time_from_csv,
)


def test_get_params_columns():
    headers = ["_", "h1", "h2", "_", "h3"]
    expected = {"h1": 1, "h2": 2, "h3": 4}

    assert get_params_indices(["h1", "h2"], []) == {}
    assert get_params_indices(["h1", "h2", "h3"], headers) == expected
    assert get_params_indices(["_"], headers) == {"_": 0}
    assert get_params_indices(["notthere"], headers) == {}


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
        markers_by_measure_from_csv(
            marker_tl,
            beat_tl,
            Path("parsers", "test_markers_by_measure_from_csv.csv").resolve(),
        )

    markers = marker_tl.ordered_markers

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
        markers_by_measure_from_csv(marker_tl, beat_tl, Path())

    markers = marker_tl.ordered_markers

    assert markers[0].time == 1
    assert markers[1].time == 2
    assert markers[2].time == 3


def test_markers_by_measure_from_csv_raises_error_if_no_measure_column(
    beat_tlui, marker_tlui
):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "label,comments\nfirst,a\nsecond,b\nthird,c"

    with patch("builtins.open", mock_open(read_data=data)):
        with pytest.raises(ValueError):
            markers_by_measure_from_csv(
                beat_tlui.timeline,
                marker_tlui.timeline,
                Path("parsers", "test_markers_from_csv_raises_error.csv").resolve(),
            )


def test_markers_by_time_from_csv(marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time,label,comments\n1,first,a\n5,second,b\n10,third,c"

    with patch("builtins.open", mock_open(read_data=data)):
        markers_by_time_from_csv(
            marker_tlui.timeline,
            Path("parsers", "test_markers_by_time_from_csv.csv").resolve(),
        )

    markers = marker_tlui.timeline.ordered_markers

    assert markers[0].time == 1
    assert markers[0].label == "first"
    assert markers[0].comments == "a"

    assert markers[1].time == 5
    assert markers[1].label == "second"
    assert markers[1].comments == "b"

    assert markers[2].time == 10
    assert markers[2].label == "third"
    assert markers[2].comments == "c"


def test_markers_by_time_from_csv_raises_error_if_no_time_column(marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "label,comments\nfirst,a\nsecond,b\nthird,c"

    with patch("builtins.open", mock_open(read_data=data)):
        with pytest.raises(ValueError):
            markers_by_time_from_csv(
                marker_tlui.timeline,
                Path("parsers", "test_markers_from_csv_raises_error.csv").resolve(),
            )


def test_markers_by_time_from_csv_outputs_error_if_bad_time_value(marker_tlui):
    data = "time\nnonsense"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = markers_by_time_from_csv(marker_tlui.timeline, Path())

    assert "nonsense" in errors[0]


def test_markers_by_measure_from_csv_outputs_error_if_bad_measure_value(
    marker_tlui, beat_tlui
):
    data = "measure\nnonsense"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = markers_by_measure_from_csv(
            marker_tlui.timeline, beat_tlui.timeline, Path()
        )

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
        errors = markers_by_measure_from_csv(
            marker_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]

    assert marker_tl.ordered_markers[0].time == 1


def test_hierarchies_by_time_from_csv(hierarchy_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "start,end,level,label\n0,1,1,first\n1,2,2,second\n2,3,3,third"

    with patch("builtins.open", mock_open(read_data=data)):
        hierarchies_by_time_from_csv(
            hierarchy_tlui.timeline,
            Path("parsers", "test_markers_by_time_from_csv.csv").resolve(),
        )

    hierarchies = hierarchy_tlui.timeline.ordered_hierarchies

    assert hierarchies[0].start == 0
    assert hierarchies[0].end == 1
    assert hierarchies[0].level == 1
    assert hierarchies[0].label == "first"

    assert hierarchies[1].start == 1
    assert hierarchies[1].end == 2
    assert hierarchies[1].level == 2
    assert hierarchies[1].label == "second"

    assert hierarchies[2].start == 2
    assert hierarchies[2].end == 3
    assert hierarchies[2].level == 3
    assert hierarchies[2].label == "third"


def test_hierarchies_by_measure_from_csv(beat_tlui, hierarchy_tlui):
    beat_tl = beat_tlui.timeline
    hierarchy_tl = hierarchy_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)
    beat_tlui.create_beat(time=3)
    beat_tlui.create_beat(time=4)

    beat_tl.recalculate_measures()

    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "start,end,level,label\n1,2,1,a\n2,3,2,b\n3,4,3,c"

    with patch("builtins.open", mock_open(read_data=data)):
        hierarchies_by_measure_from_csv(
            hierarchy_tl,
            beat_tl,
            Path(),
        )

    hierarchies = hierarchy_tl.ordered_hierarchies

    assert hierarchies[0].start == 1
    assert hierarchies[0].end == 2
    assert hierarchies[0].level == 1
    assert hierarchies[0].label == "a"

    assert hierarchies[1].start == 2
    assert hierarchies[1].end == 3
    assert hierarchies[1].level == 2
    assert hierarchies[1].label == "b"

    assert hierarchies[2].start == 3
    assert hierarchies[2].end == 4
    assert hierarchies[2].level == 3
    assert hierarchies[2].label == "c"


def test_hierarchies_by_measure_from_csv_outputs_error_if_bad_start_value(
    hierarchy_tlui, beat_tlui
):
    data = "start,end,level\nnonsense, 1, 1"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = hierarchies_by_measure_from_csv(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]


def test_hierarchies_by_measure_from_csv_outputs_error_if_bad_end_value(
    hierarchy_tlui, beat_tlui
):
    data = "start,end,level\n1, nonsense, 1"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = hierarchies_by_measure_from_csv(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]


def test_hierarchies_by_measure_from_csv_outputs_error_if_bad_level_value(
    hierarchy_tlui, beat_tlui
):
    data = "start,end,level\n1, 1, nonsense"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = hierarchies_by_measure_from_csv(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]


def test_hierarchies_by_measure_from_csv_outputs_error_if_bad_start_fraction_value(
    hierarchy_tlui, beat_tlui
):
    beat_tl = beat_tlui.timeline
    hierarchy_tl = hierarchy_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)

    data = "start,start_fraction,end,level\n1,nonsense, 2, 1"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = hierarchies_by_measure_from_csv(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]

    assert hierarchy_tl.ordered_hierarchies[0].start == 1


def test_hierarchies_by_measure_from_csv_outputs_error_if_bad_end_fraction_value(
    hierarchy_tlui, beat_tlui
):
    beat_tl = beat_tlui.timeline
    hierarchy_tl = hierarchy_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)

    data = "start,end,end_fraction,level\n1, 2, nonsense, 1"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = hierarchies_by_measure_from_csv(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]

    assert hierarchy_tl.ordered_hierarchies[0].start == 1


def test_hierarchies_by_measure_from_csv_outputs_error_if_no_measure_found(
    hierarchy_tlui, beat_tlui
):
    beat_tl = beat_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)

    data = "start,end,level\n3, 4, 1"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = hierarchies_by_measure_from_csv(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "No measure with number" in errors[0]

    data = "start,end,level\n1, 5, 1"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = hierarchies_by_measure_from_csv(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "No measure with number" in errors[0]


def test_hierarchies_by_measure_from_csv_bad_optional_attrs_values(
    hierarchy_tlui, beat_tlui
):
    beat_tl = beat_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)

    data = "start,end,level,pre_start,post_end,\n1,2,1,nonsense1,nonsense2"
    with patch("builtins.open", mock_open(read_data=data)):
        errors = hierarchies_by_measure_from_csv(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense1" in errors[0]
    assert "nonsense2" in errors[1]
