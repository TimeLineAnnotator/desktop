from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QInputDialog

from tests.mock import Serve
from tests.ui.test_qtui import get_toolbars_of_class
from tests.ui.timelines.interact import (
    click_timeline_ui,
    drag_mouse_in_timeline_view,
    press_key,
    type_string,
)
from tests.ui.timelines.marker.interact import click_marker_ui, get_marker_ui_center
from tests.utils import undoable, get_action, get_submenu, get_main_window_menu
from tilia.requests import Post, Get, post
from tilia.ui.actions import get_qaction
from tilia.ui.coords import time_x_converter

from tilia.ui.timelines.marker import MarkerTimelineToolbar
from tilia.ui.timelines.marker.context_menu import (
    MarkerContextMenu,
    MarkerTimelineUIContextMenu,
)
from tilia.ui.windows import WindowKind


class TestCreateDelete:
    def test_create(self, marker_tlui, tluis, tilia_state, user_actions):
        tilia_state.current_time = 11
        user_actions.trigger("marker_add")

        assert len(marker_tlui) == 1
        assert marker_tlui[0].get_data("time") == 11

    def test_create_at_same_time_fails(self, marker_tlui, user_actions):
        user_actions.trigger("marker_add")
        user_actions.trigger("marker_add")

        assert len(marker_tlui) == 1

    def test_delete(self, marker_tlui, user_actions):
        user_actions.trigger("marker_add")
        click_marker_ui(marker_tlui[0])

        with undoable():
            user_actions.trigger("timeline_element_delete")
            assert len(marker_tlui) == 0

    def test_delete_multiple(self, marker_tlui, user_actions, tilia_state):
        user_actions.trigger("marker_add")
        tilia_state.current_time = 10
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="ctrl")

        with undoable():
            user_actions.trigger("timeline_element_delete")
            assert len(marker_tlui) == 0


class TestSetResetColor:
    TEST_COLOR = "#000000"

    def set_color_on_all_markers(self, marker_tlui, actions):
        """Assumes there is a single marker on timeline"""
        marker_tlui.select_all_elements()
        with Serve(Get.FROM_USER_COLOR, (True, QColor(self.TEST_COLOR))):
            actions.trigger("timeline_element_color_set")

    def test_set_color(self, marker_tlui, user_actions):
        user_actions.trigger("marker_add")
        with undoable():
            self.set_color_on_all_markers(marker_tlui, user_actions)
            assert marker_tlui[0].get_data("color") == self.TEST_COLOR

    def test_set_color_multiple_markers(self, marker_tlui, user_actions, tilia_state):
        user_actions.trigger("marker_add")
        tilia_state.current_time = 10
        user_actions.trigger("marker_add")
        with undoable():
            self.set_color_on_all_markers(marker_tlui, user_actions)
            for marker in marker_tlui:
                assert marker.get_data("color") == self.TEST_COLOR

    def test_reset_color(self, marker_tlui, user_actions):
        user_actions.trigger("marker_add")
        self.set_color_on_all_markers(marker_tlui, user_actions)

        with undoable():
            user_actions.trigger("timeline_element_color_reset")
            assert marker_tlui[0].get_data("color") is None

    def test_reset_color_multiple_markers(self, marker_tlui, user_actions, tilia_state):
        user_actions.trigger("marker_add")
        tilia_state.current_time = 10
        user_actions.trigger("marker_add")
        self.set_color_on_all_markers(marker_tlui, user_actions)

        with undoable():
            user_actions.trigger("timeline_element_color_reset")
            for marker in marker_tlui:
                assert marker.get_data("color") is None

    def test_cancel_color_dialog(self, marker_tlui, user_actions, tilia_state):
        user_actions.trigger("marker_add")
        click_marker_ui(marker_tlui[0])
        with patch.object(QColorDialog, "getColor", return_value=QColor("invalid")):
            user_actions.trigger("timeline_element_color_set")

        assert marker_tlui[0].get_data("color") is None


