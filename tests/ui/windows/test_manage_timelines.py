import pytest

from tests.mock import Serve
from tilia.requests import Get, get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.collection.collection import Timelines
from tilia.ui.actions import TiliaAction
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


class TestChangeTimelineOrder:
    @pytest.fixture(autouse=True)
    def setup_timelines(self, tls, user_actions):
        with Serve(Get.FROM_USER_STRING, (True, "")):
            user_actions.trigger(TiliaAction.TIMELINES_ADD_MARKER_TIMELINE)
            user_actions.trigger(TiliaAction.TIMELINES_ADD_MARKER_TIMELINE)
            user_actions.trigger(TiliaAction.TIMELINES_ADD_MARKER_TIMELINE)
        return list(tls)

    def test_increase_ordinal(self, tls, manage_timelines, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        manage_timelines.list_widget.setCurrentRow(1)
        manage_timelines.up_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_increase_ordinal_undo(
        self, tls, user_actions, manage_timelines, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(1)
        manage_timelines.up_button.click()

        user_actions.trigger(TiliaAction.EDIT_UNDO)

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])

    def test_increase_ordinal_redo(
        self, tls, user_actions, manage_timelines, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(1)
        manage_timelines.up_button.click()

        user_actions.trigger(TiliaAction.EDIT_UNDO)
        user_actions.trigger(TiliaAction.EDIT_REDO)

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_increase_ordinal_with_first_selected_does_nothing(
        self, tls, user_actions, manage_timelines, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.up_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])

    def test_decrease_ordinal(
        self, tls, manage_timelines, user_actions, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.down_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_decrease_ordinal_undo(
        self, tls, user_actions, manage_timelines, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.down_button.click()

        user_actions.trigger(TiliaAction.EDIT_UNDO)

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])

    def test_decrease_ordinal_redo(
        self, tls, user_actions, manage_timelines, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.down_button.click()

        user_actions.trigger(TiliaAction.EDIT_UNDO)
        user_actions.trigger(TiliaAction.EDIT_REDO)

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_decrease_ordinal_with_last_selected_does_nothing(
        self, tls, manage_timelines, user_actions, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines
        manage_timelines.list_widget.setCurrentRow(2)
        manage_timelines.down_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])
