from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QInputDialog

from tests.mock import Serve, patch_ask_for_string_dialog, patch_yes_or_no_dialog
from tests.ui.test_qtui import get_toolbars_of_class
from tests.ui.timelines.interact import (
    click_timeline_ui,
    drag_mouse_in_timeline_view,
    press_key,
    type_string,
)
from tests.ui.timelines.marker.interact import click_marker_ui, get_marker_ui_center
from tests.utils import (
    undoable,
    get_command_action,
    get_submenu,
    get_main_window_menu,
    get_command_names,
)
from tilia.requests import Post, Get, post
from tilia.ui import commands
from tilia.ui.commands import get_qaction
from tilia.ui.coords import time_x_converter

from tilia.ui.timelines.marker import MarkerTimelineToolbar
from tilia.ui.timelines.marker.context_menu import (
    MarkerContextMenu,
    MarkerTimelineUIContextMenu,
)
from tilia.ui.windows import WindowKind


class TestCreateDelete:
    def test_create(self, marker_tlui, tluis, tilia_state):
        tilia_state.current_time = 11
        commands.execute("timeline.marker.add")

        assert len(marker_tlui) == 1
        assert marker_tlui[0].get_data("time") == 11

    def test_create_at_same_time_fails(self, marker_tlui):
        commands.execute("timeline.marker.add")
        commands.execute("timeline.marker.add")

        assert len(marker_tlui) == 1

    def test_delete(self, marker_tlui):
        commands.execute("timeline.marker.add")
        click_marker_ui(marker_tlui[0])

        with undoable():
            commands.execute("timeline.component.delete")
            assert len(marker_tlui) == 0

    def test_delete_multiple(self, marker_tlui, tilia_state):
        commands.execute("timeline.marker.add")
        tilia_state.current_time = 10
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="ctrl")

        with undoable():
            commands.execute("timeline.component.delete")
            assert len(marker_tlui) == 0


class TestSetResetColor:
    TEST_COLOR = "#000000"

    def set_color_on_all_markers(self, marker_tlui):
        """Assumes there is a single marker on timeline"""
        marker_tlui.select_all_elements()
        with Serve(Get.FROM_USER_COLOR, (True, QColor(self.TEST_COLOR))):
            commands.execute("timeline.component.set_color")

    def test_set_color(self, marker_tlui):
        commands.execute("timeline.marker.add")
        with undoable():
            self.set_color_on_all_markers(marker_tlui)
            assert marker_tlui[0].get_data("color") == self.TEST_COLOR

    def test_set_color_multiple_markers(self, marker_tlui, tilia_state):
        commands.execute("timeline.marker.add")
        tilia_state.current_time = 10
        commands.execute("timeline.marker.add")
        with undoable():
            self.set_color_on_all_markers(marker_tlui)
            for marker in marker_tlui:
                assert marker.get_data("color") == self.TEST_COLOR

    def test_reset_color(self, marker_tlui):
        commands.execute("timeline.marker.add")
        self.set_color_on_all_markers(marker_tlui)

        with undoable():
            commands.execute("timeline.component.reset_color")
            assert marker_tlui[0].get_data("color") is None

    def test_reset_color_multiple_markers(self, marker_tlui, tilia_state):
        commands.execute("timeline.marker.add")
        tilia_state.current_time = 10
        commands.execute("timeline.marker.add")
        self.set_color_on_all_markers(marker_tlui)

        with undoable():
            commands.execute("timeline.component.reset_color")
            for marker in marker_tlui:
                assert marker.get_data("color") is None

    def test_cancel_color_dialog(self, marker_tlui, tilia_state):
        commands.execute("timeline.marker.add")
        click_marker_ui(marker_tlui[0])
        with patch.object(QColorDialog, "getColor", return_value=QColor("invalid")):
            commands.execute("timeline.component.set_color")

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

    def test_paste_single_into_timeline(self, marker_tlui, tilia_state):
        marker_tlui.create_marker(0, label="copy me")
        # Must record explicitly, as there is no command to set a component's label
        post(Post.APP_STATE_RECORD, "set marker label")

        click_marker_ui(marker_tlui[0])
        commands.execute("timeline.component.copy")

        tilia_state.current_time = 10
        click_timeline_ui(marker_tlui, 50)

        with undoable():
            commands.execute("timeline.component.paste")

        assert len(marker_tlui) == 2
        assert marker_tlui[1].get_data("time") == 10
        assert marker_tlui[1].get_data("label") == "copy me"

    def test_paste_single_into_selected_element(self, marker_tlui, tilia_state):
        commands.execute("timeline.marker.add")
        tilia_state.current_time = 10
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])
        press_key("Enter")
        type_string("copy me")
        commands.execute("timeline.component.copy")
        click_marker_ui(marker_tlui[1])

        with undoable():
            commands.execute("timeline.component.paste")

            assert len(marker_tlui) == 2
            assert marker_tlui[1].get_data("label") == "copy me"

    def test_paste_multiple_into_timeline(self, marker_tlui, tilia_state):
        for time, label in [(0, "first"), (10, "second"), (20, "third")]:
            tilia_state.current_time = time
            commands.execute("timeline.marker.add")
            click_marker_ui(marker_tlui[-1])
            commands.execute("timeline.element.inspect")
            type_string(label)

        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="ctrl")
        click_marker_ui(marker_tlui[2], modifier="ctrl")
        commands.execute("timeline.component.copy")

        click_timeline_ui(marker_tlui, 100)  # deselect markers
        tilia_state.current_time = 50

        with undoable():
            commands.execute("timeline.component.paste")

        assert len(marker_tlui) == 6
        for index, time, label in [
            (3, 50, "first"),
            [4, 60, "second"],
            [5, 70, "third"],
        ]:
            assert marker_tlui[index].get_data("time") == time
            assert marker_tlui[index].get_data("label") == label

    def test_paste_multiple_into_selected_element(self, marker_tlui, tilia_state):
        for time, label in [(0, "first"), (10, "second"), (20, "third")]:
            tilia_state.current_time = time
            commands.execute("timeline.marker.add")
            click_marker_ui(marker_tlui[-1])
            commands.execute("timeline.element.inspect")
            type_string(label)

        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="ctrl")
        click_marker_ui(marker_tlui[2], modifier="ctrl")
        commands.execute("timeline.component.copy")

        click_marker_ui(marker_tlui[2])

        with undoable():
            commands.execute("timeline.component.paste")

        assert len(marker_tlui) == 5
        for index, time, label in [
            (2, 20, "first"),
            [3, 30, "second"],
            [4, 40, "third"],
        ]:
            assert marker_tlui[index].get_data("time") == time
            assert marker_tlui[index].get_data("label") == label


