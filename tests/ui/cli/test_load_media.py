from unittest.mock import patch
import shutil

import pytest

from tests.constants import (
    EXAMPLE_MEDIA_PATH,
    EXAMPLE_MEDIA_DURATION,
    EXAMPLE_MEDIA_SCALE_FACTOR,
)
from tilia.requests import get, Get


def test_load_media(cli, tilia_state):
    cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH}")
    assert tilia_state.media_path == EXAMPLE_MEDIA_PATH
    assert tilia_state.duration != 9.957


def assert_load_was_successful(duration):
    assert pytest.approx(get(Get.MEDIA_DURATION)) == duration


def test_load_inexistent(cli, tilia_errors):
    cli.parse_and_run("load-media inexistent")

    tilia_errors.assert_error()
    assert "inexistent" in tilia_errors.errors[0]["message"]


def test_load_with_forward_slashes(cli, tilia_errors, resources):
    path = resources / "example.ogg"
    path = str(path.resolve()).replace("/", "\\")
    cli.parse_and_run("load-media " + path)
    assert_load_was_successful(EXAMPLE_MEDIA_DURATION)


def test_load_with_spaces(cli, tilia_errors, resources, tmp_path):
    path = resources / "example.ogg"
    shutil.copy(str(path), str(tmp_path / "with spaces.ogg"))

    cli.parse_and_run(
        f'load-media "{(tmp_path / "with spaces.ogg").resolve().__str__()}"'
    )

    assert_load_was_successful(EXAMPLE_MEDIA_DURATION)


def test_with_timelines_scale_yes(cli, tilia_state, marker_tl, user_actions):
    tilia_state.current_time = tilia_state.duration / 2
    marker_tl.create_marker(tilia_state.current_time)

    cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH} --scale-timelines yes")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert marker_tl[0].get_data("time") == EXAMPLE_MEDIA_DURATION / 2


def test_with_timelines_scale_no(cli, tilia_state, marker_tl, user_actions):
    marker_tl.create_marker(5)

    cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH} --scale-timelines no")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert marker_tl[0].get_data("time") == 5


def test_with_timelines_scale_not_provided_answer_yes(
    cli, tilia_state, marker_tl, user_actions
):
    marker_tl.create_marker(50)

    from unittest.mock import patch

    with patch("builtins.input", return_value="y"):
        cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH}")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert marker_tl[0].get_data("time") == 50 * EXAMPLE_MEDIA_SCALE_FACTOR


def test_with_timelines_scale_not_provided_answer_yes_but_dont_confirm_crop(
    cli, tilia_state, marker_tl, user_actions
):
    marker_tl.create_marker(50)

    with patch("builtins.input", side_effect=["y", "n"]):
        cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH}")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert marker_tl[0].get_data("time") == 50 * EXAMPLE_MEDIA_SCALE_FACTOR


def test_with_timelines_scale_not_provied_answer_crop(
    cli, tilia_state, marker_tl, user_actions
):
    for time in [5, 50]:
        marker_tl.create_marker(time)

    with patch("builtins.input", side_effect=["n", "y"]):
        cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH}")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert len(marker_tl) == 1
    assert marker_tl[0].get_data("time") == 5
