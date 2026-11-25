import json
import os
import shutil
import sys
from io import BytesIO, TextIOWrapper
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from tests.constants import (
    EXAMPLE_MEDIA_DURATION,
    EXAMPLE_MEDIA_PATH,
    EXAMPLE_MEDIA_SCALE_FACTOR,
)
from tilia.errors import MEDIA_NOT_FOUND
from tilia.media.player.qtplayer import QtPlayer
from tilia.requests import Get, get
from tilia.ui import commands
from tilia.ui.cli.player import CLIYoutubePlayer
from tilia_core import build, tla


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


def test_with_timelines_scale_yes(cli, tilia_state, marker_tl):
    commands.execute("media.seek", tilia_state.duration / 2)

    marker_tl.create_marker(tilia_state.current_time)

    cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH} --scale-timelines yes")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert marker_tl[0].get_data("time") == EXAMPLE_MEDIA_DURATION / 2


def test_with_timelines_scale_no(cli, tilia_state, marker_tl):
    marker_tl.create_marker(5)

    cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH} --scale-timelines no")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert marker_tl[0].get_data("time") == 5


def test_with_timelines_scale_not_provided_answer_yes(cli, tilia_state, marker_tl):
    marker_tl.create_marker(50)

    from unittest.mock import patch

    with patch("builtins.input", return_value="y"):
        cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH}")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert marker_tl[0].get_data("time") == 50 * EXAMPLE_MEDIA_SCALE_FACTOR


def test_with_timelines_scale_not_provided_answer_yes_but_dont_confirm_crop(
    cli, tilia_state, marker_tl
):
    marker_tl.create_marker(50)

    with patch("builtins.input", side_effect=["y", "n"]):
        cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH}")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert marker_tl[0].get_data("time") == 50 * EXAMPLE_MEDIA_SCALE_FACTOR


def test_with_timelines_scale_not_provided_answer_crop(cli, tilia_state, marker_tl):
    for time in [5, 50]:
        marker_tl.create_marker(time)

    with patch("builtins.input", side_effect=["n", "y"]):
        cli.parse_and_run(f"load-media {EXAMPLE_MEDIA_PATH}")

    assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
    assert len(marker_tl) == 1
    assert marker_tl[0].get_data("time") == 5


VIDEO = "watch?v=dQw4w9WgXcQ"


def link_folder(link: Path, target: Path) -> None:
    """A link to a folder: a symbolic link where the system lets us make one, else,
    on Windows, a junction."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


@pytest.fixture
def working_folder(tmp_path, monkeypatch):
    """The working folder, with media in it that is never played, only looked for;
    and no YouTube to ask for a video's length."""
    for folder in ("Audio", "elsewhere", "youtube.com"):
        (tmp_path / folder).mkdir()
        shutil.copy(EXAMPLE_MEDIA_PATH, tmp_path / folder / "Clip.mp3")
    link_folder(tmp_path / "linked", tmp_path / "elsewhere")
    monkeypatch.chdir(tmp_path)
    with (
        patch.object(QtPlayer, "_engine_load_media", return_value=True),
        patch.object(
            CLIYoutubePlayer, "get_youtube_duration", return_value=(True, 100.0)
        ),
    ):
        yield tmp_path