class TestSelect:
    def test_select(self, marker_tlui, tluis):
        marker_tlui.create_marker(10)
        click_marker_ui(marker_tlui[0])

        assert marker_tlui[0] in marker_tlui.selected_elements

    def test_deselect(self, marker_tlui, tluis):
        marker_tlui.create_marker(10)
        click_marker_ui(marker_tlui[0])
        click_timeline_ui(marker_tlui, 0)

        assert len(marker_tlui.selected_elements) == 0

    def test_box_selection(self, marker_tlui, tluis):
        marker_tlui.create_marker(10)
        marker_tlui.create_marker(20)
        marker_tlui.create_marker(30)

        click_timeline_ui(marker_tlui, 5, button="left")

        drag_mouse_in_timeline_view(*get_marker_ui_center(marker_tlui[1]))

        assert len(marker_tlui.selected_elements) == 2
        assert marker_tlui[0] in marker_tlui.selected_elements
        assert marker_tlui[1] in marker_tlui.selected_elements

    def test_box_deselection(self, marker_tlui, tluis):
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
    def test_drag(self, marker_tlui, tluis, tilia_state):
        tilia_state.duration = 100
        tilia_state.current_time = 10
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])

        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(20), 0)
            assert marker_tlui[0].get_data("time") == 20

    def test_drag_beyond_start(self, marker_tlui, tluis, tilia_state):
        tilia_state.duration = 100
        tilia_state.current_time = 10
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])

        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(0) - 200, 0)
            assert marker_tlui[0].get_data("time") == 0

    def test_drag_beyond_end(self, marker_tlui, tluis, tilia_state):
        tilia_state.duration = 100
        tilia_state.current_time = 10
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])

        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(100) + 200, 0)
            assert marker_tlui[0].get_data("time") == 100


class TestElementContextMenu:
    def test_is_shown_on_right_click(self, marker_tlui, tluis, tilia_state):
        marker_tlui.create_marker(0)

        with patch.object(MarkerContextMenu, "exec") as mock:
            click_marker_ui(marker_tlui[0], button="right")

        mock.assert_called_once()

    def test_has_the_right_options(self, marker_tlui, tluis, tilia_state):
        marker_tlui.create_marker(0)

        context_menu = marker_tlui[0].CONTEXT_MENU_CLASS((marker_tlui[0]))

        expected = (
            "timeline.element.inspect",
            "timeline.component.delete",
            "timeline.component.reset_color",
            "timeline.component.set_color",
            "timeline.component.copy",
            "timeline.component.paste",
        )

        for command in expected:
            assert get_qaction(command) in context_menu.actions()