class TestCopyPaste:
    def test_shortcut(self, marker_tlui, tilia_state):
        marker_tlui.create_marker(0)
        click_marker_ui(marker_tlui[0])
        press_key("c", modifier=Qt.KeyboardModifier.ControlModifier)
        click_timeline_ui(marker_tlui, 50)

        tilia_state.current_time = 10
        press_key("v", modifier=Qt.KeyboardModifier.ControlModifier)

        assert len(marker_tlui) == 2

    def test_paste_single_into_timeline(self, marker_tlui, tilia_state, user_actions):
        marker_tlui.create_marker(0, label="copy me")
        click_marker_ui(marker_tlui[0])
        user_actions.trigger("timeline_element_copy")

        tilia_state.current_time = 10
        click_timeline_ui(marker_tlui, 50)

        with undoable():
            user_actions.trigger("timeline_element_paste")

            assert len(marker_tlui) == 2
            assert marker_tlui[1].get_data("time") == 10
            assert marker_tlui[1].get_data("label") == "copy me"

    def test_paste_single_into_selected_element(
        self, marker_tlui, tilia_state, user_actions
    ):
        user_actions.trigger("marker_add")
        tilia_state.current_time = 10
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])
        press_key("Enter")
        type_string("copy me")
        user_actions.trigger("timeline_element_copy")
        click_marker_ui(marker_tlui[1])

        with undoable():
            user_actions.trigger("timeline_element_paste")

            assert len(marker_tlui) == 2
            assert marker_tlui[1].get_data("label") == "copy me"

    def test_paste_multiple_into_timeline(self, marker_tlui, tilia_state, user_actions):
        for time, label in [(0, "first"), (10, "second"), (20, "third")]:
            tilia_state.current_time = time
            user_actions.trigger("marker_add")
            click_marker_ui(marker_tlui[-1])
            user_actions.trigger("timeline_element_inspect")
            type_string(label)

        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="ctrl")
        click_marker_ui(marker_tlui[2], modifier="ctrl")
        user_actions.trigger("timeline_element_copy")

        click_timeline_ui(marker_tlui, 100)  # deselect markers
        tilia_state.current_time = 50

        with undoable():
            user_actions.trigger("timeline_element_paste")

        assert len(marker_tlui) == 6
        for index, time, label in [
            (3, 50, "first"),
            [4, 60, "second"],
            [5, 70, "third"],
        ]:
            assert marker_tlui[index].get_data("time") == time
            assert marker_tlui[index].get_data("label") == label

    def test_paste_multiple_into_selected_element(
        self, marker_tlui, user_actions, tilia_state
    ):
        for time, label in [(0, "first"), (10, "second"), (20, "third")]:
            tilia_state.current_time = time
            user_actions.trigger("marker_add")
            click_marker_ui(marker_tlui[-1])
            user_actions.trigger("timeline_element_inspect")
            type_string(label)

        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="ctrl")
        click_marker_ui(marker_tlui[2], modifier="ctrl")
        user_actions.trigger("timeline_element_copy")

        click_marker_ui(marker_tlui[2])

        with undoable():
            user_actions.trigger("timeline_element_paste")

        assert len(marker_tlui) == 5
        for index, time, label in [
            (2, 20, "first"),
            [3, 30, "second"],
            [4, 40, "third"],
        ]:
            assert marker_tlui[index].get_data("time") == time
            assert marker_tlui[index].get_data("label") == label


class TestSelect:
    def test_select(self, marker_tlui, tluis, user_actions):
        marker_tlui.create_marker(10)
        click_marker_ui(marker_tlui[0])

        assert marker_tlui[0] in marker_tlui.selected_elements

    def test_deselect(self, marker_tlui, tluis, user_actions):
        marker_tlui.create_marker(10)
        click_marker_ui(marker_tlui[0])
        click_timeline_ui(marker_tlui, 0)

        assert len(marker_tlui.selected_elements) == 0

    def test_box_selection(self, marker_tlui, tluis, user_actions):
        marker_tlui.create_marker(10)
        marker_tlui.create_marker(20)
        marker_tlui.create_marker(30)

        click_timeline_ui(marker_tlui, 5, button="left")

        drag_mouse_in_timeline_view(*get_marker_ui_center(marker_tlui[1]))

        assert len(marker_tlui.selected_elements) == 2
        assert marker_tlui[0] in marker_tlui.selected_elements
        assert marker_tlui[1] in marker_tlui.selected_elements

    def test_box_deselection(self, marker_tlui, tluis, user_actions):
        marker_tlui.create_marker(10)
        marker_tlui.create_marker(20)
        marker_tlui.create_marker(30)

        click_timeline_ui(marker_tlui, 5, button="left")

        drag_mouse_in_timeline_view(
            *get_marker_ui_center(marker_tlui[2]), release=False
        )
        drag_mouse_in_timeline_view(0, 0)

        assert not marker_tlui.selected_elements


class TestDrag:
    def test_drag(self, marker_tlui, tluis, user_actions, tilia_state):
        tilia_state.duration = 100
        tilia_state.current_time = 10
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])

        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(20), 0)
            assert marker_tlui[0].get_data("time") == 20

    def test_drag_beyond_start(self, marker_tlui, tluis, user_actions, tilia_state):
        tilia_state.duration = 100
        tilia_state.current_time = 10
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])

        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(0) - 200, 0)
            assert marker_tlui[0].get_data("time") == 0

    def test_drag_beyond_end(self, marker_tlui, tluis, user_actions, tilia_state):
        tilia_state.duration = 100
        tilia_state.current_time = 10
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])

        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(100) + 200, 0)
            assert marker_tlui[0].get_data("time") == 100


