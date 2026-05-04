import functools
from unittest.mock import patch

import pytest

from tests.constants import EXAMPLE_MEDIA_DURATION, EXAMPLE_MEDIA_PATH
from tests.mock import Serve, patch_yes_or_no_dialog
from tests.ui.timelines.interact import click_timeline_ui, drag_mouse_in_timeline_view
from tests.utils import save_and_reopen, save_tilia_to_tmp_path
from tilia.file.common import are_tilia_data_equal
from tilia.media.player.base import MediaTimeChangeReason
from tilia.requests import Get, Post, get, post
from tilia.settings import settings
from tilia.timelines.timeline_kinds import (
    TimelineKind,
)
from tilia.timelines.timeline_kinds import (
    TimelineKind as TlKind,
)
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.dialogs.add_timeline_without_media import AddTimelineWithoutMedia
from tilia.ui.enums import ScrollType
from tilia.ui.timelines.collection.collection import TimelineSelector
from tilia.ui.timelines.constants import (
    MAX_PLAYBACK_WIDTH,
    PLAYBACK_AREA_WIDTH,
    ZOOM_MULTIPLIER,
)
from tilia.ui.timelines.marker import MarkerTimelineUI

ADD_TIMELINE_ACTIONS = [
    "timelines.add.hierarchy",
    "timelines.add.beat",
    "timelines.add.harmony",
    "timelines.add.marker",
    "timelines.add.audiowave",
]


