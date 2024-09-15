import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor

from tests.mock import PatchGet, Serve
from tests.ui.timelines.interact import click_timeline_ui
from tests.ui.timelines.marker.interact import click_marker_ui
from tilia.requests import Post, Get, post
from tilia.ui.actions import TiliaAction

from tilia.ui.timelines.marker import MarkerUI
from tilia.ui.windows import WindowKind


def marker_ui_pos(marker_ui: MarkerUI):
    x = int(marker_ui.x)
    y = int(MarkerUI.HEIGHT / 2)
    return QPoint(x, y)


@pytest.fixture
def get_inspect(qtui, actions):
    post(Post.WINDOW_INSPECT_OPEN)

    def _get_inspect():
        return qtui._windows[WindowKind.INSPECT]

    yield _get_inspect
    post(Post.WINDOW_INSPECT_CLOSE)


class TestCreateDelete:
    def test_create(self, marker_tlui, tluis, tilia_state):
        tilia_state.current_time = 11
        post(Post.MARKER_ADD)

        assert len(marker_tlui) == 1
        assert marker_tlui[0].get_data("time") == 11

    def test_create_at_same_time_succeeds(self, marker_tlui, actions):
        actions.trigger(TiliaAction.MARKER_ADD)
        actions.trigger(TiliaAction.MARKER_ADD)

        assert len(marker_tlui) == 2

    def test_delete(self, marker_tlui, actions):
        marker_tlui.create_marker(0)
        marker_tlui.select_element(marker_tlui[0])

        assert len(marker_tlui) == 1

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(marker_tlui) == 0

    def test_undo_redo_add_marker(self, marker_tlui, tluis, actions):
        post(Post.APP_RECORD_STATE, "test state")

        with PatchGet(
            "tilia.ui.timelines.marker.request_handlers", Get.MEDIA_CURRENT_TIME, 0.101
        ):
            actions.trigger(TiliaAction.MARKER_ADD)

        post(Post.EDIT_UNDO)
        assert len(marker_tlui) == 0

        post(Post.EDIT_REDO)
        assert len(marker_tlui) == 1

    def test_undo_redo_delete_marker_multiple_markers(self, marker_tlui, tluis, actions):
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

    def test_undo_redo_delete_marker(self, marker_tlui, tluis, actions):

        marker_tlui.create_marker(0)

        post(Post.APP_RECORD_STATE, "test state")

        marker_tlui.select_element(marker_tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        post(Post.EDIT_UNDO)
        assert len(marker_tlui.elements) == 1

        post(Post.EDIT_REDO)
        assert len(marker_tlui.elements) == 0


class TestEditWithInspectDialog:
    @pytest.mark.parametrize(
        "field_name,attr,value",
        [("Comments", "comments", "abc"), ("Label", "label", "abc")],
    )
    def test_set_attr(self, field_name, attr, value, marker_tlui, get_inspect, actions):
        actions.trigger(TiliaAction.MARKER_ADD)
        click_marker_ui(marker_tlui[0])
        inspect_win = get_inspect()
        inspect_win.field_name_to_widgets[field_name][1].setText(value)
        assert marker_tlui[0].get_data(attr) == value


class TestChangeColor:
    TEST_COLOR = "#000000"
    
    def _set_marker_color(self, marker_tlui, actions):
        """Assumes there is a single marker on timeline"""
        marker_tlui.select_all_elements()
        with Serve(Get.FROM_USER_COLOR, (True, QColor(self.TEST_COLOR))):
            actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_SET)

    def test_set_color(self, marker_tlui, actions):
        marker_tlui.create_marker(0)
        self._set_marker_color(marker_tlui, actions)
        assert marker_tlui[0].get_data("color") == self.TEST_COLOR

    def test_undo_set_color(self, marker_tlui, actions):
        actions.trigger(TiliaAction.MARKER_ADD)
        self._set_marker_color(marker_tlui, actions)
        actions.trigger(TiliaAction.EDIT_UNDO)
        assert marker_tlui[0].get_data('color') is None

    def test_redo_set_color(self, marker_tlui, actions):
        actions.trigger(TiliaAction.MARKER_ADD)
        self._set_marker_color(marker_tlui, actions)
        actions.trigger(TiliaAction.EDIT_UNDO)
        actions.trigger(TiliaAction.EDIT_REDO)
        assert marker_tlui[0].get_data('color') == self.TEST_COLOR

    def test_reset_color(self, marker_tlui, actions):
        marker_tlui.create_marker(time=0)
        self._set_marker_color(marker_tlui, actions)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_RESET)

        assert marker_tlui[0].get_data('color') is None

    def test_undo_reset_color(self, marker_tlui, actions):
        marker_tlui.create_marker(time=0)
        self._set_marker_color(marker_tlui, actions)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_RESET)
        actions.trigger(TiliaAction.EDIT_UNDO)

        assert marker_tlui[0].get_data('color') == self.TEST_COLOR

    def test_redo_reset_color(self, marker_tlui, actions):
        marker_tlui.create_marker(time=0)
        self._set_marker_color(marker_tlui, actions)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_RESET)
        actions.trigger(TiliaAction.EDIT_UNDO)
        actions.trigger(TiliaAction.EDIT_REDO)

        assert marker_tlui[0].get_data('color') is None