class TestElementContextMenu:
    def test_is_shown_on_right_click(
        self, marker_tlui, tluis, user_actions, tilia_state
    ):
        marker_tlui.create_marker(0)

        with patch.object(MarkerContextMenu, "exec") as mock:
            click_marker_ui(marker_tlui[0], button="right")

        mock.assert_called_once()

    def test_has_the_right_options(self, marker_tlui, tluis, user_actions, tilia_state):
        marker_tlui.create_marker(0)

        context_menu = marker_tlui[0].CONTEXT_MENU_CLASS((marker_tlui[0]))

        expected = (
            "timeline_element_inspect",
            "timeline_element_delete",
            "timeline_element_color_reset",
            "timeline_element_color_set",
            "timeline_element_copy",
            "timeline_element_paste",
        )

        for action in expected:
            assert get_qaction(action) in context_menu.actions()


class TestTimelineUIContextMenu:
    def test_is_shown_on_right_click(
        self, marker_tlui, tluis, user_actions, tilia_state
    ):
        with patch.object(MarkerTimelineUIContextMenu, "exec") as mock:
            click_timeline_ui(marker_tlui, 50, button="right")

        mock.assert_called_once()

    def test_has_no_height_set_action(
        self, marker_tlui, tluis, user_actions, tilia_state
    ):
        context_menu = marker_tlui.CONTEXT_MENU_CLASS(marker_tlui)

        assert get_qaction("timeline_height_set") not in context_menu.actions()

    def test_has_no_move_down_action_when_last(self, tluis, user_actions):
        with Serve(Get.FROM_USER_STRING, (True, "")):
            user_actions.trigger("timelines_add_marker_timeline")
            user_actions.trigger("timelines_add_marker_timeline")

        context_menu = tluis[1].CONTEXT_MENU_CLASS(tluis[1])

        action_names = [a.text().replace("&", "") for a in context_menu.actions()]
        assert "Move up" in action_names
        assert "Move down" not in action_names

    def test_has_no_move_up_action_when_first(self, tluis, user_actions):
        with Serve(Get.FROM_USER_STRING, (True, "")):
            user_actions.trigger("timelines_add_marker_timeline")
            user_actions.trigger("timelines_add_marker_timeline")

        context_menu = tluis[0].CONTEXT_MENU_CLASS(tluis[0])

        action_names = [a.text().replace("&", "") for a in context_menu.actions()]
        assert "Move up" not in action_names
        assert "Move down" in action_names

    @pytest.mark.xfail(
        reason="Waiting for refactor of timeline clear and delete actions."
    )
    def test_has_the_right_actions(self, marker_tlui, tluis, user_actions, tilia_state):
        context_menu = marker_tlui.CONTEXT_MENU_CLASS(marker_tlui)

        expected = ("timeline_delete", "timeline_clear")

        for action in expected:
            assert get_qaction(action) in context_menu.actions()


class TestInspect:
    def test_open_inspect_menu(self, marker_tlui, tluis, user_actions, qtui):
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])
        press_key("Enter")

        assert qtui.is_window_open(WindowKind.INSPECT)

    def test_close_inspect_menu_with_enter(
        self, marker_tlui, tluis, user_actions, qtui
    ):
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])
        press_key("Enter")
        press_key("Enter")

        assert not qtui.is_window_open(WindowKind.INSPECT)

    def test_close_inspect_menu_with_escape(
        self, marker_tlui, tluis, user_actions, qtui
    ):
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])
        press_key("Enter")
        press_key("Escape")

        assert not qtui.is_window_open(WindowKind.INSPECT)

    def test_set_label(self, qtui, marker_tlui, tluis, user_actions):
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])

        press_key("Enter")
        with undoable():
            type_string("hello tilia")
            assert marker_tlui[0].get_data("label") == "hello tilia"

    def test_set_label_to_empty_string(self, marker_tlui, tluis, user_actions):
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])

        press_key("Enter")
        type_string("hello tilia")
        press_key("Escape")
        press_key("Enter")
        with undoable():
            press_key("Backspace")
            assert marker_tlui[0].get_data("label") == ""

    def test_set_comments(self, marker_tlui, tluis, user_actions):
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])

        press_key("Enter")
        press_key("Tab")
        with undoable():
            type_string("some comments")
            assert marker_tlui[0].get_data("comments") == "some comments"

    def test_set_comments_to_empty_string(self, marker_tlui, tluis, user_actions):
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])

        press_key("Enter")
        press_key("Tab")
        type_string("some comments")
        press_key("Escape")
        press_key("Enter")
        press_key("Tab")
        press_key("A", modifier=Qt.KeyboardModifier.ControlModifier)
        with undoable():
            press_key("Backspace")

        assert marker_tlui[0].get_data("comments") == ""

    def test_set_attribute_with_multiple_selected(
        self, marker_tlui, tluis, user_actions, tilia_state
    ):
        user_actions.trigger("marker_add")
        tilia_state.current_time = 10
        user_actions.trigger("marker_add")

        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="ctrl")

        assert marker_tlui[0].is_selected()
        assert marker_tlui[1].is_selected()

        press_key("Enter")
        type_string("new label")
        assert marker_tlui[0].get_data("label") == ""
        assert marker_tlui[1].get_data("label") == "new label"


