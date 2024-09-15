from unittest.mock import patch, Mock

import pytest

from tests.ui.timelines.interact import click_timeline_ui, drag_mouse_in_timeline_view
from tilia import errors as tilia_errors
from tests.mock import PatchGet, PatchPost, Serve
from tilia.media.player.base import MediaTimeChangeReason
from tilia.requests import Post, post, get, Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import (
    TimelineKind as TlKind,
    TimelineKind,
)
from tilia.ui import actions
from tilia.ui.actions import TiliaAction
from tilia.ui.coords import get_x_by_time


ADD_TIMELINE_ACTIONS = [
    TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE,
    TiliaAction.TIMELINES_ADD_BEAT_TIMELINE,
    TiliaAction.TIMELINES_ADD_HARMONY_TIMELINE,
    TiliaAction.TIMELINES_ADD_MARKER_TIMELINE,
    TiliaAction.TIMELINES_ADD_AUDIOWAVE_TIMELINE,
]


class TestTimelineUICreation:
    @pytest.mark.parametrize("action", ADD_TIMELINE_ACTIONS)
    def test_create(self, action, tilia_state, tluis, actions):
        with (
            Serve(Get.FROM_USER_BEAT_PATTERN, (True, [1])),
            Serve(Get.FROM_USER_STRING, ("", True)),
        ):
            actions.trigger(action)
        assert len(tluis) == 1

    def test_create_multiple(self, tilia_state, tluis, actions):
        create_actions = [
            TiliaAction.TIMELINES_ADD_HARMONY_TIMELINE,
            TiliaAction.TIMELINES_ADD_MARKER_TIMELINE,
            TiliaAction.TIMELINES_ADD_BEAT_TIMELINE,
            TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE,
            TiliaAction.TIMELINES_ADD_AUDIOWAVE_TIMELINE,
        ]
        with (
            Serve(Get.FROM_USER_BEAT_PATTERN, (True, [1])),
            Serve(Get.FROM_USER_STRING, ("", True)),
        ):
            for action in create_actions:
                actions.trigger(action)
        assert len(tluis) == len(create_actions)

    @pytest.mark.parametrize("action", ADD_TIMELINE_ACTIONS)
    def test_user_cancels_creation(self, action, tilia_state, tluis, actions):
        with Serve(Get.FROM_USER_STRING, ("", False)):
            actions.trigger(action)
        assert tluis.is_empty

    def test_delete(self, tls, actions):
        with Serve(Get.FROM_USER_STRING, ("", True)):
            actions.trigger(TiliaAction.TIMELINES_ADD_MARKER_TIMELINE)

        tls.delete_timeline(tls[0])  # this should be an user action
        assert tls.is_empty

    def test_update_select_order(self, tls, tluis):
        tl1 = tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test1")

        tl2 = tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test2")

        tlui1 = tluis.get_timeline_ui(tl1.id)
        tlui2 = tluis.get_timeline_ui(tl2.id)

        assert tluis._select_order[0] == tlui2

        with patch("tilia.ui.timelines.selection_box.SelectionBoxQt", lambda *_: None):
            post(Post.TIMELINE_VIEW_LEFT_CLICK, tlui1.view, 0, 0, 0, None, double=False)

        assert tluis._select_order[0] == tlui1

        with patch("tilia.ui.timelines.selection_box.SelectionBoxQt", lambda *_: None):
            post(Post.TIMELINE_VIEW_LEFT_CLICK, tlui2.view, 0, 0, 0, None, double=False)

        assert tluis._select_order[0] == tlui2

    @pytest.mark.parametrize("action", ADD_TIMELINE_ACTIONS)
    def test_create_timeline_without_media_duration_fails(
        self, action, actions, tilia_state, tluis
    ):
        tilia_state.duration = 0
        actions.trigger(action)
        assert tluis.is_empty

    def test_create_timeline_without_media_duration_displays_error(self, tilia, qtui):
        patch_get_target = "tilia.ui.timelines.collection.requests.args"
        with PatchPost("tilia.errors", Post.DISPLAY_ERROR) as mock:
            with PatchGet(patch_get_target, Get.MEDIA_DURATION, 0):
                actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

        mock.assert_called_once_with(
            Post.DISPLAY_ERROR, *tilia_errors.CREATE_TIMELINE_WITHOUT_MEDIA
        )


