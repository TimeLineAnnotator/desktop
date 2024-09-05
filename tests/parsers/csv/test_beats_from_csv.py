from pathlib import Path
from unittest.mock import patch, mock_open

from tests.parsers.csv.common import assert_in_errors
from tilia.parsers.csv.beat import beats_from_csv


def _import_with_patch(tl, data):
    with patch("builtins.open", mock_open(read_data=data)):
        errors = beats_from_csv(tl, Path(), )
    return errors


def test_by_time(beat_tl):
    data = "time\n5\n10\n15\n20"

    _import_with_patch(beat_tl, data)
    beat_tl.beat_pattern = [2]

    assert beat_tl[0].time == 5
    assert beat_tl[1].time == 10
    assert beat_tl[2].time == 15
    assert beat_tl[3].time == 20


def test_component_creation_fail_reason_gets_into_errors(beat_tl, tilia_state):
    tilia_state.duration = 100
    data = "time\n101"

    errors = _import_with_patch(beat_tl, data)

    assert_in_errors("101", errors)


def test_with_measure_number(beat_tl):
    data = "time,measure_number\n5,1\n10,\n15,\n20,\n25,\n30,8"
    _import_with_patch(beat_tl, data)

    assert beat_tl[3].metric_position == (1, 4)
    assert beat_tl[4].metric_position == (8, 1)


def test_with_measure_number_non_monotonic(beat_tl):
    data = "time,measure_number\n1,1\n2,10\n3,2\n4,11\n5,"
    beat_tl.beat_pattern = [1]

    _import_with_patch(beat_tl, data)

    assert beat_tl[0].metric_position == (1, 1)
    assert beat_tl[1].metric_position == (10, 1)
    assert beat_tl[2].metric_position == (2, 1)
    assert beat_tl[3].metric_position == (11, 1)
    assert beat_tl[4].metric_position == (12, 1)


def test_with_is_first_in_measure(beat_tl):
    data = "time,is_first_in_measure\n0,True\n5,\n10,\n15,\n20,\n25,True\n30,\n35,True"

    _import_with_patch(beat_tl, data)

    assert beat_tl[4].metric_position == (1, 5)
    assert beat_tl[5].metric_position == (2, 1)
    assert beat_tl[6].metric_position == (2, 2)
    assert beat_tl[7].metric_position == (3, 1)


def test_with_measure_numbers_in_rows_with_is_first_in_measure_false(beat_tl):
    data = 'time,is_first_in_measure,measure_number\n0,True,1\n2,False,8'

    _import_with_patch(beat_tl, data)

    assert beat_tl[0].metric_position == (1, 1)
    assert beat_tl[1].metric_position == (1, 2)


def test_with_measure_number_and_is_first_in_csv(beat_tl):
    data = "time,is_first_in_measure,measure_number\n0,,\n5,,\n10,,\n15,,\n20,True,\n25,True,10\n30,,\n35,True,"

    _import_with_patch(beat_tl, data)

    assert beat_tl[3].metric_position == (1, 4)
    assert beat_tl[4].metric_position == (2, 1)
    assert beat_tl[5].metric_position == (10, 1)
    assert beat_tl[6].metric_position == (10, 2)
    assert beat_tl[7].metric_position == (11, 1)


def test_with_optional_params_not_sorted(beat_tl):
    data = "time,is_first_in_measure,measure_number\n0,,\n10,,\n5,,\n15,True,"

    errors = _import_with_patch(beat_tl, data)

    assert_in_errors("sorted", errors)


def test_with_empty_is_first_in_measure(beat_tl):
    data = "time,is_first_in_measure\n0,\n5,\n10,\n15,\n20,\n25,\n30,\n35,"

    _import_with_patch(beat_tl, data)

    assert beat_tl.beats_in_measure == [8]


def test_with_invalid_is_first_in_measure(beat_tl):
    data = "time,is_first_in_measure\n0,\n5,\n10,\n15,\n20,not_valid\n25,True\n30,\n35,"

    _import_with_patch(beat_tl, data)

    assert beat_tl.beats_in_measure == [5, 3]
