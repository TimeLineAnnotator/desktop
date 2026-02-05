import pytest

from tests.mock import Serve
from tilia.requests import Get, get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.collection.collection import Timelines
from tilia.ui import commands
from tilia.ui.windows.manage_timelines import ManageTimelines


def assert_timeline_order(tls: Timelines, expected: list[Timeline]):
    for tl, expected in zip(sorted(tls), expected):
        assert tl == expected


def assert_list_widget_order(window: ManageTimelines, expected: list[Timeline]):
    for i, tl in enumerate(expected):
        tlui = get(Get.TIMELINE_UI, tl.id)
        assert window.list_widget.item(i).timeline_ui == tlui


def assert_order_is_correct(
    tls: Timelines, window: ManageTimelines, expected: list[Timeline]
):
    assert_timeline_order(tls, expected)
    assert_list_widget_order(window, expected)


@pytest.fixture
def manage_timelines(qtui):
    mt = ManageTimelines()
    yield mt
    mt.close()


class TestChangeTimelineVisibility:
    def set_is_visible(self, manage_timelines, row: int, is_visible: bool):
        manage_timelines.list_widget.setCurrentRow(row)
        manage_timelines.checkbox.setChecked(is_visible)

    def test_hide(self, marker_tl, manage_timelines):
        marker_tl.set_data("is_visible", True)
        self.set_is_visible(manage_timelines, 0, False)
        assert marker_tl.get_data("is_visible") is False

    def test_show(self, marker_tl, manage_timelines):
        marker_tl.set_data("is_visible", False)
        self.set_is_visible(manage_timelines, 0, True)
        assert marker_tl.get_data("is_visible") is True

    def test_hide_then_show(self, marker_tl, manage_timelines):
        marker_tl.set_data("is_visible", True)
        self.set_is_visible(manage_timelines, 0, False)
        self.set_is_visible(manage_timelines, 0, True)
        assert marker_tl.get_data("is_visible") is True

    def test_show_then_hide(self, marker_tl, manage_timelines):
        marker_tl.set_data("is_visible", False)
        self.set_is_visible(manage_timelines, 0, True)
        self.set_is_visible(manage_timelines, 0, False)
        assert marker_tl.get_data("is_visible") is False


class TestChangeTimelineOrder:
    @pytest.fixture(autouse=True)
    def setup_timelines(self, tls):
        with Serve(Get.FROM_USER_STRING, (True, "")):
            commands.execute("timelines.add.marker")
            commands.execute("timelines.add.marker")
            commands.execute("timelines.add.marker")
        return list(tls)

    def test_increase_ordinal(self, tls, manage_timelines, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        manage_timelines.list_widget.setCurrentRow(1)
        manage_timelines.up_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_increase_ordinal_undo(self, tls, manage_timelines, setup_timelines):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(1)
        manage_timelines.up_button.click()

        commands.execute("edit.undo")

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])

    def test_increase_ordinal_redo(self, tls, manage_timelines, setup_timelines):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(1)
        manage_timelines.up_button.click()

        commands.execute("edit.undo")
        commands.execute("edit.redo")

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_increase_ordinal_with_first_selected_does_nothing(
        self, tls, manage_timelines, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.up_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])

    def test_decrease_ordinal(self, tls, manage_timelines, setup_timelines):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.down_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_decrease_ordinal_undo(self, tls, manage_timelines, setup_timelines):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.down_button.click()

        commands.execute("edit.undo")

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])

    def test_decrease_ordinal_redo(self, tls, manage_timelines, setup_timelines):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.down_button.click()

        commands.execute("edit.undo")
        commands.execute("edit.redo")

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_decrease_ordinal_with_last_selected_does_nothing(
        self, tls, manage_timelines, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(2)
        manage_timelines.down_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])
