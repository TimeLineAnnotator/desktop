import os.path
import time
import tkinter as tk
from collections import OrderedDict
from unittest.mock import patch, PropertyMock, mock_open

import pytest

from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.menus import DynamicMenu
from tilia.ui.tkinterui import TkinterUI
from tests.conftest import pump_events
from tilia.ui.windows import WindowKind


class TiliaDummy:
    def __init__(self):
        self.media_length = 99
        self.media_metadata = {"title": "test"}

    @property
    def media_path(self):
        return "test_path"


class TestTkinterUI:
    @patch("tilia.ui.tkinterui.Inspect")
    def test_on_request_window_inspect(self, inspect_mock, tkui):
        tkui.on_request_window(WindowKind.INSPECT)
        assert inspect_mock.called

        tkui.on_request_window(WindowKind.INSPECT)
        assert tkui._windows[WindowKind.INSPECT].focus.called

    @patch("tilia.ui.tkinterui.ManageTimelines")
    def test_on_request_window_manage_timelines(self, managetl_mock, tkui):
        tkui.on_request_window(WindowKind.MANAGE_TIMELINES)
        assert managetl_mock.called

    @patch("tilia.ui.tkinterui.MediaMetadataWindow")
    def test_on_request_window_media_metadata(self, mngmtdata_mock, tilia):
        tilia.ui.on_request_window(WindowKind.MEDIA_METADATA)
        assert mngmtdata_mock.called

    @patch("tilia.ui.tkinterui.About")
    def test_on_request_window_about(self, about_mock, tkui):
        tkui.on_request_window(WindowKind.ABOUT)
        assert about_mock.called

    def test_on_marker_timeline_kind_instanced(self, tkui):
        assert not tkui.enabled_dynamic_menus

        tkui._on_timeline_kind_instanced(TimelineKind.MARKER_TIMELINE)

        assert tkui.enabled_dynamic_menus == {DynamicMenu.MARKER_TIMELINE}

        tkui._on_timeline_kind_instanced(TimelineKind.MARKER_TIMELINE)
        tkui._on_timeline_kind_instanced(TimelineKind.MARKER_TIMELINE)

        assert tkui.enabled_dynamic_menus == {DynamicMenu.MARKER_TIMELINE}

        # cleanup
        tkui.enabled_dynamic_menus = set()

    def test_on_hierarchy_timeline_kind_instanced(self, tkui):
        assert not tkui.enabled_dynamic_menus

        tkui._on_timeline_kind_instanced(TimelineKind.HIERARCHY_TIMELINE)

        assert tkui.enabled_dynamic_menus == {DynamicMenu.HIERARCHY_TIMELINE}

        tkui._on_timeline_kind_instanced(TimelineKind.HIERARCHY_TIMELINE)
        tkui._on_timeline_kind_instanced(TimelineKind.HIERARCHY_TIMELINE)

        assert tkui.enabled_dynamic_menus == {DynamicMenu.HIERARCHY_TIMELINE}

        # cleanup
        tkui.enabled_dynamic_menus = set()

    def test_on_marker_timeline_kind_uninstanced(self, tkui):
        tkui._on_timeline_kind_instanced(TimelineKind.MARKER_TIMELINE)
        tkui._on_timeline_kind_uninstanced(TimelineKind.MARKER_TIMELINE)
        assert tkui.enabled_dynamic_menus == set()

    def test_on_hierarchy_timeline_kind_uninstanced(self, tkui):
        tkui._on_timeline_kind_instanced(TimelineKind.HIERARCHY_TIMELINE)
        tkui._on_timeline_kind_uninstanced(TimelineKind.HIERARCHY_TIMELINE)
        assert tkui.enabled_dynamic_menus == set()

    def test_on_menu_import_markers_from_csv(self, tkui, marker_tlui, beat_tlui):
        def get_by_kind(kind):
            if kind == TimelineKind.MARKER_TIMELINE:
                return [marker_tlui]
            elif kind == TimelineKind.BEAT_TIMELINE:
                return [beat_tlui]
            else:
                raise ValueError

        def get_timeline_uis_mock(self, kind):
            return get_by_kind(kind)

        def ask_choose_timeline_mock(self, _1, _2, kind):
            return get_by_kind(kind)[0].timeline

        tlui_coll_path = "tilia.ui.timelines.collection.TimelineUICollection"
        with (
            patch(tlui_coll_path + ".get_timeline_uis_by_kind", get_timeline_uis_mock),
            patch(tlui_coll_path + ".ask_choose_timeline", ask_choose_timeline_mock),
            patch("tkinter.filedialog.askopenfilename", lambda **_: "dummy"),
        ):
            data = """time,label,comments\n10,marker,imported"""
            with (
                patch(
                    "tilia.ui.dialogs.by_time_or_by_measure.ByTimeOrByMeasure.ask",
                    lambda _: "time",
                ),
                patch("builtins.open", mock_open(read_data=data)),
            ):
                tkui.on_import_from_csv(TimelineKind.MARKER_TIMELINE)

                created_marker = marker_tlui.timeline.ordered_markers[0]
                assert created_marker.time == 10
                assert created_marker.label == "marker"
                assert created_marker.comments == "imported"

                marker_tlui.timeline.on_request_to_delete_components([created_marker])

            data = """measure,fraction,label,comments\n2,0.5,abc,def"""
            with (
                patch(
                    "tilia.ui.dialogs.by_time_or_by_measure.ByTimeOrByMeasure.ask",
                    lambda _: "measure",
                ),
                patch("builtins.open", mock_open(read_data=data)),
            ):
                beat_tlui.timeline.beat_pattern = [1]

                beat_tlui.create_beat(1)
                beat_tlui.create_beat(2)
                beat_tlui.create_beat(3)

                beat_tlui.timeline.recalculate_measures()

                tkui.on_import_from_csv(TimelineKind.MARKER_TIMELINE)

                created_marker = marker_tlui.timeline.ordered_markers[0]
                assert created_marker.time == 2.5
                assert created_marker.label == "abc"
                assert created_marker.comments == "def"

    def test_on_menu_import_hierarchies_from_csv(self, tkui, hierarchy_tlui, beat_tlui):
        def get_by_kind(kind):
            if kind == TimelineKind.HIERARCHY_TIMELINE:
                return [hierarchy_tlui]
            elif kind == TimelineKind.BEAT_TIMELINE:
                return [beat_tlui]
            else:
                raise ValueError

        def get_timeline_uis_mock(self, kind):
            return get_by_kind(kind)

        def ask_choose_timeline_mock(self, _1, _2, kind):
            return get_by_kind(kind)[0].timeline

        tlui_coll_path = "tilia.ui.timelines.collection.TimelineUICollection"
        with (
            patch(tlui_coll_path + ".get_timeline_uis_by_kind", get_timeline_uis_mock),
            patch(tlui_coll_path + ".ask_choose_timeline", ask_choose_timeline_mock),
            patch("tkinter.filedialog.askopenfilename", lambda **_: "dummy"),
        ):
            data = """start,end,level,label,comments\n10,20,1,hierarchy,imported"""
            with (
                patch(
                    "tilia.ui.dialogs.by_time_or_by_measure.ByTimeOrByMeasure.ask",
                    lambda _: "time",
                ),
                patch("builtins.open", mock_open(read_data=data)),
            ):
                tkui.on_import_from_csv(TimelineKind.HIERARCHY_TIMELINE)

                created = hierarchy_tlui.timeline.ordered_hierarchies[0]
                assert created.start == 10
                assert created.end == 20
                assert created.label == "hierarchy"
                assert created.comments == "imported"

                hierarchy_tlui.timeline.on_request_to_delete_components([created])

            data = (
                "start,start_fraction,end,end_fraction,level,label,comments\n"
                "1,0.5,2,0.1,1,mylabel,fromcsv"
            )
            with (
                patch(
                    "tilia.ui.dialogs.by_time_or_by_measure.ByTimeOrByMeasure.ask",
                    lambda _: "measure",
                ),
                patch("builtins.open", mock_open(read_data=data)),
            ):
                beat_tlui.timeline.beat_pattern = [1]

                beat_tlui.create_beat(1)
                beat_tlui.create_beat(2)
                beat_tlui.create_beat(3)

                beat_tlui.timeline.recalculate_measures()

                tkui.on_import_from_csv(TimelineKind.HIERARCHY_TIMELINE)

                created = hierarchy_tlui.timeline.ordered_hierarchies[0]
                assert created.start == 1.5
                assert created.end == 2.1
                assert created.label == "mylabel"
                assert created.comments == "fromcsv"

    def test_on_menu_import_markers_from_csv_displays_errors_during_creation(
        self, tkui, marker_tlui, beat_tlui
    ):
        def get_by_kind(kind):
            if kind == TimelineKind.MARKER_TIMELINE:
                return [marker_tlui]
            elif kind == TimelineKind.BEAT_TIMELINE:
                return [beat_tlui]
            else:
                raise ValueError

        def get_timeline_uis_mock(self, kind):
            return get_by_kind(kind)

        def ask_choose_timeline_mock(self, _1, _2, kind):
            return get_by_kind(kind)[0].timeline

        tlui_coll_path = "tilia.ui.timelines.collection.TimelineUICollection"
        with (
            patch(tlui_coll_path + ".get_timeline_uis_by_kind", get_timeline_uis_mock),
            patch(tlui_coll_path + ".ask_choose_timeline", ask_choose_timeline_mock),
            patch("tkinter.filedialog.askopenfilename", lambda **_: "dummy"),
            patch("tilia.events.post") as post_mock,
        ):
            data = "time,label,comments\n101,,\n102,,\n103,,"
            with (
                patch(
                    "tilia.ui.dialogs.by_time_or_by_measure.ByTimeOrByMeasure.ask",
                    lambda _: "time",
                ),
                patch("builtins.open", mock_open(read_data=data)),
            ):
                tkui.on_import_from_csv(TimelineKind.MARKER_TIMELINE)

                post_mock.assert_called_once()
                assert "101" in post_mock.call_args.args[2]
                assert "102" in post_mock.call_args.args[2]
                assert "103" in post_mock.call_args.args[2]

            data = """measure,fraction,label,comments\n999,0.5,,"""

            # TODO: refactor this mess of nested context managers
            with (
                patch(
                    "tilia.ui.dialogs.by_time_or_by_measure.ByTimeOrByMeasure.ask",
                    lambda _: "measure",
                ),
                patch("builtins.open", mock_open(read_data=data)),
                patch(
                    "tilia.ui.timelines.beat.timeline.BeatTimelineUI.on_beat_position_change"
                ),
                patch(
                    "tilia.ui.timelines.beat.timeline.BeatTimelineUI.on_timeline_component_deleted"
                ),
            ):
                beat_tlui.create_beat(1)
                tkui.on_import_from_csv(TimelineKind.MARKER_TIMELINE)

                assert "999" in post_mock.call_args.args[2]

                beat_tlui.timeline.clear()
                # as post was mocked, a ui was not created for the beat at 1, so
                # we need to clear the timeline manually to prevent a KeyError
                # during cleanup

    def test_on_menu_import_hierarchies_from_csv_displays_errors_during_creation(
        self, tkui, hierarchy_tlui, beat_tlui
    ):
        def get_by_kind(kind):
            if kind == TimelineKind.HIERARCHY_TIMELINE:
                return [hierarchy_tlui]
            elif kind == TimelineKind.BEAT_TIMELINE:
                return [beat_tlui]
            else:
                raise ValueError

        def get_timeline_uis_mock(self, kind):
            return get_by_kind(kind)

        def ask_choose_timeline_mock(self, _1, _2, kind):
            return get_by_kind(kind)[0].timeline

        tlui_coll_path = "tilia.ui.timelines.collection.TimelineUICollection"
        with (
            patch(tlui_coll_path + ".get_timeline_uis_by_kind", get_timeline_uis_mock),
            patch(tlui_coll_path + ".ask_choose_timeline", ask_choose_timeline_mock),
            patch("tkinter.filedialog.askopenfilename", lambda **_: "dummy"),
            patch("tilia.events.post") as post_mock,
        ):
            data = "start,end,level\n101,2,1\n102,2,1\n103,2,1"
            with (
                patch(
                    "tilia.ui.dialogs.by_time_or_by_measure.ByTimeOrByMeasure.ask",
                    lambda _: "time",
                ),
                patch("builtins.open", mock_open(read_data=data)),
            ):
                tkui.on_import_from_csv(TimelineKind.HIERARCHY_TIMELINE)

                post_mock.assert_called_once()
                assert "101" in post_mock.call_args.args[2]
                assert "102" in post_mock.call_args.args[2]
                assert "103" in post_mock.call_args.args[2]

            data = """start,start_fraction,end,level,label,comments\n999,0.5,2,1,,"""
            with (
                patch(
                    "tilia.ui.dialogs.by_time_or_by_measure.ByTimeOrByMeasure.ask",
                    lambda _: "measure",
                ),
                patch("builtins.open", mock_open(read_data=data)),
                patch(
                    "tilia.ui.timelines.beat.timeline.BeatTimelineUI.on_beat_position_change"
                ),
                patch(
                    "tilia.ui.timelines.beat.timeline.BeatTimelineUI.on_timeline_component_deleted"
                ),
            ):
                beat_tlui.create_beat(1)

                tkui.on_import_from_csv(TimelineKind.HIERARCHY_TIMELINE)

                assert "999" in post_mock.call_args.args[2]

                beat_tlui.timeline.clear()
                # as post was mocked, a ui was not created for the beat at 1, so
                # we need to clear the timeline manually to prevent a KeyError
                # during cleanup

    def test_on_display_error_crops_long_message(self, tkui):
        message = "\n".join(["." for _ in range(50)])  # 50 lines with a dot

        with patch("tkinter.messagebox.showerror") as showerror_mock:
            tkui.on_display_error("", message)

        assert showerror_mock.call_args.args[1].count("\n") == 35