class TestTimelineUICreation:
    @pytest.mark.parametrize("command", ADD_TIMELINE_ACTIONS)
    def test_create(self, command, tluis):
        with (
            Serve(Get.FROM_USER_BEAT_PATTERN, (True, [1])),
            Serve(Get.FROM_USER_STRING, (True, "")),
        ):
            commands.execute(command)
        assert len(tluis) == 1

    def test_create_multiple(self, tilia_state, tluis):
        create_actions = [
            "timelines.add.harmony",
            "timelines.add.marker",
            "timelines.add.beat",
            "timelines.add.hierarchy",
            "timelines.add.audiowave",
        ]
        with (
            Serve(Get.FROM_USER_BEAT_PATTERN, (True, [1])),
            Serve(Get.FROM_USER_STRING, (True, "")),
        ):
            for command in create_actions:
                commands.execute(command)
        assert len(tluis) == len(create_actions)

    def test_with_no_media_loaded_set_media_duration(self, tluis, tilia_state):
        tilia_state.duration = 0
        with Serve(
            Get.FROM_USER_ADD_TIMELINE_WITHOUT_MEDIA,
            (True, AddTimelineWithoutMedia.Result.SET_DURATION),
        ):
            with Serve(Get.FROM_USER_FLOAT, (True, 10)):
                with Serve(Get.FROM_USER_STRING, (True, "")):
                    commands.execute("timelines.add.marker")
        assert tilia_state.duration == 10
        assert len(tluis) == 1

    def test_with_no_media_loaded_load_media(self, tluis, tilia_state, resources):
        tilia_state.duration = 0
        with Serve(
            Get.FROM_USER_ADD_TIMELINE_WITHOUT_MEDIA,
            (True, AddTimelineWithoutMedia.Result.LOAD_MEDIA),
        ):
            with Serve(Get.FROM_USER_MEDIA_PATH, (True, EXAMPLE_MEDIA_PATH)):
                with Serve(Get.FROM_USER_STRING, (True, "")):
                    commands.execute("timelines.add.marker")
        assert tilia_state.duration == EXAMPLE_MEDIA_DURATION
        assert len(tluis) == 1

    def test_with_no_media_loaded_cancel_set_media_duration(self, tluis, tilia_state):
        tilia_state.duration = 0
        with Serve(
            Get.FROM_USER_ADD_TIMELINE_WITHOUT_MEDIA,
            (True, AddTimelineWithoutMedia.Result.SET_DURATION),
        ):
            with Serve(Get.FROM_USER_FLOAT, (False, 10)):
                commands.execute("timelines.add.marker")
        assert tilia_state.duration == 0
        assert len(tluis) == 0

    def test_with_no_media_loaded_cancelload_media(self, tluis, tilia_state, resources):
        tilia_state.duration = 0
        with Serve(
            Get.FROM_USER_ADD_TIMELINE_WITHOUT_MEDIA,
            (True, AddTimelineWithoutMedia.Result.LOAD_MEDIA),
        ):
            with Serve(Get.FROM_USER_MEDIA_PATH, (False, EXAMPLE_MEDIA_PATH)):
                commands.execute("timelines.add.marker")
        assert tilia_state.duration == 0
        assert len(tluis) == 0

    @pytest.mark.parametrize("command", ADD_TIMELINE_ACTIONS)
    def test_user_cancels_creation(self, command, tilia_state, tluis):
        with Serve(Get.FROM_USER_STRING, (False, "")):
            commands.execute(command)
        assert tluis.is_empty

    def test_delete(self, tls, tluis):
        with Serve(Get.FROM_USER_STRING, (True, "")):
            commands.execute("timelines.add.marker")

        tls.delete_timeline(tls[0])  # this should be a command
        assert tls.is_empty

    def test_update_select_order(self, tls, tluis):
        tl1 = tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test1")

        tl2 = tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test2")

        tlui1 = tluis.get_timeline_ui(tl1.id)
        tlui2 = tluis.get_timeline_ui(tl2.id)

        assert tluis._select_order[0] == tlui2

        click_timeline_ui(tlui1, 0)

        assert tluis._select_order[0] == tlui1

        click_timeline_ui(tlui2, 0)

        assert tluis._select_order[0] == tlui2


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
    @staticmethod
    def _set_auto_scroll(type: ScrollType):
        settings.set("general", "auto-scroll", type)
        post(Post.SETTINGS_UPDATED, ["general"])

    def test_continuous_is_triggered_when_playing(self, tluis):
        self._set_auto_scroll(ScrollType.CONTINUOUS)
        with patch.object(tluis, "center_on_time") as center_on_time_mock:
            post(Post.PLAYER_CURRENT_TIME_CHANGED, 50, MediaTimeChangeReason.PLAYBACK)
        center_on_time_mock.assert_called()

    @pytest.mark.parametrize("scroll_type", [ScrollType.CONTINUOUS, ScrollType.BY_PAGE])
    def test_is_not_triggered_when_seeking(self, scroll_type, tluis):
        self._set_auto_scroll(scroll_type)
        with patch.object(tluis, "center_on_time") as center_on_time_mock:
            commands.execute("media.seek", 50)
        center_on_time_mock.assert_not_called()

    @pytest.mark.parametrize("scroll_type", [ScrollType.CONTINUOUS, ScrollType.BY_PAGE])
    def test_is_not_triggered_when_scrollbar_is_pressed(self, scroll_type, tluis):
        self._set_auto_scroll(ScrollType.CONTINUOUS)
        with (
            patch.object(tluis.view, "is_hscrollbar_pressed", return_value=True),
            patch.object(tluis, "center_on_time") as center_on_time_mock,
        ):
            post(Post.PLAYER_CURRENT_TIME_CHANGED, 50, MediaTimeChangeReason.PLAYBACK)
        center_on_time_mock.assert_not_called()

    @pytest.mark.parametrize("scroll_type", [ScrollType.CONTINUOUS, ScrollType.BY_PAGE])
    def test_is_not_triggered_when_scroll_type_is_off(self, scroll_type, tluis):
        self._set_auto_scroll(ScrollType.OFF)
        with patch.object(tluis, "center_on_time") as center_on_time_mock:
            post(Post.PLAYER_CURRENT_TIME_CHANGED, 50, MediaTimeChangeReason.PLAYBACK)
        center_on_time_mock.assert_not_called()

    @pytest.mark.parametrize("scroll_type", [ScrollType.CONTINUOUS, ScrollType.BY_PAGE])
    def test_is_not_triggered_when_dragging(self, scroll_type, tluis):
        self._set_auto_scroll(ScrollType.CONTINUOUS)
        post(Post.SLIDER_DRAG_START)
        with patch.object(tluis, "center_on_time") as center_on_time_mock:
            post(Post.PLAYER_CURRENT_TIME_CHANGED, 50, MediaTimeChangeReason.PLAYBACK)
        post(Post.SLIDER_DRAG_END)
        center_on_time_mock.assert_not_called()

    def test_by_page_is_triggered(self, tluis):
        self._set_auto_scroll(ScrollType.BY_PAGE)
        viewport = tluis.view.current_viewport_x
        time_outside = time_x_converter.get_time_by_x(viewport[1] + 100)
        with (
            patch.object(tluis, "center_on_time") as center_on_time_mock,
            patch.object(tluis.view, "move_to_x") as move_to_x_mock,
        ):
            post(
                Post.PLAYER_CURRENT_TIME_CHANGED,
                time_outside,
                MediaTimeChangeReason.PLAYBACK,
            )
        move_to_x_mock.assert_called()
        center_on_time_mock.assert_not_called()

    def test_by_page_is_not_triggered_when_not_over_threshold(self, tluis):
        self._set_auto_scroll(ScrollType.BY_PAGE)
        viewport = tluis.view.current_viewport_x
        x_center = (viewport[0] + viewport[1]) / 2
        time_inside = time_x_converter.get_time_by_x(x_center)
        with patch.object(tluis.view, "move_to_x") as move_to_x_mock:
            post(
                Post.PLAYER_CURRENT_TIME_CHANGED,
                time_inside,
                MediaTimeChangeReason.PLAYBACK,
            )
        move_to_x_mock.assert_not_called()


