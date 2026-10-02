import os

import pytest

from tests.constants import EXAMPLE_MEDIA_PATH
from tilia.requests import Post, post
from tilia.ui import commands


@pytest.fixture
def conservative_player_stop(tilia):
    """
    Increases player.SLEEP_AFTER_STOP to 5 seconds if on CI.
    Avoids freezes when setting URL after stop. Workaround for running tests on CI.
    Proper handling of player status changes would be a more robust solution.
    """

    original_sleep_after_stop = tilia.player.SLEEP_AFTER_STOP
    if os.getenv("CI") == "true":
        tilia.player.SLEEP_AFTER_STOP = 5
    yield
    tilia.player.SLEEP_AFTER_STOP = original_sleep_after_stop


class TestSeek:
    @pytest.mark.parametrize(
        "time, expected",
        [(50, 50), (150, 100), (-10, 0)],
        ids=["in_bounds", "past_end", "negative"],
    )
    def test_seek_is_clamped_to_media_bounds(self, tilia_state, time, expected):
        tilia_state.duration = 100
        commands.execute("media.seek", time)
        assert tilia_state.current_time == expected


@pytest.mark.skipif(os.getenv("CI") == "true", reason="Tests are flaky on CI.")
class TestPlayer:
    @staticmethod
    def _load_example():
        post(Post.APP_MEDIA_LOAD, EXAMPLE_MEDIA_PATH)

    def test_unload_media(self, tilia):
        self._load_example()
        post(Post.APP_CLEAR)

    def test_unload_media_after_playing(self, tilia):
        self._load_example()
        commands.execute("media.toggle_play", False)
        commands.execute("media.toggle_play", True)
        post(Post.APP_CLEAR)

    def test_unload_media_while_playing(self, tilia):
        self._load_example()
        commands.execute("media.toggle_play", False)
        post(Post.APP_CLEAR)
