import pytest

from tests.mock import Serve
from tilia.requests import Post, post, Get, get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.actions import TiliaAction


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
    def test_set(self, tls, actions):
        tl = tls.add_timeline_with_post(TimelineKind.MARKER_TIMELINE, name="change me")
        tlui = get(Get.TIMELINE_UI, tl.id)
        with Serve(Get.FROM_USER_STRING, ("this", True)):
            actions.trigger(TiliaAction.TIMELINE_NAME_SET)

        assert tl.get_data("name") == "this"
        assert tlui.displayed_name == "this"

    def test_set_undo(self, tls, actions):
        tl = tls.add_timeline_with_post(TimelineKind.MARKER_TIMELINE, name="pure")
        tlui = get(Get.TIMELINE_UI, tl.id)
        with Serve(Get.FROM_USER_STRING, ("tainted", True)):
            actions.trigger(TiliaAction.TIMELINE_NAME_SET)

        actions.trigger(TiliaAction.EDIT_UNDO)

        assert tl.get_data("name") == "pure"
        assert tlui.displayed_name == "pure"

    def test_set_redo(self, tls, actions):
        tl = tls.add_timeline_with_post(TimelineKind.MARKER_TIMELINE, name="pure")
        tlui = get(Get.TIMELINE_UI, tl.id)
        with Serve(Get.FROM_USER_STRING, ("tainted", True)):
            actions.trigger(TiliaAction.TIMELINE_NAME_SET)

        actions.trigger(TiliaAction.EDIT_UNDO)
        actions.trigger(TiliaAction.EDIT_REDO)

        assert tl.get_data("name") == "tainted"
        assert tlui.displayed_name == "tainted"

    def test_set_empty_string(self, tls, actions):
        tl = tls.add_timeline_with_post(TimelineKind.MARKER_TIMELINE, name="change me")
        tlui = get(Get.TIMELINE_UI, tl.id)
        with Serve(Get.FROM_USER_STRING, ("", True)):
            actions.trigger(TiliaAction.TIMELINE_NAME_SET)

        assert tl.get_data("name") == ""
        assert tlui.displayed_name == ""