def test_set_timeline_height_updates_playback_line_height(tls, tluis):
    tls.create_timeline(TimelineKind.MARKER_TIMELINE)
    tls.set_timeline_data(tls[0].id, "height", 100)
    assert tluis[0].scene.playback_line.line().dy() == 100


def test_zooming_updates_playback_line_position(tls, tluis):
    tls.create_timeline(TimelineKind.MARKER_TIMELINE)
    commands.execute("media.seek", 50)
    commands.execute("view.zoom.in")
    assert tluis[0].scene.playback_line.line().x1() == pytest.approx(
        time_x_converter.get_x_by_time(50)
    )


class TestSeek:
    def test_playback_line_follows_slider_drag_if_media_is_not_playing(
        self, marker_tlui, slider_tlui
    ):
        y = slider_tlui.trough.pos().y()
        click_timeline_ui(slider_tlui, 0, y=y)
        target_x = time_x_converter.get_x_by_time(50)
        drag_mouse_in_timeline_view(target_x, y)
        assert marker_tlui.playback_line.line().x1() == pytest.approx(target_x)

    def test_playback_line_follows_slider_drag_if_media_is_playing(
        self, marker_tlui, slider_tlui, tilia_state
    ):
        y = slider_tlui.trough.pos().y()
        click_timeline_ui(slider_tlui, 0, y=y)
        target_x = time_x_converter.get_x_by_time(60)
        drag_mouse_in_timeline_view(target_x, y)
        assert marker_tlui.playback_line.line().x1() == target_x

    @pytest.mark.parametrize(
        "tlui,request_to_serve, add_request",
        [
            ("marker", None, "timeline.marker.add"),
            (
                "harmony",
                (
                    Get.FROM_USER_MODE_PARAMS,
                    (True, {"step": 0, "accidental": 0, "type": "major"}),
                ),
                "timeline.harmony.add_mode",
            ),
            (
                "harmony",
                (
                    Get.FROM_USER_HARMONY_PARAMS,
                    (True, {"step": 0, "accidental": 0, "quality": "major"}),
                ),
                "timeline.harmony.add_harmony",
            ),
            ("beat", None, "timeline.beat.add"),
        ],
        indirect=["tlui"],
    )
    def test_add_component_while_media_is_playing_and_slider_is_being_dragged(
        self,
        tlui,
        request_to_serve,
        add_request,
        slider_tlui,
        tilia_state,
    ):
        y = slider_tlui.trough.pos().y()
        click_timeline_ui(slider_tlui, 0, y=y)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(50), y)
        if request_to_serve:
            with Serve(*request_to_serve):
                commands.execute(add_request)
        else:
            commands.execute(add_request)
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
        commands.execute("timeline.hierarchy.add", start=10, end=50, level=1)
        self.tlui.select_element(self.tlui[0])
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 50)

    def test_loop_hierarchy_move_start_end(self):
        commands.execute("timeline.hierarchy.add", start=10, end=50, level=1)
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
        commands.execute("timeline.hierarchy.add", start=10, end=50, level=1)
        hui = self.tlui[0]
        self.tlui.select_element(hui)
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 50)

        commands.execute("timeline.component.delete")
        assert get(Get.LOOP_TIME) == (0, 0)

    def test_loop_hierarchy_neighbouring_passes(self):
        commands.execute("timeline.hierarchy.add", start=10, end=20, level=1)
        commands.execute("timeline.hierarchy.add", start=20, end=30, level=1)
        self.tlui.select_element(self.tlui[0])
        self.tlui.select_element(self.tlui[1])
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 30)

    def test_loop_hierarchy_disjunct_fails(self):
        commands.execute("timeline.hierarchy.add", start=10, end=20, level=1)
        commands.execute("timeline.hierarchy.add", start=25, end=30, level=1)
        self.tlui.select_element(self.tlui[0])
        self.tlui.select_element(self.tlui[1])
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (0, 0)

    def test_loop_hierarchy_delete_end_continues(self):
        commands.execute("timeline.hierarchy.add", start=10, end=50, level=1)
        commands.execute("timeline.hierarchy.add", start=50, end=100, level=1)
        self.tlui.select_all_elements()
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 100)

        self.tlui.deselect_all_elements()
        self.tlui.select_element(self.tlui[0])
        commands.execute("timeline.component.delete")
        assert get(Get.LOOP_TIME) == (50, 100)

    def test_loop_hierarchy_delete_middle_cancels(self):
        commands.execute("timeline.hierarchy.add", start=0, end=10, level=1)
        commands.execute("timeline.hierarchy.add", start=10, end=50, level=1)
        commands.execute("timeline.hierarchy.add", start=50, end=100, level=1)
        self.tlui.select_all_elements()
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (0, 100)

        self.tlui.deselect_all_elements()
        self.tlui.select_element(self.tlui[1])
        commands.execute("timeline.component.delete")
        assert get(Get.LOOP_TIME) == (0, 0)

    def test_loop_hierarchy_merge_split(self):
        commands.execute("timeline.hierarchy.add", start=10, end=20, level=1)
        self.tlui.select_all_elements()
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 20)

        with Serve(Get.MEDIA_CURRENT_TIME, 15):
            commands.execute("timeline.hierarchy.split")
        assert get(Get.LOOP_TIME) == (10, 20)

        self.tlui.deselect_all_elements()
        self.tlui.select_all_elements()
        commands.execute("timeline.hierarchy.merge")
        assert get(Get.LOOP_TIME) == (10, 20)

    def test_loop_undo_manager_cancels(self):
        commands.execute("timeline.hierarchy.add", start=10, end=20, level=1)
        self.tlui.select_all_elements()
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 20)

        commands.execute("edit.undo")
        assert get(Get.LOOP_TIME) == (0, 0)

    def test_player_cancel_loop_clears_full_state(self, tluis, tilia_state):
        # Regression test for #438: PLAYER_CANCEL_LOOP (posted by
        # app.load_media after a successful media swap, among other
        # paths) used to leave loop_elements populated and the player
        # still in is_looping=True, so playback would keep seeking
        # back over the new media.
        self.tlui.create_hierarchy(10, 20, 1)
        self.tlui.select_all_elements()
        post(Post.PLAYER_TOGGLE_LOOP, True)
        assert get(Get.LOOP_TIME) == (10, 20)
        assert tluis.loop_elements
        assert tilia_state.player.is_looping

        post(Post.PLAYER_CANCEL_LOOP)

        assert get(Get.LOOP_TIME) == (0, 0)
        assert not tluis.loop_elements
        assert not tilia_state.player.is_looping


