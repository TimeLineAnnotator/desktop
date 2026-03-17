from typing import Literal

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from tests.mock import Serve
from tilia.requests import Get, get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.collection.collection import Timelines
from tilia.ui import commands
from tilia.ui.windows.manage_timelines import ManageTimelines


def assert_order_is_correct(tls: Timelines, expected: list[Timeline]):
    # assert timeline order
    for tl, expected in zip(sorted(tls), expected):
        assert tl == expected

    # assert list widget order
    for i, tl in enumerate(expected):
        tlui = get(Get.TIMELINE_UI, tl.id)
        assert ManageTimelines().list_widget.item(i).timeline_ui == tlui


class TestChangeTimelineVisibility:
    @staticmethod
    def toggle_timeline_is_visible(row: int = 0):
        """Toggles timeline visibility using the Manage Timelines window."""
        mt = ManageTimelines()
        mt.list_widget.setCurrentRow(row)
        QTest.mouseClick(mt.checkbox, Qt.MouseButton.LeftButton)
        mt.close()

    def test_hide(self, marker_tlui):
        commands.execute("timeline.set_is_visible", marker_tlui, True)
        self.toggle_timeline_is_visible()
        assert not marker_tlui.get_data("is_visible")

    def test_show(self, marker_tlui):
        commands.execute("timeline.set_is_visible", marker_tlui, False)
        self.toggle_timeline_is_visible()
        assert marker_tlui.get_data("is_visible")

    def test_toggle_visibility_multiple_times(self, marker_tlui):
        commands.execute("timeline.set_is_visible", marker_tlui, True)
        for i in range(10):
            self.toggle_timeline_is_visible()
            if i % 2 == 1:
                assert marker_tlui.get_data("is_visible")
            else:
                assert not marker_tlui.get_data("is_visible")


class TestChangeTimelineOrder:
    @pytest.fixture(autouse=True)
    def setup_timelines(self, tluis, tls):
        with Serve(Get.FROM_USER_STRING, (True, "")):
            commands.execute("timelines.add.marker")
            commands.execute("timelines.add.marker")
            commands.execute("timelines.add.marker")
        return list(tls)

    @staticmethod
    def click_set_ordinal_button(button: Literal["up", "down"], row: int):
        """Toggles timeline visibility using the ManageTimelines window."""
        mt = ManageTimelines()
        mt.list_widget.setCurrentRow(row)
        if button == "up":
            button = mt.up_button
        elif button == "down":
            button = mt.down_button
        else:
            assert False, "Invalid button value."

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        mt.close()

    def test_increase_ordinal(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("up", 1)

        assert_order_is_correct(tls, [tl1, tl0, tl2])

    def test_increase_ordinal_undo(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("up", 1)
        commands.execute("edit.undo")

        assert_order_is_correct(tls, [tl0, tl1, tl2])

    def test_increase_ordinal_redo(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("up", 1)
        commands.execute("edit.undo")
        commands.execute("edit.redo")

        assert_order_is_correct(tls, [tl1, tl0, tl2])

    def test_increase_ordinal_with_first_selected_does_nothing(
        self, tls, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("up", 0)

        assert_order_is_correct(tls, [tl0, tl1, tl2])

    def test_decrease_ordinal(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("down", 0)

        assert_order_is_correct(tls, [tl1, tl0, tl2])

    def test_decrease_ordinal_undo(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("down", 0)
        commands.execute("edit.undo")

        assert_order_is_correct(tls, [tl0, tl1, tl2])

    def test_decrease_ordinal_redo(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("down", 0)
        commands.execute("edit.undo")
        commands.execute("edit.redo")

        assert_order_is_correct(tls, [tl1, tl0, tl2])

    def test_decrease_ordinal_with_last_selected_does_nothing(
        self, tls, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("down", 2)

        assert_order_is_correct(tls, [tl0, tl1, tl2])
