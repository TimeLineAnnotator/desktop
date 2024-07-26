import os
from pathlib import Path
from unittest.mock import patch, mock_open

from tests.parsers.csv.common import assert_in_errors
from tilia.parsers.csv.beat import beats_from_csv


def test_beats_from_csv(beat_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time\n5\n10\n15\n20"

    with patch("builtins.open", mock_open(read_data=data)):
        beats_from_csv(
            beat_tlui.timeline,
            Path(),
        )

    tl = beat_tlui.timeline
    tl.beat_pattern = [2]
    beats = sorted(tl.components)

    assert beats[0].time == 5
    assert beats[1].time == 10
    assert beats[2].time == 15
    assert beats[3].time == 20


def test_component_creation_fail_reason_gets_into_errors(beat_tl, tilia_state):

    tilia_state.duration = 100
    data = "time\n101"

    with patch("builtins.open", mock_open(read_data=data)):
        errors = beats_from_csv(
            beat_tl,
            Path(),
        )

    assert_in_errors("101", errors)


def test_beats_from_csv_with_measure_number(beat_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time,measure_number\n5,1\n10,\n15,\n20,\n25,\n30,8"

    tl = beat_tlui.timeline
    with patch("builtins.open", mock_open(read_data=data)):
        beats_from_csv(
            tl,
            Path(),
        )

    beats = sorted(tl.components)
    assert beats[3].metric_position == (1, 4)
    assert beats[4].metric_position == (8, 1)


def test_beats_from_csv_with_is_first_in_measure(beat_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time,is_first_in_measure\n0,True\n5,\n10,\n15,\n20,\n25,True\n30,\n35,True"

    tl = beat_tlui.timeline
    with patch("builtins.open", mock_open(read_data=data)):
        beats_from_csv(tl, Path())

    beats = sorted(tl.components)
    assert beats[4].metric_position == (1, 5)
    assert beats[5].metric_position == (2, 1)
    assert beats[6].metric_position == (2, 2)
    assert beats[7].metric_position == (3, 1)


def test_beats_from_csv_with_measure_number_and_is_first_in_csv(beat_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time,is_first_in_measure,measure_number\n0,,\n5,,\n10,,\n15,,\n20,True,\n25,True,10\n30,,\n35,True,"

    tl = beat_tlui.timeline
    with patch("builtins.open", mock_open(read_data=data)):
        beats_from_csv(tl, Path())

    beats = sorted(tl.components)
    assert beats[3].metric_position == (1, 4)
    assert beats[4].metric_position == (2, 1)
    assert beats[5].metric_position == (10, 1)
    assert beats[6].metric_position == (10, 2)
    assert beats[7].metric_position == (11, 1)


def test_beats_from_csv_with_optional_params_not_sorted(beat_tl):
    data = "time,is_first_in_measure,measure_number\n0,,\n10,,\n5,,\n15,True,"

    with patch("builtins.open", mock_open(read_data=data)):
        errors = beats_from_csv(
            beat_tl,
            Path(),
        )

    assert_in_errors("sorted", errors)


def test_beats_from_csv_with_empty_is_first_in_measure(beat_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time,is_first_in_measure\n0,\n5,\n10,\n15,\n20,\n25,\n30,\n35,"

    tl = beat_tlui.timeline
    with patch("builtins.open", mock_open(read_data=data)):
        beats_from_csv(tl, Path())

    assert tl.beats_in_measure == [8]


def test_beats_from_csv_with_invalid_is_first_in_measure(beat_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time,is_first_in_measure\n0,\n5,\n10,\n15,\n20,not_valid\n25,True\n30,\n35,"

    tl = beat_tlui.timeline
    with patch("builtins.open", mock_open(read_data=data)):
        beats_from_csv(tl, Path())

    assert tl.beats_in_measure == [5, 3]
