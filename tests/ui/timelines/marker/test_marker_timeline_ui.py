from unittest.mock import patch

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor

from tests.mock import PatchGet
from tilia.requests import Post, Get, post
from tilia.ui import actions
from tilia.ui.actions import TiliaAction

from tilia.ui.timelines.marker import MarkerUI


def marker_ui_pos(marker_ui: MarkerUI):
    x = int(marker_ui.x)
    y = int(MarkerUI.HEIGHT / 2)
    return QPoint(x, y)


class TestActions:
    def test_change_color(self, marker_tlui):
        mrk, ui = marker_tlui.create_marker(time=0)

        marker_tlui.select_all_elements()
        with patch("tilia.ui.dialogs.basic.ask_for_color", lambda _: QColor("#000")):
            actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_SET)

        assert mrk.color == "#000000"

    def test_reset_color(self, marker_tlui):
        mrk, ui = marker_tlui.create_marker(time=0)

        marker_tlui.select_all_elements()
        with patch("tilia.ui.dialogs.basic.ask_for_color", lambda _: QColor("#000")):
            actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_SET)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_RESET)

        assert mrk.color is None

    def test_on_add_marker(self, marker_tlui, tluis):
        with PatchGet(
            "tilia.ui.timelines.marker.request_handlers", Get.MEDIA_CURRENT_TIME, 0.101
        ):
            post(Post.MARKER_ADD)

        assert len(marker_tlui) == 1
        assert marker_tlui[0].get_data("time") == 0.101

    def test_on_delete_marker(self, marker_tlui):
        _, mui = marker_tlui.create_marker(0)
        marker_tlui.select_element(mui)

        assert len(marker_tlui) == 1

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(marker_tlui) == 0

    def test_on_delete_marker_multiple_markers(self, marker_tlui, tluis):
        _, mui1 = marker_tlui.create_marker(0)
        _, mui2 = marker_tlui.create_marker(1)
        _, mui3 = marker_tlui.create_marker(2)

        marker_tlui.select_element(mui1)
        marker_tlui.select_element(mui2)
        marker_tlui.select_element(mui3)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(marker_tlui) == 0


class TestUndoRedo:
    def test_undo_redo_add_marker(self, marker_tlui, tluis):
        post(Post.APP_RECORD_STATE, "test state")

        with PatchGet(
            "tilia.ui.timelines.marker.request_handlers", Get.MEDIA_CURRENT_TIME, 0.101
        ):
            actions.trigger(TiliaAction.MARKER_ADD)

        post(Post.EDIT_UNDO)
        assert len(marker_tlui) == 0

        post(Post.EDIT_REDO)
        assert len(marker_tlui) == 1

    def test_undo_redo_delete_marker_multiple_markers(self, marker_tlui, tluis):
        marker_tlui.create_marker(0)
        marker_tlui.create_marker(0.1)
        marker_tlui.create_marker(0.2)

        marker_tlui.select_all_elements()

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        post(Post.EDIT_UNDO)
        assert len(marker_tlui.elements) == 3

        post(Post.EDIT_REDO)
        assert len(marker_tlui.elements) == 0

    def test_undo_redo_delete_marker(self, marker_tlui, tluis):
        # 'tlui_clct' is needed as it subscriber to toolbar event
        # and forwards it to marker timeline

        marker_tlui.create_marker(0)

        post(Post.APP_RECORD_STATE, "test state")

        marker_tlui.select_element(marker_tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        post(Post.EDIT_UNDO)
        assert len(marker_tlui.elements) == 1

        post(Post.EDIT_REDO)
        assert len(marker_tlui.elements) == 0
