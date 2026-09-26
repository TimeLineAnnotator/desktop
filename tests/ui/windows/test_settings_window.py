import pytest

from tilia.requests import Post, post
from tilia.settings import settings
from tilia.ui.windows import WindowKind


@pytest.fixture
def settings_window(qtui):
    post(Post.WINDOW_OPEN, WindowKind.SETTINGS)
    window = qtui._windows[WindowKind.SETTINGS]
    yield window
    window.close()


def test_changing_and_applying_a_setting_takes_effect(settings_window, range_tlui):
    original = range_tlui.default_row_height
    new_height = original + 30

    widget = settings_window.settings["range_timeline"]["default_row_height"]
    widget.setValue(new_height)
    settings_window.apply_fields()

    # the setting itself was updated...
    assert settings.get("range_timeline", "default_row_height") == new_height
    # ...and applying it took effect on an already-open timeline.
    assert range_tlui.default_row_height == new_height
