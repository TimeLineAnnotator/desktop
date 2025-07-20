import os
from unittest.mock import patch
import shutil

import pytest
import httpx

from tests.constants import (
    EXAMPLE_MEDIA_PATH,
    EXAMPLE_MEDIA_DURATION,
    EXAMPLE_MEDIA_SCALE_FACTOR,
)
from tilia.requests import get, Get
from tilia.ui.cli.player import CLIYoutubePlayer


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


@pytest.mark.skipif(
    os.environ.get("YOUTUBE_API_KEY") is None,
    reason="YOUTUBE_API_KEY environment variable is required to run this test.",
)
class TestLoadYoutube:
    PREFIX = "https://www.youtube.com/watch?v="
    EXAMPLE_VIDEO_ID = "WDzeHNpNaoM"
    EXAMPLE_VIDEO_DURATION = 3056
    INITIAL_DURATION = 1

    @pytest.fixture(autouse=True)
    def set_duration(self, tilia_state):
        tilia_state.duration = self.INITIAL_DURATION

    @staticmethod
    def skip_if_no_youtube_api_key(func):
        return

    def load_media(self, cli, id):
        cli.parse_and_run(f"load-media {self.PREFIX}{id}")

    def assert_error(self, tilia_errors, message, tilia_state, prev_duration):
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message(message)
        assert tilia_state.duration == prev_duration

    def test_load(self, cli, tilia_errors):
        self.load_media(cli, self.EXAMPLE_VIDEO_ID)

        tilia_errors.assert_no_error()
        assert get(Get.MEDIA_DURATION) == self.EXAMPLE_VIDEO_DURATION

    def test_load_youtu_dot_be(self, cli, tilia_errors):
        cli.parse_and_run(
            f"load-media https://youtu.be/watch?v={self.EXAMPLE_VIDEO_ID}"
        )

        tilia_errors.assert_no_error()
        assert get(Get.MEDIA_DURATION) == self.EXAMPLE_VIDEO_DURATION

    def test_load_from_playlist(self, cli, tilia_errors):
        cli.parse_and_run(
            'load-media "https://www.youtube.com/watch?v=adLGHcj_fmA&list=RDQMgEzdN5RuCXE&index=2"'
        )

        tilia_errors.assert_no_error()
        assert get(Get.MEDIA_DURATION) == 249

    @patch("httpx.get")
    def test_no_connection(self, mock_httpx, cli, tilia_errors, tilia_state):
        mock_httpx.side_effect = httpx.RequestError("")

        self.load_media(cli, self.EXAMPLE_VIDEO_ID)

        self.assert_error(
            tilia_errors,
            CLIYoutubePlayer.CONNECTION_ERROR_MESSAGE,
            tilia_state,
            self.INITIAL_DURATION,
        )

    @patch("httpx.Response.raise_for_status")
    def test_request_failed(self, mock_httpx, cli, tilia_errors, tilia_state):
        mock_httpx.side_effect = httpx.HTTPStatusError(
            "",
            request=httpx.Request("", self.PREFIX + self.EXAMPLE_VIDEO_ID),
            response=httpx.Response(404),
        )

        self.load_media(cli, self.EXAMPLE_VIDEO_ID)

        self.assert_error(
            tilia_errors,
            CLIYoutubePlayer.REQUEST_FAILED_MESSAGE.format(200),
            tilia_state,
            self.INITIAL_DURATION,
        )

    @patch("httpx.Response.json")
    def test_decode_error(self, mock_httpx, cli, tilia_errors, tilia_state):
        mock_httpx.side_effect = httpx.DecodingError("")

        self.load_media(cli, self.EXAMPLE_VIDEO_ID)

        self.assert_error(
            tilia_errors,
            CLIYoutubePlayer.DECODE_ERROR_MESSAGE,
            tilia_state,
            self.INITIAL_DURATION,
        )

    def test_video_not_found(self, cli, tilia_errors, tilia_state):
        self.load_media(cli, "INEXISTENT_ID")

        self.assert_error(
            tilia_errors,
            CLIYoutubePlayer.VIDEO_NOT_FOUND_MESSAGE.format("INEXISTENT_ID"),
            tilia_state,
            self.INITIAL_DURATION,
        )

    @patch("httpx.Response.json")
    def test_duration_not_available(self, mock_httpx, cli, tilia_errors, tilia_state):
        mock_httpx.return_value = {"items": [{"contentDetails": {}}]}

        self.load_media(cli, self.EXAMPLE_VIDEO_ID)

        self.assert_error(
            tilia_errors,
            CLIYoutubePlayer.DURATION_NOT_AVAILABLE_MESSAGE,
            tilia_state,
            self.INITIAL_DURATION,
        )

    def test_duration_if_error(self, cli, tilia_errors, tilia_state):
        cli.parse_and_run(
            f"load-media {self.PREFIX}INEXISTENT_ID --duration-if-error 99"
        )

        tilia_errors.assert_error()
        assert tilia_state.duration == 99
