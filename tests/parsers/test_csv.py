import os
from pathlib import Path

import pytest
from tilia.parsers.csv import *


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

    markers_by_measure_from_csv(
        marker_tl,
        beat_tl,
        Path("parsers", "test_markers_by_measure_from_csv.csv").resolve(),
    )

    markers = marker_tl.ordered_markers

    assert markers[0].time == 1
    assert markers[1].time == 2.5
    assert markers[2].time == 4


def test_markers_by_measure_from_csv_raises_error_if_no_measure_column(
    beat_tlui, marker_tlui
):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    with pytest.raises(ValueError):
        markers_by_measure_from_csv(
            beat_tlui.timeline,
            marker_tlui.timeline,
            Path("parsers", "test_markers_from_csv_raises_error.csv").resolve(),
        )


def test_markers_by_time_from_csv(marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    markers_by_time_from_csv(
        marker_tlui.timeline,
        Path("parsers", "test_markers_from_csv.csv").resolve(),
    )

    markers = marker_tlui.timeline.ordered_markers

    assert markers[0].time == 1
    assert markers[0].ui.label == "first"
    assert markers[0].comments == "first comment"

    assert markers[1].time == 5
    assert markers[1].ui.label == "second"
    assert markers[1].comments == "second comment"

    assert markers[2].time == 10
    assert markers[2].ui.label == "third"
    assert markers[2].comments == "third comment"


def test_markers_by_time_from_csv_raises_error_if_no_time_column(marker_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    with pytest.raises(ValueError):
        markers_by_time_from_csv(
            marker_tlui.timeline,
            Path("parsers", "test_markers_from_csv_raises_error.csv").resolve(),
        )
