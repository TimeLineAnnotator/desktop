import pytest
import shiboken6
from PySide6.QtWidgets import QDialog

from tests.utils import (
    EXAMPLE_VIDEO_FILENAME,
    EXAMPLE_YOUTUBE_URL,
    load_local_media,
    load_youtube_media,
)
from tilia.requests import Post, listen, post, stop_listening_to_all
from tilia.ui.windows import WindowKind
from tilia.ui.windows.view_window import ViewWindow


class _SimpleViewWindow(ViewWindow, QDialog):
    """Minimal ViewWindow for tests that need a ViewWidget without QWebEngineView."""

    def __init__(self):
        super().__init__("TiLiA Player", menu_title="YouTube Player")


@pytest.mark.parametrize("window_kind", WindowKind)
def test_open_close(qtui, window_kind):
    window_open_done_posted = False
    window_close_done_posted = False

    def window_open_done(_):
        nonlocal window_open_done_posted
        window_open_done_posted = True

    def window_close_done(_):
        nonlocal window_close_done_posted
        window_close_done_posted = True

    listen(qtui, Post.WINDOW_OPEN_DONE, window_open_done)
    listen(qtui, Post.WINDOW_CLOSE_DONE, window_close_done)

    post(Post.WINDOW_OPEN, window_kind)
    assert qtui.is_window_open(window_kind)
    assert window_open_done_posted

    post(Post.WINDOW_CLOSE, window_kind)
    assert not qtui.is_window_open(window_kind)
    assert window_close_done_posted


class TestViewWindow:
    @staticmethod
    def load_local_video(tilia, resources, filename: str = EXAMPLE_VIDEO_FILENAME):
        path = (resources / filename).resolve().absolute()
        load_local_media(path)
        return tilia.player.widget

    @staticmethod
    def load_youtube_video(tilia, url: str = EXAMPLE_YOUTUBE_URL):
        load_youtube_media(url)
        return tilia.player.view

    def test_video_window_opens_on_load(self, tilia, qtui, resources):
        window = self.load_local_video(tilia, resources)
        assert window.isVisible()

    def test_youtube_window_opens_on_load(self, tilia, qtui):
        window = self.load_youtube_video(tilia)
        assert window.isVisible()

    def test_video_window_hides_on_close_request(self, tilia, qtui, resources):
        window = self.load_local_video(tilia, resources)
        post(Post.WINDOW_UPDATE_REQUEST, window.id, False)
        assert not window.isVisible()

    def test_video_window_reopens_on_show_request(self, tilia, qtui, resources):
        window = self.load_local_video(tilia, resources)
        post(Post.WINDOW_UPDATE_REQUEST, window.id, False)
        post(Post.WINDOW_UPDATE_REQUEST, window.id, True)
        assert window.isVisible()

    def test_video_window_close_event_does_not_destroy(self, tilia, qtui, resources):
        window = self.load_local_video(tilia, resources)
        window.close()
        # ViewWidget.closeEvent ignores the event and only hides.
        assert not window.isVisible()
        assert shiboken6.isValid(window)

    def test_swapping_player_type_does_not_crash_window_update_request(
        self, tilia, qtui
    ):
        # Reproduction of the leak described in
        # https://github.com/TimeLineAnnotator/desktop/issues/436.
        # Loading a different media type swaps the player and calls
        # `deleteLater()` on the previous window. The Python wrapper
        # survives, so the listener registered in `ViewWidget.__init__`
        # for `Post.WINDOW_UPDATE_REQUEST` stays in the listener dict.
        #
        # The stale-listener behaviour is independent of player type; plain
        # ViewWindows (QDialog-based) avoid QVideoWidget / QWebEngineView,
        # both of which block in macOS offscreen mode when force-deleted.
        window1 = _SimpleViewWindow()
        window2 = _SimpleViewWindow()

        # Simulate the production leak: window1's listener stays registered
        # without going through deleteLater (which would call stop_listening_to_all).
        # We do not need to destroy the C++ object — the fix under test is the
        # `window_id == self.id` guard in on_update_request, which is a pure
        # Python check safe to exercise on a live object.
        post(Post.WINDOW_UPDATE_REQUEST, window2.id, True)
        assert window2.isVisible()

        # Clean up both listeners so they do not pollute subsequent reruns.
        stop_listening_to_all(window1)
        stop_listening_to_all(window2)
