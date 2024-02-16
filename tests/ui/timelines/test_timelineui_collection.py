from unittest.mock import patch, Mock

import pytest

from tests.ui.timelines.interact import click_timeline_ui, drag_mouse_in_timeline_view
from tilia import errors as tilia_errors
from tests.mock import PatchGet, PatchPost
from tilia.media.player.base import MediaTimeChangeReason
from tilia.requests import Post, post, get, Get
from tilia.timelines.timeline_kinds import (
    TimelineKind as TlKind,
    TimelineKind,
)
from tilia.ui import actions
from tilia.ui.actions import TiliaAction
from tilia.ui.coords import get_x_by_time
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI
from tilia.ui.timelines.slider.timeline import SliderTimelineUI


class TestTimelineUICollection:
    def test_create_timeline_ui_hierarchy_timeline(self, tls, tluis):
        tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test")

        ui = list(tluis.get_timeline_uis())[0]

        assert ui.__class__ == HierarchyTimelineUI
        assert ui in tluis._timeline_uis
        assert tluis._select_order[0] == ui

        # cleanup
        tls.delete_timeline(ui.timeline)

    def test_create_timeline_ui_slider_timeline(self, tls, tluis):
        tls.create_timeline(TlKind.SLIDER_TIMELINE, name="test")

        ui = list(tluis.get_timeline_uis())[0]

        assert ui.__class__ == SliderTimelineUI
        assert ui in tluis._timeline_uis
        assert tluis._select_order[0] == ui

        # cleanup
        tls.delete_timeline(ui.timeline)

    def test_create_two_timeline_uis(self, tls, tluis):
        tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test1")

        tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test2")

        ui1, ui2 = tluis._select_order

        assert ui1.get_data("name") == "test2"
        assert ui2.get_data("name") == "test1"

        # cleanup
        tls.delete_timeline(ui1.timeline)
        tls.delete_timeline(ui2.timeline)

    def test_create_timeline_uis_of_all_kinds(self, tls, tluis):

        for kind in TimelineKind:
            if kind == TimelineKind.BEAT_TIMELINE:
                tls.create_timeline(kind, beat_pattern=[2])
                continue
            tls.create_timeline(kind)

        assert len(tluis.get_timeline_uis()) == len(TimelineKind)

        for timeline in tls._timelines.copy():
            tls.delete_timeline(timeline)

    def test_delete_timeline_ui(self, tls, tluis):
        tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test")

        tlui = list(tluis.get_timeline_uis())[0]

        tls.delete_timeline(tlui.timeline)

        assert not tluis._timeline_uis
        assert not tluis._select_order

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


class TestServe:
    def test_serve_are_timeline_elements_selected_empty_case(self, tluis):
        assert not get(Get.ARE_TIMELINE_ELEMENTS_SELECTED)

    def test_serve_are_timeline_elements_selected_case_false(self, tls, tluis):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        assert not get(Get.ARE_TIMELINE_ELEMENTS_SELECTED)

    def test_serve_are_timeline_elements_selected_case_true(self, tls, tluis):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tluis[0].select_all_elements()

        assert get(Get.ARE_TIMELINE_ELEMENTS_SELECTED)

    def test_serve_are_timeline_elements_selected_case_false_multiple_timelines(
        self, tls, tluis
    ):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        assert not get(Get.ARE_TIMELINE_ELEMENTS_SELECTED)

    def test_serve_are_timeline_elements_selected_case_true_multiple_tls(
        self, tls, tluis
    ):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tluis[2].select_all_elements()

        assert get(Get.ARE_TIMELINE_ELEMENTS_SELECTED)

    def test_create_timeline_without_media_load_displays_error(self, tilia, qtui):
        patch_target = "tilia.ui.timelines.collection.requests.args"
        with PatchPost(patch_target, Post.DISPLAY_ERROR) as mock:
            with PatchGet(patch_target, Get.MEDIA_DURATION, 0):
                actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

        mock.assert_called_once_with(
            Post.DISPLAY_ERROR, *tilia_errors.CREATE_TIMELINE_WITHOUT_MEDIA
        )


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
        assert marker_tlui.playback_line.line().x1() == target_x

    def test_playback_line_follows_slider_drag_if_media_is_playing(
        self, marker_tlui, slider_tlui, tilia_state
    ):
        y = slider_tlui.trough.pos().y()
        click_timeline_ui(slider_tlui, 0, y=y)
        target_x = get_x_by_time(60)
        drag_mouse_in_timeline_view(target_x, y)
        tilia_state.current_time = 75
        assert marker_tlui.playback_line.line().x1() == target_x