class TestServe:
    def test_serve_timeline_elements_selected_empty_case(self, tluis):
        assert not get(Get.TIMELINE_ELEMENTS_SELECTED)

    def test_serve_timeline_elements_selected_case_false(self, tls, tluis):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        assert not get(Get.TIMELINE_ELEMENTS_SELECTED)

    def test_serve_timeline_elements_selected_case_true(self, tls, tluis):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tluis[0].select_all_elements()

        assert get(Get.TIMELINE_ELEMENTS_SELECTED)

    def test_serve_timeline_elements_selected_case_false_multiple_timelines(
        self, tls, tluis
    ):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        assert not get(Get.TIMELINE_ELEMENTS_SELECTED)

    def test_serve_timeline_elements_selected_case_true_multiple_tls(self, tls, tluis):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tluis[2].select_all_elements()

        assert get(Get.TIMELINE_ELEMENTS_SELECTED)


class TestAutoScroll:
    def test_auto_scroll_is_triggered_when_playing(self, tluis):
        mock = Mock()
        tluis.center_on_time = mock
        tluis.auto_scroll_is_enabled = True
        post(Post.PLAYER_CURRENT_TIME_CHANGED, 50, MediaTimeChangeReason.PLAYBACK)
        mock.assert_called()

    def test_auto_scroll_is_not_triggered_when_seeking(self, tluis):
        mock = Mock()
        tluis.center_on_time = mock
        tluis.auto_scroll_is_enabled = True
        post(Post.PLAYER_SEEK, 50)
        mock.assert_not_called()

    def test_auto_scroll_is_not_triggered_when_scrollbar_is_pressed(self, tluis):
        center_on_time_mock = Mock()
        tluis.center_on_time = center_on_time_mock
        tluis.auto_scroll_is_enabled = True
        tluis.view.is_hscrollbar_pressed = Mock(return_value=True)
        post(Post.PLAYER_CURRENT_TIME_CHANGED, 50, MediaTimeChangeReason.PLAYBACK)
        center_on_time_mock.assert_not_called()

    def test_set_timeline_height_updates_playback_line_height(self, tls, tluis):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        tls.set_timeline_data(tls[0].id, "height", 100)
        assert tluis[0].scene.playback_line.line().dy() == 100

    def test_zooming_updates_playback_line_position(self, tls, tluis):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        post(Post.PLAYER_SEEK, 50)
        post(Post.VIEW_ZOOM_IN)
        assert tluis[0].scene.playback_line.line().x1() == pytest.approx(
            get_x_by_time(50)
        )


class TestSeek:
    def test_playback_line_follows_slider_drag_if_media_is_not_playing(
        self, marker_tlui, slider_tlui
    ):
        y = slider_tlui.trough.pos().y()
        click_timeline_ui(slider_tlui, 0, y=y)
        target_x = get_x_by_time(50)
        drag_mouse_in_timeline_view(target_x, y)
        assert marker_tlui.playback_line.line().x1() == pytest.approx(target_x)

    def test_playback_line_follows_slider_drag_if_media_is_playing(
        self, marker_tlui, slider_tlui, tilia_state
    ):
        y = slider_tlui.trough.pos().y()
        click_timeline_ui(slider_tlui, 0, y=y)
        target_x = get_x_by_time(60)
        drag_mouse_in_timeline_view(target_x, y)
        tilia_state.current_time = 75
        assert marker_tlui.playback_line.line().x1() == target_x

    @pytest.mark.parametrize(
        "tlui,request_to_serve, add_request",
        [
            ("marker", None, TiliaAction.MARKER_ADD),
            (
                "harmony",
                (
                    Get.FROM_USER_MODE_PARAMS,
                    (True, {"step": 0, "accidental": 0, "type": "major"}),
                ),
                TiliaAction.MODE_ADD,
            ),
            (
                "harmony",
                (
                    Get.FROM_USER_HARMONY_PARAMS,
                    (True, {"step": 0, "accidental": 0, "quality": "major"}),
                ),
                TiliaAction.HARMONY_ADD,
            ),
            ("beat", None, TiliaAction.BEAT_ADD),
        ],
        indirect=["tlui"],
    )
    def test_add_component_while_media_is_playing_and_slider_is_being_dragged(
        self, tlui, request_to_serve, add_request, slider_tlui, tilia_state, actions
    ):
        y = slider_tlui.trough.pos().y()
        click_timeline_ui(slider_tlui, 0, y=y)
        drag_mouse_in_timeline_view(get_x_by_time(50), y)
        tilia_state.current_time = 75
        if request_to_serve:
            with Serve(*request_to_serve):
                actions.trigger(add_request)
        else:
            actions.trigger(add_request)
        assert tlui[0].get_data("time") == pytest.approx(50)


