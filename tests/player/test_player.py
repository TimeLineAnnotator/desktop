from tests.constants import EXAMPLE_MEDIA_PATH, EXAMPLE_VIDEO_PATH
from tilia.requests import Post, post
from tilia.ui import commands


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


class TestVideoPlayer:
    """QtVideoPlayer needs Get.MAIN_WINDOW (served by QtUI), unlike the
    audio-only tests above which only need the bare App (`tilia`)."""

    def test_load_play_stop_video(self, qtui):
        post(Post.APP_MEDIA_LOAD, EXAMPLE_VIDEO_PATH)
        commands.execute("media.toggle_play", True)
        commands.execute("media.toggle_play", False)
        post(Post.APP_CLEAR)


class TestVideoPlayerWithWebEngineView:
    """Regression coverage for QtVideoPlayer's worker-thread fix: loading/
    playing/stopping local video must not hang or crash once a
    QWebEngineView (score view, YouTube player) exists in-process -- the
    same hazard QtAudioPlayer was fixed for, now also fixed for video."""

    def test_load_play_stop_video_with_webengineview_alive(self, qtui):
        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        try:
            post(Post.APP_MEDIA_LOAD, EXAMPLE_VIDEO_PATH)
            commands.execute("media.toggle_play", True)
            commands.execute("media.toggle_play", False)
            post(Post.APP_CLEAR)
        finally:
            view.deleteLater()
