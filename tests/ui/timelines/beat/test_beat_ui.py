from unittest.mock import Mock, patch

from PyQt6.QtCore import Qt

from tilia.requests import get, Get, Post, post
from tilia.ui.coords import get_x_by_time


class TestRightClick:
    def test_right_click(self, beat_tlui):
        _, hui = beat_tlui.create_beat(0)
        with patch(
            "tilia.ui.timelines.beat.context_menu.BeatContextMenu.exec"
        ) as exec_mock:
            hui.on_right_click(0, 0, None)

        exec_mock.assert_called_once()


def click_beat_ui(beat_ui, button='left', modifier=None, double=False):
    request = {
        'left': Post.TIMELINE_VIEW_LEFT_CLICK,
        'right': Post.TIMELINE_VIEW_RIGHT_CLICK,
    }[button]

    modifier = {
        None: Qt.KeyboardModifier.NoModifier
    }[modifier]

    post(
        request,
        beat_ui.timeline_ui.view,
        get_x_by_time(beat_ui.time),
        beat_ui.height / 2,
        beat_ui.body,
        modifier,
        double=double,
    )


def move_mouse_to(tlui, x, y):
    post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x, y)


class TestDoubleClick:
    def test_triggers_seek(self, beat_tlui, qtbot):
        b, bui = beat_tlui.create_beat(10)
        click_beat_ui(bui, double=True)
        assert get(Get.MEDIA_CURRENT_TIME) == 10

    def test_does_not_trigger_drag(self, beat_tlui):
        _, bui = beat_tlui.create_beat(0)
        click_beat_ui(bui, double=True)
        move_mouse_to(beat_tlui, int(get_x_by_time(50)), int(bui.height / 2))
        assert bui.get_data('time') == 0



