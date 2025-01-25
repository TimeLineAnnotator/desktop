import pytest

from tilia.requests import post, Post, listen
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
