import shutil
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.constants import EXAMPLE_MEDIA_PATH
from tilia.media.player import QtAudioPlayer
from tilia.requests import Get, get
from tilia.timelines.slider.timeline import SliderTimeline


class TestClear:
    @pytest.fixture(autouse=True)
    def setup_timelines(self, tls):
        tls.create_timeline(SliderTimeline)

    @staticmethod
    def assert_cleared(tls):
        assert len(tls) == 1
        assert isinstance(tls[0], SliderTimeline)

    def test_clear(self, cli, tls, tilia_state):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        cli.parse_and_run("clear --force")

        self.assert_cleared(tls)

    def test_clear_twice(self, cli, tls, tilia_state):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        cli.parse_and_run("clear --force")
        cli.parse_and_run("clear --force")

        self.assert_cleared(tls)

    def test_clear_saved_does_not_prompt_for_confirmation(
        self, cli, tls, tmp_path, tilia_state
    ):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        cli.parse_and_run("save " + str(tmp_path.resolve()))
        cli.parse_and_run("clear")

        self.assert_cleared(tls)

    def test_clear_unsaved_do_not_confirm(
        self, cli, tls, tmp_path, tilia_state, monkeypatch
    ):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        monkeypatch.setattr("sys.stdin", StringIO("no\n"))
        cli.parse_and_run("clear")

        assert len(tls) == 2

    def test_clear_unsaved_confirm(self, cli, tls, tmp_path, tilia_state, monkeypatch):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        monkeypatch.setattr("sys.stdin", StringIO("yes\n"))
        cli.parse_and_run("clear")

        self.assert_cleared(tls)

    def test_clear_after_loading_other_media_of_the_same_length_prompts(
        self, cli, tls, tmp_path, monkeypatch
    ):
        other = Path(shutil.copy(EXAMPLE_MEDIA_PATH, tmp_path / "other.mp3"))
        monkeypatch.setattr("sys.stdin", StringIO("no\n"))
        # The player reports no length: it stays the file's.
        with patch.object(QtAudioPlayer, "_engine_load_media", return_value=True):
            cli.parse_and_run(f'load-media "{EXAMPLE_MEDIA_PATH}"')
            cli.parse_and_run(f'save "{tmp_path / "piece.tla"}"')
            assert not get(Get.IS_FILE_MODIFIED)
            cli.parse_and_run(f'load-media "{other}"')

        cli.parse_and_run("clear")

        # Not cleared.
        assert Path(get(Get.MEDIA_PATH)) == other.resolve()
