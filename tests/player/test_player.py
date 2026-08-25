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


class TestPlayerWithWebEngineView:
    """Regression coverage for QtAudioPlayer's worker-thread fix: loading/
    playing/stopping local audio must not hang or crash once a
    QWebEngineView (score view, YouTube player) exists in-process. Before
    the fix, QtPlayer's wait_for_signal blocked on a nested QEventLoop on
    the GUI thread, which could reenter WebEngine's pending IPC work and
    segfault."""

    def test_load_play_stop_audio_with_webengineview_alive(self, tilia):
        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        try:
            post(Post.APP_MEDIA_LOAD, EXAMPLE_MEDIA_PATH)
            commands.execute("media.toggle_play", True)
            commands.execute("media.toggle_play", False)
            post(Post.APP_CLEAR)
        finally:
            view.deleteLater()
