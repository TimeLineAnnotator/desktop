from unittest.mock import patch, Mock

import pytest

import tilia
from tilia import settings
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
from tilia.ui.timelines.collection.collection import TimelineUIs
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

    @pytest.mark.skip("Needs reimplementing")
    def test_ask_choose_timeline(self, tluis, beat_tlui, hierarchy_tlui, marker_tlui):
        with patch("tilia.ui.dialogs.choose.ChooseDialog", lambda _: 1):
            assert tluis.ask_choose_timeline("", "") == beat_tlui.timeline

        with patch("tilia.ui.timelines.collection.ChooseDialog.ask", lambda _: 2):
            assert tluis.ask_choose_timeline("", "") == hierarchy_tlui.timeline

        with patch("tilia.ui.timelines.collection.ChooseDialog.ask", lambda _: 3):
            assert tluis.ask_choose_timeline("", "") == marker_tlui.timeline

    @pytest.mark.skip("Needs reimplementing")
    def test_ask_choose_timeline_restrict_kind(
        self, tkui, tluis, beat_tlui, hierarchy_tlui, marker_tlui
    ):
        with (
            patch("tilia.ui.timelines.collection.ChooseDialog") as choose_window_mock,
        ):

            class ChooseWindowDummy:
                call_count = 0

                def ask(self):
                    """
                    ChooseDialog.ask must return the ordinal of
                    'hierarchy_tlui' and 'marker_tlui', respectively.
                    That is, 2 and 3.
                    """
                    self.call_count += 1
                    return self.call_count + 1

            choose_window_mock.return_value = ChooseWindowDummy()

            tluis.ask_choose_timeline("title", "prompt", TlKind.HIERARCHY_TIMELINE)

            choose_window_mock.assert_called_with(
                tkui.root, "title", "prompt", [(2, str(hierarchy_tlui))]
            )

            tluis.ask_choose_timeline("title", "prompt", TlKind.MARKER_TIMELINE)

            choose_window_mock.assert_called_with(
                tkui.root, "title", "prompt", [(3, str(marker_tlui))]
            )


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
        post(
            Post.PLAYER_CURRENT_TIME_CHANGED, 50, reason=MediaTimeChangeReason.PLAYBACK
        )
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
        post(
            Post.PLAYER_CURRENT_TIME_CHANGED, 50, reason=MediaTimeChangeReason.PLAYBACK
        )
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