class TestTimelineUIContextMenu:
    @staticmethod
    def get_context_menu(tluis, tl_index=0):
        return tluis[tl_index].CONTEXT_MENU_CLASS(tluis[tl_index])

    def test_is_shown_on_right_click(self, marker_tlui, tluis, tilia_state):
        with patch.object(MarkerTimelineUIContextMenu, "exec") as mock:
            click_timeline_ui(marker_tlui, 50, button="right")

        mock.assert_called_once()

    def test_has_no_height_set_action(self, marker_tlui, tluis, tilia_state):
        context_menu = self.get_context_menu(tluis)

        assert get_qaction("timeline.set_height") not in context_menu.actions()

    def test_has_no_move_down_action_when_last(self, tluis):
        with Serve(Get.FROM_USER_STRING, (True, "")):
            commands.execute("timelines.add.marker")
            commands.execute("timelines.add.marker")

        context_menu = self.get_context_menu(tluis, 1)

        action_commands = get_command_names(context_menu)
        assert "timeline.move_up" in action_commands
        assert "timeline.move_down" not in action_commands

    def test_has_no_move_up_action_when_first(self, tluis):
        with Serve(Get.FROM_USER_STRING, (True, "")):
            commands.execute("timelines.add.marker")
            commands.execute("timelines.add.marker")

        context_menu = self.get_context_menu(tluis)

        action_commands = get_command_names(context_menu)
        assert "timeline.move_up" not in action_commands
        assert "timeline.move_down" in action_commands

    def test_has_the_right_actions(self, marker_tlui, tluis, tilia_state):
        context_menu = self.get_context_menu(tluis)

        # As each context menu creates its own QActions,
        # we can't get them with commands.get_action().
        # Instead, we see if their "text" property is as expected.
        expected = ("Delete", "Clear")

        for name in expected:
            assert name in [a.text() for a in context_menu.actions()]

    def test_set_name_via_context_menu(self, marker_tlui, tluis):
        context_menu = self.get_context_menu(tluis)
        marker_tlui.get_data("name")
        set_name_action = get_command_action(context_menu, "timeline.set_name")

        with patch_ask_for_string_dialog(True, "new name"):
            with undoable():
                set_name_action.trigger()
        assert marker_tlui.get_data("name") == "new name"

    def test_move_up_via_context_menu(self, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timelines.add.marker", name="Move me up")

        context_menu = self.get_context_menu(tluis, 1)
        move_up_action = get_command_action(context_menu, "timeline.move_up")
        with undoable():
            move_up_action.trigger()

        assert tluis[0].get_data("name") == "Move me up"

    def test_move_down_via_context_menu(self, tluis):
        commands.execute("timelines.add.marker", name="Move me down")
        commands.execute("timelines.add.marker", name="")

        context_menu = self.get_context_menu(tluis)
        move_down_action = get_command_action(context_menu, "timeline.move_down")

        with undoable():
            move_down_action.trigger()

        assert tluis[1].get_data("name") == "Move me down"

    def test_delete_via_context_menu(self, marker_tlui, tluis):
        context_menu = self.get_context_menu(tluis)
        delete_action = get_command_action(context_menu, "timeline.delete")
        with patch_yes_or_no_dialog(True):
            with undoable():
                delete_action.trigger()

        assert tluis.is_empty

    def test_clear_via_context_menu(self, marker_tlui, tluis):
        commands.execute("timeline.marker.add")
        commands.execute("timeline.marker.add", time=1)
        commands.execute("timeline.marker.add", time=2)
        # post(Post.APP_STATE_RECORD, "test setup")

        context_menu = self.get_context_menu(tluis)
        delete_action = get_command_action(context_menu, "timeline.clear")
        with patch_yes_or_no_dialog(True):
            with undoable():
                delete_action.trigger()

        assert marker_tlui.is_empty


class TestInspect:
    def test_open_inspect_menu(self, marker_tlui, tluis, qtui):
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])
        press_key("Enter")

        assert qtui.is_window_open(WindowKind.INSPECT)

    def test_close_inspect_menu_with_enter(self, marker_tlui, tluis, qtui):
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])
        press_key("Enter")
        press_key("Enter")

        assert not qtui.is_window_open(WindowKind.INSPECT)

    def test_close_inspect_menu_with_escape(self, marker_tlui, tluis, qtui):
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])
        press_key("Enter")
        press_key("Escape")

        assert not qtui.is_window_open(WindowKind.INSPECT)

    def test_set_label(self, qtui, marker_tlui, tluis):
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])

        press_key("Enter")
        with undoable():
            type_string("hello tilia")
            assert marker_tlui[0].get_data("label") == "hello tilia"

    def test_set_label_to_empty_string(self, marker_tlui, tluis):
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])

        press_key("Enter")
        type_string("hello tilia")
        press_key("Escape")
        press_key("Enter")
        with undoable():
            press_key("Backspace")
            assert marker_tlui[0].get_data("label") == ""

    def test_set_comments(self, marker_tlui, tluis):
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])

        press_key("Enter")
        press_key("Tab")
        with undoable():
            type_string("some comments")
            assert marker_tlui[0].get_data("comments") == "some comments"

    def test_set_comments_to_empty_string(self, marker_tlui, tluis):
        commands.execute("timeline.marker.add")

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
        self, marker_tlui, tluis, tilia_state
    ):
        commands.execute("timeline.marker.add")
        tilia_state.current_time = 10
        commands.execute("timeline.marker.add")

        click_marker_ui(marker_tlui[0])
        click_marker_ui(marker_tlui[1], modifier="ctrl")

        assert marker_tlui[0].is_selected()
        assert marker_tlui[1].is_selected()

        press_key("Enter")
        type_string("new label")
        assert marker_tlui[0].get_data("label") == ""
        assert marker_tlui[1].get_data("label") == "new label"


