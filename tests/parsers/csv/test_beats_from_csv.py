from pathlib import Path
from unittest.mock import mock_open, patch

from tests.parsers.csv.common import assert_in_errors
from tilia.parsers.csv.beat import beats_from_csv
from tilia.settings import settings
from tilia.timelines.base.metric_position import MetricPosition
from tilia.ui import commands
from tilia.ui.format import format_media_time


def _import_with_patch(tl, data):
    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = beats_from_csv(
            tl,
            Path(),
        )
    return success, errors


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

    success, errors = _import_with_patch(beat_tl, data)

    assert_in_errors(format_media_time(101), errors)


def test_with_measure_number(beat_tl):
    data = "time,measure\n5,1\n10,\n15,\n20,\n25,\n30,8"
    _import_with_patch(beat_tl, data)

    assert beat_tl[3].metric_position == MetricPosition(1, 4, 1)
    assert beat_tl[4].metric_position == MetricPosition(8, 1, 1)


def test_with_measure_number_non_monotonic(beat_tl):
    data = "time,measure\n1,1\n2,10\n3,2\n4,11\n5,"
    beat_tl.beat_pattern = [1]

    _import_with_patch(beat_tl, data)

    assert beat_tl[0].metric_position == MetricPosition(1, 1, 1)
    assert beat_tl[1].metric_position == MetricPosition(10, 1, 1)
    assert beat_tl[2].metric_position == MetricPosition(2, 1, 1)
    assert beat_tl[3].metric_position == MetricPosition(11, 1, 1)
    assert beat_tl[4].metric_position == MetricPosition(12, 1, 1)


def test_with_is_first_in_measure(beat_tl):
    data = "time,is_first_in_measure\n0,True\n5,\n10,\n15,\n20,\n25,True\n30,\n35,True"

    _import_with_patch(beat_tl, data)

    assert beat_tl[4].metric_position == MetricPosition(1, 5, 1)
    assert beat_tl[5].metric_position == MetricPosition(2, 1, 1)
    assert beat_tl[6].metric_position == MetricPosition(2, 2, 1)
    assert beat_tl[7].metric_position == MetricPosition(3, 1, 1)


def test_with_measure_numbers_in_rows_with_is_first_in_measure_false(beat_tl):
    data = "time,is_first_in_measure,measure\n0,True,1\n2,False,8"

    _import_with_patch(beat_tl, data)

    assert beat_tl[0].metric_position == MetricPosition(1, 1, 1)
    assert beat_tl[1].metric_position == MetricPosition(1, 2, 1)


def test_with_measure_number_and_is_first_in_csv(beat_tl):
    data = "time,is_first_in_measure,measure\n0,,\n5,,\n10,,\n15,,\n20,True,\n25,True,10\n30,,\n35,True,"

    _import_with_patch(beat_tl, data)

    assert beat_tl[3].metric_position == MetricPosition(1, 4, 1)
    assert beat_tl[4].metric_position == MetricPosition(2, 1, 1)
    assert beat_tl[5].metric_position == MetricPosition(10, 1, 1)
    assert beat_tl[6].metric_position == MetricPosition(10, 2, 1)
    assert beat_tl[7].metric_position == MetricPosition(11, 1, 1)


def test_with_optional_params_not_sorted(beat_tl):
    data = "time,is_first_in_measure,measure\n0,,\n10,,\n5,,\n15,True,"

    success, errors = _import_with_patch(beat_tl, data)

    assert_in_errors("sorted", errors)


def test_with_empty_is_first_in_measure(beat_tl):
    data = "time,is_first_in_measure\n0,\n5,\n10,\n15,\n20,\n25,\n30,\n35,"

    _import_with_patch(beat_tl, data)

    assert beat_tl.beats_in_measure == [8]


def test_with_invalid_is_first_in_measure(beat_tl):
    data = "time,is_first_in_measure\n0,\n5,\n10,\n15,\n20,not_valid\n25,True\n30,\n35,"

    _import_with_patch(beat_tl, data)

    assert beat_tl.beats_in_measure == [5, 3]


def test_measure_number_on_every_beat_is_forced_once(beat_tlui):
    settings.set("beat_timeline", "display_measure_periodicity", 4)
    beat_tlui.timeline.beat_pattern = [4]
    rows = [f"{time},{1 if time < 4 else 2}" for time in range(8)]
    _import_with_patch(beat_tlui.timeline, "\n".join(["time,measure", *rows]))
    assert beat_tlui[4].label.isVisible()

    beat_tlui.select_element(beat_tlui[4])
    commands.execute("timeline.beat.reset_measure_number")

    # A measure forced once per beat would need a reset per beat.
    assert not beat_tlui[4].label.isVisible()