class TestDelete:
    def test_on_delete_marker_multiple_markers(self, marker_tlui, tluis, actions):
        marker_tlui.create_marker(0)
        marker_tlui.create_marker(1)
        marker_tlui.create_marker(2)

        marker_tlui.select_element(marker_tlui[0])
        marker_tlui.select_element(marker_tlui[1])
        marker_tlui.select_element(marker_tlui[2])

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(marker_tlui) == 0


class TestCopyPaste:
    def test_paste_single_into_timeline(self, marker_tlui, tilia_state, actions):
        marker_tlui.create_marker(0, label="copy me")
        click_marker_ui(marker_tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)

        tilia_state.current_time = 10
        click_timeline_ui(marker_tlui, 50)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert len(marker_tlui) == 2
        assert marker_tlui[1].get_data("time") == 10
        assert marker_tlui[1].get_data("label") == "copy me"

    def test_paste_single_into_selected_element(
        self, marker_tlui, tilia_state, actions
    ):
        marker_tlui.create_marker(0, label="copy me")
        marker_tlui.create_marker(10, label="paste here")
        click_marker_ui(marker_tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)

        click_marker_ui(marker_tlui[1])

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert len(marker_tlui) == 2
        assert marker_tlui[1].get_data("label") == "copy me"

    def test_paste_multiple_into_timeline(self, marker_tlui, tilia_state, actions):
        marker_tlui.create_marker(0, label="first")
        marker_tlui.create_marker(10, label="second")
        marker_tlui.create_marker(20, label="third")
        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="shift")
        click_marker_ui(marker_tlui[2], modifier="shift")
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)

        tilia_state.current_time = 50
        click_timeline_ui(marker_tlui, 50)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert len(marker_tlui) == 6
        for index, time, label in [
            (3, 50, "first"),
            [4, 60, "second"],
            [5, 70, "third"],
        ]:
            assert marker_tlui[index].get_data("time") == time
            assert marker_tlui[index].get_data("label") == label

    def test_paste_multiple_into_selected_element(self, marker_tlui, actions):
        marker_tlui.create_marker(0, label="first")
        marker_tlui.create_marker(10, label="second")
        marker_tlui.create_marker(20, label="third")
        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="shift")
        click_marker_ui(marker_tlui[2], modifier="shift")
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)

        click_marker_ui(marker_tlui[2])

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert len(marker_tlui) == 5
        for index, time, label in [
            (2, 20, "first"),
            [3, 30, "second"],
            [4, 40, "third"],
        ]:
            assert marker_tlui[index].get_data("time") == time
            assert marker_tlui[index].get_data("label") == label