class TestSetTimelineName:
    def test_set(self, tluis):
        with Serve(Get.FROM_USER_STRING, (True, "initial name")):
            commands.execute("timelines.add.marker")

        with undoable():
            with patch.object(QInputDialog, "getText", return_value=("new name", True)):
                commands.execute("timeline.set_name", tluis[0])

        assert tluis[0].get_data("name") == "new name"

    def test_set_to_empty_string(self, tluis):
        with Serve(Get.FROM_USER_STRING, (True, "initial name")):
            commands.execute("timelines.add.marker")

        with undoable():
            with patch.object(QInputDialog, "getText", return_value=("", True)):
                commands.execute("timeline.set_name", tluis[0])

        assert tluis[0].get_data("name") == ""


class TestToolbar:
    def test_is_created_when_timeline_is_created(self, tluis, qtui, marker_tlui):
        assert get_toolbars_of_class(qtui, MarkerTimelineToolbar)

    def test_right_actions_are_shown(self, tluis, qtui, marker_tlui):
        expected_actions = [
            "timeline.marker.add",
        ]
        toolbar = get_toolbars_of_class(qtui, MarkerTimelineToolbar)[0]
        for command in expected_actions:
            assert get_qaction(command) in toolbar.actions()


class TestMoveInTimelineOrder:
    def test_move_up(self, tluis):
        for name in ["1", "2", "3"]:
            with Serve(Get.FROM_USER_STRING, (True, name)):
                commands.execute("timelines.add.marker")

        context_menu = tluis[1].CONTEXT_MENU_CLASS(tluis[1])
        action = get_command_action(context_menu, "timeline.move_up")
        with undoable():
            action.trigger()
        assert [tlui.get_data("name") for tlui in tluis.get_timeline_uis()] == [
            "2",
            "1",
            "3",
        ]

    def test_move_down(self, tluis):
        for name in ["1", "2", "3"]:
            with Serve(Get.FROM_USER_STRING, (True, name)):
                commands.execute("timelines.add.marker")

        context_menu = tluis[1].CONTEXT_MENU_CLASS(tluis[1])
        action = get_command_action(context_menu, "timeline.move_down")
        assert action
        with undoable():
            action.trigger()
        assert [tlui.get_data("name") for tlui in tluis.get_timeline_uis()] == [
            "1",
            "3",
            "2",
        ]


def test_timeline_menu_has_right_actions(tluis, qtui, marker_tlui, tilia_state):
    expected_actions = ["timelines.import.marker"]
    menu = get_main_window_menu(qtui, "Timelines")
    marker_submenu = get_submenu(menu, "Marker")
    assert marker_submenu

    for a in expected_actions:
        assert get_qaction(a) in marker_submenu.actions()


def test_clear(tluis, qtui, marker_tlui, tilia_state):
    for i in range(10):
        tilia_state.current_time = i
        commands.execute("timeline.marker.add")

    with Serve(Get.FROM_USER_YES_OR_NO, True):
        commands.execute("timeline.clear", marker_tlui)

    assert len(marker_tlui) == 0


def test_delete(tluis, qtui, marker_tlui, tilia_state):
    with Serve(Get.FROM_USER_YES_OR_NO, True):
        commands.execute("timeline.delete", marker_tlui)

    assert tluis.is_empty
