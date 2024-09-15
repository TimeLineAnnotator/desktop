from unittest.mock import patch, Mock

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from tests.mock import PatchPost
from tilia.requests import Post
from tilia.ui.coords import get_time_by_x, get_x_by_time

MODULE = "tilia.ui.timelines.marker.element"


class TestMarker:
    def test_creation(self, mrkui):
        assert mrkui
        for item in mrkui.child_items():
            assert item

    def test_pen_style_is_no_pen(self, mrkui):
        assert mrkui.body.pen().style() == Qt.PenStyle.NoPen

    def test_pen_color_is_black(self, mrkui):
        assert mrkui.body.pen().color() == QColor("black")

    def test_update_label(self, mrkui):
        mrkui.set_data("label", "new")
        assert mrkui.label.toPlainText() == "new"

    def test_update_time(self, mrkui):
        mrkui.set_data("time", 100)
        assert mrkui.x == get_x_by_time(100)

    def test_update_color(self, mrkui):
        mrkui.set_data("color", "#010101")
        assert mrkui.body.brush().color() == QColor("#010101")

    def test_right_click(self, marker_tlui):
        marker_tlui.create_marker(0)
        with patch(
            "tilia.ui.timelines.marker.context_menu.MarkerContextMenu.exec"
        ) as exec_mock:
            marker_tlui[0].on_right_click(0, 0, None)

        exec_mock.assert_called_once()


class TestMarkerDrag:
    def test_setup_drag(self, mrkui):
        with patch(MODULE + ".DragManager") as manager_mock:
            mrkui.setup_drag()

        manager_mock.assert_called_once()

    def test_before_each_drag(self, mrkui):
        assert not mrkui.dragged
        mrkui.before_each_drag()
        assert mrkui.dragged

    def test_after_each_drag(self, mrkui):
        mrkui.after_each_drag(202)
        assert mrkui.get_data("time") == get_time_by_x(202)

    def test_on_drag_end_when_dragged(self, mrkui):
        mrkui.dragged = True
        with PatchPost(MODULE, Post.ELEMENT_DRAG_END) as post_mock:
            mrkui.on_drag_end()

        post_mock.assert_called_once()
        assert not mrkui.dragged

    def test_on_drag_end_when_not_dragged(self, mrkui):
        mrkui.dragged = False
        with PatchPost(MODULE, Post.ELEMENT_DRAG_END) as post_mock:
            mrkui.on_drag_end()

        post_mock.assert_not_called()


class TestMarkerSelected:
    def test_on_select(self, mrkui):
        mrkui.body.on_select = Mock()
        mrkui.on_select()
        mrkui.body.on_select.assert_called_once()

    def test_on_deselect(self, mrkui):
        mrkui.body.on_deselect = Mock()
        mrkui.on_deselect()
        mrkui.body.on_deselect.assert_called_once()


class TestDoubleClick:
    def test_posts_seek(self, marker_tlui):
        marker_tlui.create_marker(10)
        with PatchPost("tilia.ui.timelines.marker.element", Post.PLAYER_SEEK) as mock:
            marker_tlui[0].on_double_left_click(None)

        mock.assert_called_with(Post.PLAYER_SEEK, 10)

    def test_does_not_trigger_drag(self, marker_tlui):
        marker_tlui.create_marker(0)
        mock = Mock()
        marker_tlui[0].setup_drag = mock
        marker_tlui[0].on_double_left_click(None)

        mock.assert_not_called()
