import pytest
import shiboken6

from tests.utils import (
    load_local_media,
    EXAMPLE_VIDEO_FILENAME,
    EXAMPLE_YOUTUBE_URL,
    load_youtube_media,
)
from tilia.requests import Post, listen, post
from tilia.ui.windows import WindowKind


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
        self, tilia, qtui, resources
    ):
        # Reproduction of the leak described in
        # https://github.com/TimeLineAnnotator/desktop/issues/436.
        # Loading a different media type swaps the player and calls
        # `deleteLater()` on the previous window. The Python wrapper
        # survives, so the listener registered in `ViewWidget.__init__`
        # for `Post.WINDOW_UPDATE_REQUEST` stays in the listener dict.

        window1 = self.load_local_video(tilia, resources)
        window2 = self.load_youtube_video(tilia)

        # In production the C++ object is destroyed asynchronously by the
        # event loop; here we must force it with `shiboken6.delete`.
        shiboken6.delete(window1)

        post(Post.WINDOW_UPDATE_REQUEST, window2.id, True)
