from unittest.mock import Mock, patch

from tests.mock import PatchPost
from tilia.requests import Post


class TestRightClick:
    def test_right_click(self, beat_tlui):
        _, hui = beat_tlui.create_beat(0)
        with patch(
            "tilia.ui.timelines.beat.context_menu.BeatContextMenu.exec"
        ) as exec_mock:
            hui.on_right_click(0, 0, None)

        exec_mock.assert_called_once()


class TestDoubleClick:
    def test_posts_seek(self, beat_tlui):
        beat_tlui.create_beat(10)
        with PatchPost("tilia.ui.timelines.beat.element", Post.PLAYER_SEEK) as mock:
            beat_tlui[0].on_double_left_click(None)

        mock.assert_called_with(Post.PLAYER_SEEK, 10)

    def test_does_not_trigger_drag(self, beat_tlui):
        beat_tlui.create_beat(0)
        mock = Mock()
        beat_tlui[0].setup_drag = mock
        beat_tlui[0].on_double_left_click(None)

        mock.assert_not_called()
