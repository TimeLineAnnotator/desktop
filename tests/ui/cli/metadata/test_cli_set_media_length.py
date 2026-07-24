from unittest.mock import patch

import pytest

from tests.constants import EXAMPLE_MEDIA_PATH


def test_set(cli, tilia_state):
    cli.parse_and_run("metadata set-media-length 123.45")

    assert tilia_state.duration == 123.45


def test_set_to_string_fails(cli, tilia_state, tilia_errors):
    prev_duration = tilia_state.duration
    cli.parse_and_run("metadata set-media-length invalid")

    assert tilia_state.duration == prev_duration
    # no error is raised since argparse pre-validates the value


def test_set_to_negative_fails(cli, tilia_state, tilia_errors):
    prev_duration = tilia_state.duration
    cli.parse_and_run("metadata set-media-length -23")

    assert tilia_state.duration == prev_duration
    tilia_errors.assert_error()


def test_set_to_zero_fails(cli, tilia_state, tilia_errors):
    prev_duration = tilia_state.duration
    cli.parse_and_run("metadata set-media-length 0")

    assert tilia_state.duration == prev_duration
    tilia_errors.assert_error()


def test_does_not_inherit_scale_timelines_from_earlier_load_media(
    cli, tilia_state, marker_tl
):
    # Regression: `load-media --scale-timelines yes` used to leave
    # App.should_scale_timelines = "yes" for the rest of the session, so a
    # later, unrelated `set-media-length` (which doesn't pass its own
    # --scale-timelines) would silently auto-scale instead of prompting.
    marker_tl.create_marker(50)
    cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH} --scale-timelines yes")
    marker_time_after_load = marker_tl[0].get_data("time")
    duration_after_load = tilia_state.duration

    with patch("builtins.input", return_value="y") as mock_input:
        cli.parse_and_run("metadata set-media-length 999")

    mock_input.assert_called()
    assert tilia_state.duration == 999
    assert marker_tl[0].get_data("time") == pytest.approx(
        marker_time_after_load * 999 / duration_after_load
    )