class TestClearAllTimelines:
    def test_none(self, tilia, tluis):
        commands.execute("timelines.clear_all")
        assert tluis.is_empty

    def test_non_clearable_timeline(self, tilia, tls, tluis):
        tls.create_timeline(TimelineKind.SLIDER_TIMELINE)
        commands.execute("timelines.clear_all")

    def test_timelines_are_empty(self, tilia, tls, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timelines.add.harmony", name="")
        commands.execute("timelines.clear_all")

    def test_not_clearable_and_empty_timeline(self, tilia, tls, tluis):
        tls.create_timeline(TimelineKind.SLIDER_TIMELINE)
        commands.execute("timelines.add.marker", name="")
        commands.execute("timelines.clear_all")

    def test_user_cancels(self, tilia, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timeline.marker.add")
        assert not tluis[0].is_empty
        with patch_yes_or_no_dialog(False):
            commands.execute("timelines.clear_all")

        assert not tluis[0].is_empty

    def test_one(self, tilia, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timeline.marker.add")
        assert not tluis[0].is_empty
        with patch_yes_or_no_dialog(True):
            commands.execute("timelines.clear_all")

        assert tluis[0].is_empty

    def test_multiple(self, tilia, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timeline.marker.add")

        commands.execute("timelines.add.marker", name="")
        commands.execute("timeline.marker.add")

        with patch_yes_or_no_dialog(True):
            commands.execute("timelines.clear_all")

        assert all(tl.is_empty for tl in tluis[0])


class TestZoom:
    def test_zoom_in_multiplies_by_factor(self, tilia_state, tluis):
        tilia_state.duration = 100
        commands.execute("view.zoom.set", 1.0)
        commands.execute("view.zoom.in")
        assert get(Get.CURRENT_ZOOM) == pytest.approx(1.0 * ZOOM_MULTIPLIER)

    def test_zoom_out_divides_by_factor(self, tilia_state, tluis):
        tilia_state.duration = 100
        commands.execute("view.zoom.set", 1.0)
        commands.execute("view.zoom.out")
        assert get(Get.CURRENT_ZOOM) == pytest.approx(1.0 / ZOOM_MULTIPLIER)

    def test_zoom_in_rejected_at_physical_max(self, tilia_state, tluis):
        tilia_state.duration = 100
        zoom_ref = get(Get.ZOOM_REFERENCE_WIDTH)
        # largest ratio whose next step would exceed MAX_PLAYBACK_WIDTH
        at_limit = MAX_PLAYBACK_WIDTH / zoom_ref / ZOOM_MULTIPLIER
        commands.execute("view.zoom.set", at_limit)
        commands.execute("view.zoom.in")
        assert get(Get.CURRENT_ZOOM) == pytest.approx(at_limit)

    def test_zoom_out_rejected_at_physical_min(self, tilia_state, tluis):
        tilia_state.duration = 100
        zoom_ref = get(Get.ZOOM_REFERENCE_WIDTH)
        # ratio where new_width=1 (passes); next step gives new_width<1 (rejected)
        at_limit = 1 / zoom_ref
        commands.execute("view.zoom.set", at_limit)
        commands.execute("view.zoom.out")
        assert get(Get.CURRENT_ZOOM) == pytest.approx(at_limit)

    def test_zoom_set_changes_playback_area_width(self, tilia_state, tluis):
        tilia_state.duration = 100
        zoom_ref = get(Get.ZOOM_REFERENCE_WIDTH)
        commands.execute("view.zoom.set", 2.0)
        assert get(Get.PLAYBACK_AREA_WIDTH) == pytest.approx(zoom_ref * 2.0)

    def test_zoom_without_media_uses_default_reference(self, tilia_state, tluis):
        tilia_state.duration = 0
        commands.execute("view.zoom.set", 2.0)
        assert get(Get.PLAYBACK_AREA_WIDTH) == pytest.approx(PLAYBACK_AREA_WIDTH * 2.0)

    def test_zoom_resets_to_one_on_clear(self, tilia_state, tluis):
        tilia_state.duration = 100
        commands.execute("view.zoom.set", 3.0)
        post(Post.APP_CLEAR)
        assert get(Get.CURRENT_ZOOM) == pytest.approx(1.0)

    def test_zoom_preserved_when_duration_changes(self, tilia_state, tluis):
        tilia_state.duration = 100
        commands.execute("view.zoom.set", 2.0)
        post(Post.PLAYER_DURATION_AVAILABLE, 200)
        assert get(Get.CURRENT_ZOOM) == pytest.approx(2.0)

    def test_zoom_saved_and_restored_on_file_open(self, tilia_state, tluis, tmp_path):
        duration = 123
        tilia_state.duration = duration
        commands.execute("view.zoom.set", 1.5)
        original_width = get(Get.PLAYBACK_AREA_WIDTH)
        file_path = save_tilia_to_tmp_path(tmp_path)
        assert settings.get_file_zoom(file_path) == pytest.approx(1.5)
        save_and_reopen(tmp_path)
        # save_and_reopen opens the .tla file but doesn't load media, so
        # PLAYER_DURATION_AVAILABLE never fires; post it manually to trigger
        # _on_duration_available and apply the restored zoom to the timeline width
        post(Post.PLAYER_DURATION_AVAILABLE, duration)
        assert get(Get.CURRENT_ZOOM) == pytest.approx(1.5)
        assert get(Get.PLAYBACK_AREA_WIDTH) == pytest.approx(original_width)


def test_timeline_command_fails(tilia, qtui, tluis, marker_tlui, tilia_errors):
    healthy_state = tilia.get_app_state()

    def add_and_fail():
        # It's important that we let the operation happen
        # so a marker is actually created before the exception is raised.
        # In this way, there is actually a change in a app state
        # that will need to be reverted.
        marker_tlui.on_add()
        raise Exception

    MarkerTimelineUI.add_and_fail = add_and_fail

    callback = functools.partial(
        tluis.on_timeline_command,
        TimelineKind.MARKER_TIMELINE,
        "add_and_fail",
        TimelineSelector.ALL,
    )
    # register the add_and_fail as a callback for the timeline.marker.add command
    commands.register("timeline.marker.add", callback)

    commands.execute("timeline.marker.add")

    assert are_tilia_data_equal(tilia.get_app_state(), healthy_state)
