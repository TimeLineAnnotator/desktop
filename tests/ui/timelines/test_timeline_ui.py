import pytest

from tests.mock import Serve
from tests.ui.timelines.interact import click_timeline_ui
from tilia.requests import Post, post, Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.actions import TiliaAction


class TestControlSelect:
    # ideally we would test this on every kind of element
    # but I didn't find an abstract way to click on all of them

    def test_single(self, marker_ui):
        for i in range(10):  # nothing special about 10, just clicking a few times
            click_timeline_ui(
                marker_ui.timeline_ui, marker_ui.get_data("time"), modifier="control"
            )
            if i % 2 == 0:
                assert marker_ui.is_selected()
            else:
                assert not marker_ui.is_selected()

    def test_multiple(self, marker_tlui):
        marker_tlui.create_marker(0)
        marker_tlui.create_marker(10)

        click_timeline_ui(marker_tlui, 0, modifier="control")
        assert marker_tlui[0].is_selected()
        assert not marker_tlui[1].is_selected()

        click_timeline_ui(marker_tlui, 10, modifier="control")
        assert marker_tlui[0].is_selected()
        assert marker_tlui[1].is_selected()

        click_timeline_ui(marker_tlui, 0, modifier="control")
        assert not marker_tlui[0].is_selected()
        assert marker_tlui[1].is_selected()

        click_timeline_ui(marker_tlui, 10, modifier="control")
        assert not marker_tlui[0].is_selected()
        assert not marker_tlui[1].is_selected()

    def test_does_not_deselect_if_nothing_clicked(self, marker_tlui):
        marker_tlui.create_marker(0)

        click_timeline_ui(marker_tlui, 0, modifier="control")
        click_timeline_ui(marker_tlui, 50, modifier="control")
        assert marker_tlui[0].is_selected()


@pytest.mark.parametrize(
    "tlui,component_kind",
    [
        ("harmony", ComponentKind.HARMONY),
        ("harmony", ComponentKind.MODE),
        ("marker", ComponentKind.MARKER),
        ("beat", ComponentKind.BEAT),
        # ("hierarchy", ComponentKind.HIERARCHY),
        # ("audiowave",ComponentKind.AUDIOWAVE)
    ],
    indirect=["tlui"],
)
class TestArrowSelection:
    def test_clicking_right_arrow_selects_next_element(self, tlui, component_kind):
        tlui.create_component(component_kind, 0)
        tlui.create_component(component_kind, 10)
        tlui.select_element(tlui[0])

        post(Post.TIMELINE_KEY_PRESS_RIGHT)

        assert not tlui[0].is_selected()
        assert tlui[1].is_selected()

    def test_clicking_right_arrow_with_multiple_selected_selects_next_element(
        self, tlui, component_kind
    ):
        tlui.create_component(component_kind, 0)
        tlui.create_component(component_kind, 10)
        tlui.create_component(component_kind, 20)
        tlui.create_component(component_kind, 30)
        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.select_element(tlui[2])

        post(Post.TIMELINE_KEY_PRESS_RIGHT)

        assert not tlui[0].is_selected()
        assert not tlui[1].is_selected()
        assert not tlui[2].is_selected()
        assert tlui[3].is_selected()

    def test_clicking_right_arrow_does_nothing_if_last_element_is_selected(
        self, tlui, component_kind
    ):
        tlui.create_component(component_kind, 0)
        tlui.create_component(component_kind, 10)
        tlui.select_element(tlui[1])

        post(Post.TIMELINE_KEY_PRESS_RIGHT)

        assert not tlui[0].is_selected()
        assert tlui[1].is_selected()

    def test_clicking_left_arrow_selects_previous_element(self, tlui, component_kind):
        tlui.create_component(component_kind, 0)
        tlui.create_component(component_kind, 10)
        tlui.select_element(tlui[1])

        post(Post.TIMELINE_KEY_PRESS_LEFT)

        assert tlui[0].is_selected()
        assert not tlui[1].is_selected()

    def test_clicking_left_arrow_with_multiple_selected_selects_previous_element(
        self, tlui, component_kind
    ):
        tlui.create_component(component_kind, 0)
        tlui.create_component(component_kind, 10)
        tlui.create_component(component_kind, 20)
        tlui.create_component(component_kind, 30)
        tlui.select_element(tlui[1])
        tlui.select_element(tlui[2])
        tlui.select_element(tlui[3])

        post(Post.TIMELINE_KEY_PRESS_LEFT)

        assert tlui[0].is_selected()
        assert not tlui[1].is_selected()
        assert not tlui[2].is_selected()
        assert not tlui[3].is_selected()

    def test_clicking_left_arrow_does_nothing_if_first_element_is_selected(
        self, tlui, component_kind
    ):
        tlui.create_component(component_kind, 0)
        tlui.create_component(component_kind, 10)
        tlui.select_element(tlui[0])

        post(Post.TIMELINE_KEY_PRESS_LEFT)

        assert tlui[0].is_selected()
        assert not tlui[1].is_selected()


class TestSetTimelineName:
    def test_set(self, tls, tluis, user_actions):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name="change me")
        with Serve(Get.FROM_USER_STRING, (True, "this")):
            user_actions.trigger(TiliaAction.TIMELINE_NAME_SET)

        assert tls[0].get_data("name") == "this"
        assert tluis[0].displayed_name == "this"

    def test_set_undo(self, tls, tluis, user_actions):
        with Serve(Get.FROM_USER_STRING, (True, "pure")):
            user_actions.trigger(TiliaAction.TIMELINES_ADD_MARKER_TIMELINE)
        with Serve(Get.FROM_USER_STRING, (True, "tainted")):
            user_actions.trigger(TiliaAction.TIMELINE_NAME_SET)

        user_actions.trigger(TiliaAction.EDIT_UNDO)

        assert tls[0].get_data("name") == "pure"
        assert tluis[0].displayed_name == "pure"

    def test_set_redo(self, tls, tluis, user_actions):
        with Serve(Get.FROM_USER_STRING, (True, "pure")):
            user_actions.trigger(TiliaAction.TIMELINES_ADD_MARKER_TIMELINE)
        with Serve(Get.FROM_USER_STRING, (True, "tainted")):
            user_actions.trigger(TiliaAction.TIMELINE_NAME_SET)

        user_actions.trigger(TiliaAction.EDIT_UNDO)
        user_actions.trigger(TiliaAction.EDIT_REDO)

        assert tls[0].get_data("name") == "tainted"
        assert tluis[0].displayed_name == "tainted"

    def test_set_empty_string(self, tls, tluis, user_actions):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name="change me")
        with Serve(Get.FROM_USER_STRING, (True, "")):
            user_actions.trigger(TiliaAction.TIMELINE_NAME_SET)

        assert tls[0].get_data("name") == ""
        assert tluis[0].displayed_name == ""
