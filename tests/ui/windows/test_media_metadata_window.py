import pytest

from tests.mock import Serve
from tilia.requests import post, Post, Get
from tilia.ui.windows import WindowKind


@pytest.fixture
def media_metadata_window(qtui):
    post(Post.WINDOW_OPEN, WindowKind.MEDIA_METADATA)
    window = qtui._windows[WindowKind.MEDIA_METADATA]
    yield window
    with Serve(Get.FROM_USER_YES_OR_NO, True):
        window.close()


def test_open(media_metadata_window):
    assert media_metadata_window


def test_close(qtui, media_metadata_window):
    media_metadata_window.close()
    assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)


def test_edit_field_value(qtui, media_metadata_window, tilia_state):
    media_metadata_window.metadata["title"].setText("New Title")
    media_metadata_window.apply_fields()
    media_metadata_window.close()

    assert tilia_state.metadata["title"] == "New Title"


def test_do_not_confirm_close(qtui, media_metadata_window, tilia_state):
    prev_title = tilia_state.metadata["title"]
    media_metadata_window.metadata["title"].setText("New Title")
    with Serve(Get.FROM_USER_YES_OR_NO, False):
        media_metadata_window.close()

    assert qtui.is_window_open(WindowKind.MEDIA_METADATA)
    assert tilia_state.metadata["title"] == prev_title


def test_confirm_close_discards_changes(qtui, media_metadata_window, tilia_state):
    prev_title = tilia_state.metadata["title"]
    media_metadata_window.metadata["title"].setText("New Title")
    with Serve(Get.FROM_USER_YES_OR_NO, True):
        media_metadata_window.close()

    assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)
    assert tilia_state.metadata["title"] == prev_title
