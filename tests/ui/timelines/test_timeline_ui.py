import pytest

from tests.mock import Serve
from tests.ui.timelines.interact import (
    click_timeline_ui_element_body,
    click_timeline_ui,
)
from tilia.requests import Post, post, Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.actions import TiliaAction


def get_time_shifted_args(args: dict[str, int], d_time) -> dict[str, int]:
    if "time" in args:
        args["time"] += d_time
    else:
        args["start"] += d_time
        args["end"] += d_time
    return args


@pytest.mark.parametrize(
    "tlui, args",
    [
        (
            "audiowave_tlui",
            {"kind": ComponentKind.AUDIOWAVE, "start": 50, "end": 55, "amplitude": 10},
        ),
        ("beat_tlui", {"kind": ComponentKind.BEAT, "time": 50}),
        ("harmony_tlui", {"kind": ComponentKind.HARMONY, "time": 50}),
        ("harmony_tlui", {"kind": ComponentKind.MODE, "time": 50}),
        (
            "hierarchy_tlui",
            {"kind": ComponentKind.HIERARCHY, "start": 50, "end": 55, "level": 2},
        ),
        ("marker_tlui", {"kind": ComponentKind.MARKER, "time": 50}),
        ("pdf_tlui", {"kind": ComponentKind.PDF_MARKER, "time": 50, "page_number": 1}),
        # "score_tlui", setup is a little too complicated
        # "slider_tlui", not clickable
    ],
)
class TestModifierSelect:
    @pytest.mark.parametrize(
        "modifiers,changes_time,select_value",
        [
            (["alt", "ctrl"], False, [True, False]),
            (["alt"], False, [True, True]),
            (["ctrl"], True, [True, False]),
        ],
        ids=["alt+ctrl", "alt", "ctrl"],
    )
    def test_single(
        self,
        qtui,
        tlui,
        args,
        tilia_state,
        request,
        modifiers,
        changes_time,
        select_value,
    ):
        tlui = request.getfixturevalue(tlui)
        tlui.create_component(**args)

        if "time" in args:
            click_time = tlui[0].get_data("time")
        else:
            click_time = tlui[0].get_data("start")

        for i in range(10):
            click_timeline_ui_element_body(tlui[0], modifier=modifiers)
            assert tlui[0].is_selected() == select_value[i % 2]
            assert tilia_state.current_time == (click_time if changes_time else 0)

    @pytest.mark.parametrize(
        "modifiers,changes_time,select_value",
        [
            (
                ["alt", "ctrl"],
                False,
                [(True, False), (True, True), (False, True), (False, False)],
            ),
            (
                ["alt"],
                False,
                [(True, False), (False, True), (True, False), (False, True)],
            ),
            (
                [
                    "ctrl",
                    True,
                    [(True, False), (True, True), (False, True), (False, False)],
                ]
            ),
        ],
        ids=["alt+ctrl", "alt", "ctrl"],
    )
    def test_multiple(
        self,
        qtui,
        tlui,
        args,
        tilia_state,
        request,
        modifiers,
        changes_time,
        select_value,
    ):
        tlui = request.getfixturevalue(tlui)
        tlui.create_component(**args)
        tlui.create_component(**get_time_shifted_args(args, 10))

        if "time" in args:
            click_time = [tlui[0].get_data("time"), tlui[1].get_data("time")]
        else:
            click_time = [tlui[0].get_data("start"), tlui[1].get_data("start")]

        click_timeline_ui_element_body(tlui[0], modifier=modifiers)
        assert ((tlui[0].is_selected(), tlui[1].is_selected())) == select_value[0]
        assert tilia_state.current_time == (click_time[0] if changes_time else 0)

        click_timeline_ui_element_body(tlui[1], modifier=modifiers)
        assert (tlui[0].is_selected(), tlui[1].is_selected()) == select_value[1]
        assert tilia_state.current_time == (click_time[1] if changes_time else 0)

        click_timeline_ui_element_body(tlui[0], modifier=modifiers)
        assert (tlui[0].is_selected(), tlui[1].is_selected()) == select_value[2]
        assert tilia_state.current_time == (click_time[0] if changes_time else 0)

        click_timeline_ui_element_body(tlui[1], modifier=modifiers)
        assert (tlui[0].is_selected(), tlui[1].is_selected()) == select_value[3]
        assert tilia_state.current_time == (click_time[1] if changes_time else 0)


class TestControlSelect:
    def test_does_not_deselect_if_nothing_clicked(self, marker_tlui):
        marker_tlui.create_marker(0)

        click_timeline_ui(marker_tlui, 0, modifier="ctrl")
        click_timeline_ui(marker_tlui, 50, modifier="ctrl")
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
