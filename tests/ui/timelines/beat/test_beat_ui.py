from unittest.mock import patch

from tests.ui.timelines.beat.interact import click_beat_ui
from tests.ui.timelines.interact import drag_mouse_in_timeline_view
from tilia.requests import get, Get
from tilia.ui.coords import get_x_by_time


class TestRightClick:
    def test_right_click(self, beat_tlui):
        _, hui = beat_tlui.create_beat(0)
        with patch(
            "tilia.ui.timelines.beat.context_menu.BeatContextMenu.exec"
        ) as exec_mock:
            hui.on_right_click(0, 0, None)

        exec_mock.assert_called_once()


class TestDoubleClick:
    def test_triggers_seek(self, beat_tlui, qtbot):
        b, bui = beat_tlui.create_beat(10)
        click_beat_ui(bui, double=True)
        assert get(Get.MEDIA_CURRENT_TIME) == 10

    def test_does_not_trigger_drag(self, beat_tlui):
        _, bui = beat_tlui.create_beat(0)
        click_beat_ui(bui, double=True)
        drag_mouse_in_timeline_view(get_x_by_time(50), bui.height / 2)
        assert bui.get_data("time") == 0