class TestSetTimelineName:
    def test_set(self, user_actions, tluis):
        with Serve(Get.FROM_USER_STRING, (True, "initial name")):
            user_actions.trigger("timelines_add_marker_timeline")

        with undoable():
            with patch.object(QInputDialog, "getText", return_value=("new name", True)):
                user_actions.trigger("timeline_name_set")

        assert tluis[0].get_data("name") == "new name"

    def test_set_to_empty_string(self, tluis, user_actions):
        with Serve(Get.FROM_USER_STRING, (True, "initial name")):
            user_actions.trigger("timelines_add_marker_timeline")

        with undoable():
            with patch.object(QInputDialog, "getText", return_value=("", True)):
                user_actions.trigger("timeline_name_set")

        assert tluis[0].get_data("name") == ""


class TestToolbar:
    def test_is_created_when_timeline_is_created(self, tluis, qtui, marker_tlui):
        assert get_toolbars_of_class(qtui, MarkerTimelineToolbar)

    def test_right_actions_are_shown(self, tluis, qtui, marker_tlui):
        expected_actions = [
            "marker_add",
        ]
        toolbar = get_toolbars_of_class(qtui, MarkerTimelineToolbar)[0]
        for action in expected_actions:
            assert get_qaction(action) in toolbar.actions()


class TestMoveInTimelineOrder:
    def test_move_up(self, tluis, user_actions):
        for name in ["1", "2", "3"]:
            with Serve(Get.FROM_USER_STRING, (True, name)):
                user_actions.trigger("timelines_add_marker_timeline")

        context_menu = tluis[1].CONTEXT_MENU_CLASS(tluis[1])
        action = get_action(context_menu, "Move up")
        assert action
        with undoable():
            action.trigger()
        assert [tlui.get_data("name") for tlui in tluis.get_timeline_uis()] == [
            "2",
            "1",
            "3",
        ]

    def test_move_down(self, tluis, user_actions):
        for name in ["1", "2", "3"]:
            with Serve(Get.FROM_USER_STRING, (True, name)):
                user_actions.trigger("timelines_add_marker_timeline")

        context_menu = tluis[1].CONTEXT_MENU_CLASS(tluis[1])
        action = get_action(context_menu, "Move down")
        assert action
        with undoable():
            action.trigger()
        assert [tlui.get_data("name") for tlui in tluis.get_timeline_uis()] == [
            "1",
            "3",
            "2",
        ]


def test_timeline_menu_has_right_actions(
    tluis, qtui, marker_tlui, tilia_state, user_actions
):
    expected_actions = ["import_csv_marker_timeline"]
    menu = get_main_window_menu(qtui, "Timelines")
    marker_submenu = get_submenu(menu, "Marker")
    assert marker_submenu

    for a in expected_actions:
        assert get_qaction(a) in marker_submenu.actions()


@pytest.mark.xfail(reason="Waiting for refactor of timeline clear actions.")
def test_clear(tluis, qtui, marker_tlui, tilia_state, user_actions):
    # TODO
    # needs refactoring of timeline clear actions
    # we want to be able to do post(Post.TIMELINE_CLEAR, marker_tlui)
    for i in range(10):
        tilia_state.current_time = i
        user_actions.trigger("marker_add")

    post(Post.TIMELINE_DELETE, marker_tlui)
    assert len(marker_tlui) == 0


@pytest.mark.xfail(reason="Waiting for refactor of timeline delete actions.")
def test_delete(tluis, qtui, marker_tlui, tilia_state, user_actions):
    # TODO
    # needs refactoring of timeline delete actions
    # we want to be able to do post(Post.TIMELINE_DELETE, marker_tlui)
    user_actions.trigger("timeline_delete", marker_tlui)

    assert tluis.is_empty