class TestLoop:
    def test_loop_with_none_selected(self, tilia_state):
        tilia_state.duration = 100
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (0, 100)

    @pytest.fixture(autouse=True)
    def _tlui(self, hierarchy_tlui):
        self.tlui = hierarchy_tlui

    def test_loop_with_hierarchy(self, tilia_state):
        tilia_state.duration = 100
        self.tlui.create_hierarchy(10, 50, 1)
        self.tlui.select_element(self.tlui[0])
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 50)

    def test_loop_hierarchy_move_start_end(self):
        self.tlui.create_hierarchy(10, 50, 1)
        hrc = self.tlui.timeline[0]
        hui = self.tlui[0]
        self.tlui.select_element(hui)
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 50)

        hrc.start = 0
        assert hrc.start == 0
        post(
            Post.TIMELINE_COMPONENT_SET_DATA_DONE,
            hui.timeline_ui.id,
            hui.id,
            "start",
            0,
        )
        assert get(Get.LOOP_TIME) == (0, 50)

    def test_loop_hierarchy_delete_all_cancels(self):
        self.tlui.create_hierarchy(10, 50, 1)
        hui = self.tlui[0]
        self.tlui.select_element(hui)
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 50)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)
        assert get(Get.LOOP_TIME) == (0, 0)

    def test_loop_hierarchy_neighbouring_passes(self):
        self.tlui.create_hierarchy(10, 20, 1)
        self.tlui.create_hierarchy(20, 30, 1)
        self.tlui.select_element(self.tlui[0])
        self.tlui.select_element(self.tlui[1])
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 30)

    def test_loop_hierarchy_disjunct_fails(self):
        self.tlui.create_hierarchy(10, 20, 1)
        self.tlui.create_hierarchy(25, 30, 1)
        self.tlui.select_element(self.tlui[0])
        self.tlui.select_element(self.tlui[1])
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (0, 0)

    def test_loop_hierarchy_delete_end_continues(self):
        self.tlui.create_hierarchy(10, 50, 1)
        self.tlui.create_hierarchy(50, 100, 1)
        self.tlui.select_all_elements()
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 100)

        self.tlui.deselect_all_elements()
        self.tlui.select_element(self.tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)
        assert get(Get.LOOP_TIME) == (50, 100)

    def test_loop_hierarchy_delete_middle_cancels(self):
        self.tlui.create_hierarchy(0, 10, 1)
        self.tlui.create_hierarchy(10, 50, 1)
        self.tlui.create_hierarchy(50, 100, 1)
        self.tlui.select_all_elements()
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (0, 100)

        self.tlui.deselect_all_elements()
        self.tlui.select_element(self.tlui[1])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)
        assert get(Get.LOOP_TIME) == (0, 0)

    def test_loop_hierarchy_merge_split(self):
        self.tlui.create_hierarchy(10, 20, 1)
        self.tlui.select_all_elements()
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 20)

        with Serve(Get.MEDIA_CURRENT_TIME, 15):
            actions.trigger(TiliaAction.HIERARCHY_SPLIT)
        assert get(Get.LOOP_TIME) == (10, 20)

        self.tlui.deselect_all_elements()
        self.tlui.select_all_elements()
        actions.trigger(TiliaAction.HIERARCHY_MERGE)
        assert get(Get.LOOP_TIME) == (10, 20)

    def test_loop_undo_manager_cancels(self):
        self.tlui.create_hierarchy(10, 20, 1)
        self.tlui.select_all_elements()
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 20)

        post(Post.EDIT_UNDO)
        assert get(Get.LOOP_TIME) == (0, 0)
