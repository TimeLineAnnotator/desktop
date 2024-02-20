import pytest

from tests.mock import Serve
from tilia.requests import post, Post, Get, get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.collection.collection import Timelines
from tilia.timelines.timeline_kinds import TimelineKind
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
def manage_timelines():
    mt = ManageTimelines()
    yield mt
    mt.close()


def create_timeline(tls: Timelines, kind: TimelineKind, name: str = ""):
    kind_to_request = {
        TimelineKind.MARKER_TIMELINE: Post.TIMELINE_ADD_MARKER_TIMELINE,
        TimelineKind.HIERARCHY_TIMELINE: Post.TIMELINE_ADD_HIERARCHY_TIMELINE,
        TimelineKind.HARMONY_TIMELINE: Post.TIMELINE_ADD_HARMONY_TIMELINE,
        TimelineKind.BEAT_TIMELINE: Post.TIMELINE_ADD_BEAT_TIMELINE,
    }
    with Serve(Get.FROM_USER_STRING, (name, True)):
        post(kind_to_request[kind])

    return tls[-1]


class TestChangeTimelineOrder:
    def test_increase_ordinal(self, tls, manage_timelines):
        tl0 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)
        tl1 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)
        tl2 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)

        manage_timelines.list_widget.setCurrentRow(1)
        manage_timelines.up_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_increase_ordinal_undo(self, tls, actions, manage_timelines):
        tl0 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="first")
        tl1 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="second")
        tl2 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="third")

        manage_timelines.list_widget.setCurrentRow(1)
        manage_timelines.up_button.click()

        actions.trigger(TiliaAction.EDIT_UNDO)

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])

    def test_increase_ordinal_redo(self, tls, actions, manage_timelines):
        tl0 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="first")
        tl1 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="second")
        tl2 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="third")

        manage_timelines.list_widget.setCurrentRow(1)
        manage_timelines.up_button.click()

        actions.trigger(TiliaAction.EDIT_UNDO)
        actions.trigger(TiliaAction.EDIT_REDO)

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_increase_ordinal_with_first_selected_does_nothing(
        self, tls, manage_timelines
    ):
        tl0 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)
        tl1 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)
        tl2 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)

        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.up_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])

    def test_decrease_ordinal(self, tls, manage_timelines):
        tl0 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)
        tl1 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)
        tl2 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)

        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.down_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_decrease_ordinal_undo(self, tls, actions, manage_timelines):
        tl0 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="first")
        tl1 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="second")
        tl2 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="third")

        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.down_button.click()

        actions.trigger(TiliaAction.EDIT_UNDO)

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])

    def test_decrease_ordinal_redo(self, tls, actions, manage_timelines):
        tl0 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="first")
        tl1 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="second")
        tl2 = create_timeline(tls, TimelineKind.MARKER_TIMELINE, name="third")

        manage_timelines.list_widget.setCurrentRow(0)
        manage_timelines.down_button.click()

        actions.trigger(TiliaAction.EDIT_UNDO)
        actions.trigger(TiliaAction.EDIT_REDO)

        assert_order_is_correct(tls, manage_timelines, [tl1, tl0, tl2])

    def test_decrease_ordinal_with_last_selected_does_nothing(
        self, tls, manage_timelines
    ):
        tl0 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)
        tl1 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)
        tl2 = create_timeline(tls, TimelineKind.MARKER_TIMELINE)

        manage_timelines.list_widget.setCurrentRow(2)
        manage_timelines.down_button.click()

        assert_order_is_correct(tls, manage_timelines, [tl0, tl1, tl2])
