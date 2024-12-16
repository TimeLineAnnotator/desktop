import os
from pathlib import Path
from unittest.mock import mock_open, patch

from tests.parsers.csv.common import assert_in_errors
from tilia.parsers.csv.hierarchy import (
    import_by_time,
    import_by_measure,
)


def test_hierarchies_by_time_from_csv(hierarchy_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "start,end,level,label\n0,1,1,first\n1,2,2,second\n2,3,3,third"

    with patch("builtins.open", mock_open(read_data=data)):
        import_by_time(
            hierarchy_tlui.timeline,
            Path("parsers", "test_markers_by_time_from_csv.csv").resolve(),
        )

    hierarchies = sorted(hierarchy_tlui.timeline)

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
        import_by_measure(
            hierarchy_tl,
            beat_tl,
            Path(),
        )

    hierarchies = sorted(hierarchy_tl)

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
        success, errors = import_by_measure(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]


def test_hierarchies_by_measure_from_csv_outputs_error_if_bad_end_value(
    hierarchy_tlui, beat_tlui
):
    data = "start,end,level\n1, nonsense, 1"
    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = import_by_measure(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]


def test_hierarchies_by_measure_from_csv_outputs_error_if_bad_level_value(
    hierarchy_tlui, beat_tlui
):
    data = "start,end,level\n1, 1, nonsense"
    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = import_by_measure(
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
        success, errors = import_by_measure(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]

    assert sorted(hierarchy_tl)[0].start == 1


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
        success, errors = import_by_measure(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense" in errors[0]

    assert sorted(hierarchy_tl)[0].start == 1


def test_hierarchies_by_measure_from_csv_outputs_error_if_no_measure_found(
    hierarchy_tlui, beat_tlui
):
    beat_tl = beat_tlui.timeline
    beat_tl.beat_pattern = [1]
    beat_tlui.create_beat(time=1)
    beat_tlui.create_beat(time=2)

    data = "start,end,level\n3, 4, 1"
    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = import_by_measure(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "No measure with number" in errors[0]

    data = "start,end,level\n1, 5, 1"
    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = import_by_measure(
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
        success, errors = import_by_measure(
            hierarchy_tlui.timeline, beat_tlui.timeline, Path()
        )

    assert "nonsense1" in errors[0]
    assert "nonsense2" in errors[1]


def test_component_creation_fail_reason_gets_into_errors(
    hierarchy_tl, beat_tlui, tilia_state
):

    tilia_state.duration = 100
    data = "start,end,level\n101,1,1"

    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = import_by_time(
            hierarchy_tl,
            Path(),
        )

    assert_in_errors("101", errors)
