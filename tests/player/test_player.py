import os
from unittest.mock import patch

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


def load_example():
    post(Post.APP_MEDIA_LOAD, EXAMPLE_MEDIA_PATH)


@pytest.mark.skipif(os.getenv("CI") == "true", reason="Tests are flaky on CI.")
class TestPlayer:
    def test_unload_media(self, tilia):
        load_example()
        post(Post.APP_CLEAR)

    def test_unload_media_after_playing(self, tilia):
        load_example()
        commands.execute("media.toggle_play", False)
        commands.execute("media.toggle_play", True)
        post(Post.APP_CLEAR)

    def test_unload_media_while_playing(self, tilia):
        load_example()
        commands.execute("media.toggle_play", False)
        post(Post.APP_CLEAR)

    @pytest.mark.skip(
        reason=(
            "Passes on its own, but in a parallel full-suite run the "
            "xdist worker died with a Windows heap-corruption error "
            "(0xc0000374) inside the Qt media engine while changing the rate. "
            "Skipped until that is understood."
        )
    )
    def test_change_playback_rate_with_audio_loaded(self, tilia, qtui):
        # Turning the playback-rate spinbox on the player toolbar
        # while audio is loaded must change the player's actual rate.
        load_example()

        qtui.player_toolbar.playback_rate_spinbox.setValue(1.5)

        assert tilia.player.player.playbackRate() == 1.5


class TestStop:
    # Unlike the tests above, these never start playback: they only load
    # media and stop it, so they don't hit the engine timing that makes the
    # rest of this module flaky on CI, and they run there.

    def test_stop_while_paused_resets_to_start(self, tilia):
        # Stopping while paused (i.e. not playing, but not at the
        # start either) must bring the current time back to the start and
        # leave playback stopped.
        load_example()
        tilia.player.current_time = 5.0

        commands.get_qaction("media.stop").trigger()

        assert tilia.player.current_time == 0
        assert not tilia.player.is_playing

    def test_stop_while_stopped_changes_nothing(self, tilia):
        # Stopping while already stopped (current_time == 0, not
        # playing) must be a no-op. Player.stop (tilia/media/player/base.py)
        # early-returns before touching the engine in that case.
        load_example()

        with patch.object(tilia.player, "_engine_stop") as mock_engine_stop:
            commands.get_qaction("media.stop").trigger()

        mock_engine_stop.assert_not_called()
        assert tilia.player.current_time == 0
        assert not tilia.player.is_playing