class TestStoresWhatAScriptStores:
    """The core decides what is media, and the path to store for it, for a script's
    `load-media` too (FR-033; US8)."""

    @staticmethod
    def stored(path: Path) -> str:
        return json.loads(path.read_bytes())["media"]["path"]

    def stored_by_a_script(self, text: str, folder: Path) -> str:
        doc = build.new_script_document()
        build.load_media(doc, text, duration_if_error=100.0)
        tla.write(folder / "by a script.tla", doc)
        return self.stored(folder / "by a script.tla")

    @pytest.mark.parametrize(
        "text, expected",
        [
            pytest.param("Audio/Clip.mp3", "Audio/Clip.mp3", id="relative"),
            pytest.param("Audio/../Audio/Clip.mp3", "Audio/Clip.mp3", id="parent"),
            pytest.param(r"Audio\Clip.mp3", "Audio/Clip.mp3", id="backslash"),
            pytest.param(
                "AUDIO/CLIP.MP3",
                "Audio/Clip.mp3",
                id="letter-case",
                marks=pytest.mark.skipif(
                    sys.platform != "win32", reason="Windows only"
                ),
            ),
            pytest.param("linked/Clip.mp3", "linked/Clip.mp3", id="linked-folder"),
            pytest.param(
                "youtube.com/Clip.mp3", "youtube.com/Clip.mp3", id="file-like-a-link"
            ),
            pytest.param(
                r"youtube.com\Clip.mp3", "youtube.com/Clip.mp3", id="so-with-backslash"
            ),
            pytest.param(
                f"youtube.com/{VIDEO}", f"https://youtube.com/{VIDEO}", id="no-scheme"
            ),
            pytest.param(
                f"http://youtube.com/{VIDEO}",
                f"http://youtube.com/{VIDEO}",
                id="scheme",
            ),
        ],
    )
    def test_the_media_path(
        self, cli, tilia_state, tilia_errors, working_folder, text, expected
    ):
        cli.parse_and_run(f'load-media "{text}"')
        cli.parse_and_run(f'save "{working_folder / "by TiLiA.tla"}"')

        tilia_errors.assert_no_error()
        assert self.stored(working_folder / "by TiLiA.tla") == expected
        assert self.stored_by_a_script(text, working_folder) == expected

    def test_the_player_gets_a_link_with_its_scheme(
        self, cli, tilia_state, working_folder
    ):
        cli.parse_and_run(f"load-media youtube.com/{VIDEO}")

        assert tilia_state.media_path == f"https://youtube.com/{VIDEO}"

    @pytest.mark.parametrize("folder", ["linked", "youtube.com"])
    def test_the_player_gets_the_file_s_path_absolute(
        self, cli, tilia_state, working_folder, folder
    ):
        cli.parse_and_run(f"load-media {folder}/Clip.mp3")

        assert (
            tilia_state.media_path == (working_folder / folder / "Clip.mp3").as_posix()
        )


class TestNotMedia:
    """What the core refuses is refused with TiLiA's message, whose words are the
    core's, and nothing is loaded."""

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("missing.mp3", id="missing"),
            pytest.param(r"missing folder\missing.mp3", id="missing-with-backslash"),
            pytest.param("Audio", id="folder"),
            pytest.param("https://example.com/a.mp3", id="web-link"),
            pytest.param(r"https://example.com/a\b.mp3", id="web-link-with-backslash"),
            pytest.param(r"youtube.com/sub\clip.mp4", id="like-a-link-with-backslash"),
            pytest.param("bad\udcff.mp3", id="not-utf-8"),
        ],
    )
    def test_is_refused(self, cli, tilia_state, tilia_errors, working_folder, text):
        with pytest.raises(ValueError) as by_the_core:
            build.media_path(text)

        cli.parse_and_run(f'load-media "{text}" --duration-if-error 9')

        assert tilia_errors.errors == [
            {"title": MEDIA_NOT_FOUND.title, "message": str(by_the_core.value)}
        ]
        assert tilia_state.media_path == ""
        assert tilia_state.duration == 100

    @pytest.mark.parametrize("name", ["missing.mp3", "né.mp3", "{0}.mp3"])
    def test_the_words_are_media_not_found_s(
        self, cli, tilia_errors, working_folder, name
    ):
        cli.parse_and_run(f"load-media {name}")

        assert tilia_errors.errors[0]["message"] == MEDIA_NOT_FOUND.message.format(name)

    def test_a_name_that_isnt_utf_8_is_printed(self, cli, working_folder, monkeypatch):
        # As its escape: an output in UTF-8 refuses the name itself.
        output = TextIOWrapper(BytesIO(), encoding="utf-8")
        monkeypatch.setattr(sys, "stdout", output)

        cli.parse_and_run("load-media bad\udcff.mp3")

        output.flush()
        printed = output.buffer.getvalue().decode()
        assert MEDIA_NOT_FOUND.message.format("bad\\udcff.mp3") in printed
        assert cli.exception is None


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
