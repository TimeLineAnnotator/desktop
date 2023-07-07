import pytest
from unittest.mock import patch, mock_open

from tests.mock import PatchGet, PatchPost
from tilia.requests import post, Post, Get
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.menus import DynamicMenu
from tilia.ui.timelines.collection import TimelineUIs
from tilia.ui.windows import WindowKind


class TiliaDummy:
    def __init__(self):
        self.media_length = 99
        self.media_metadata = {"title": "test"}

    @property
    def media_path(self):
        return "test_path"


@pytest.fixture
def import_from_csv_patched_environment(marker_tlui, beat_tlui, hierarchy_tlui):
    """
    Patches the following functions:
        - TimelineUIs.ask_choose_timeline
        - TimelineUIs.get (for Get.TILIA_FILE_PATH_FROM_USER)
    """

    def ask_choose_timeline_mock(_1, _2, _3, kind):
        if kind == TimelineKind.MARKER_TIMELINE:
            return marker_tlui.timeline
        elif kind == TimelineKind.BEAT_TIMELINE:
            return beat_tlui.timeline
        elif kind == TimelineKind.HIERARCHY_TIMELINE:
            return hierarchy_tlui.timeline
        else:
            raise ValueError

    with (
        patch(
            "tilia.ui.timelines.collection.TimelineUIs.ask_choose_timeline",
            ask_choose_timeline_mock
        ),
    ):
        with PatchGet(
            "tilia.ui.tkinterui", Get.FILE_PATH_FROM_USER, "****"
        ):  # can't be empty or import will abort
            yield


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
    def test_on_request_window_media_metadata(self, window_mock, tkui):
        with PatchGet("tilia.ui.windows.metadata", Get.MEDIA_DURATION, 100):
            tkui.on_request_window(WindowKind.MEDIA_METADATA)
        assert window_mock.called

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

    @pytest.mark.parametrize("tlkind", [e.name for e in DynamicMenu])
    def test_on_timeline_kind_instanced(self, tlkind, tkui):
        assert not tkui.enabled_dynamic_menus

        tkui._on_timeline_kind_instanced(TimelineKind[tlkind])

        assert tkui.enabled_dynamic_menus == {DynamicMenu[tlkind]}

        tkui._on_timeline_kind_instanced(TimelineKind[tlkind])
        tkui._on_timeline_kind_instanced(TimelineKind[tlkind])

        assert tkui.enabled_dynamic_menus == {DynamicMenu[tlkind]}

        # cleanup
        tkui.enabled_dynamic_menus = set()

    @pytest.mark.parametrize("tlkind", DynamicMenu)
    def test_on_timeline_kind_uninstanced(self, tlkind, tkui):
        tkui._on_timeline_kind_instanced(tlkind)
        tkui._on_timeline_kind_uninstanced(tlkind)
        assert tkui.enabled_dynamic_menus == set()

    BY_TIME_OR_MEASURE_PATCH_TARGET = (
        "tilia.ui.dialogs.by_time_or_by_measure.ByTimeOrByMeasure.ask"
    )

    def test_on_menu_import_markers_from_csv_by_time(
        self, tkui, marker_tlui, import_from_csv_patched_environment
    ):
        data = """time,label,comments\n10,marker,imported"""
        with (
            patch(
                self.BY_TIME_OR_MEASURE_PATCH_TARGET,
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

    def test_on_menu_import_markers_from_csv_by_measure(
        self, tkui, marker_tlui, beat_tlui, import_from_csv_patched_environment
    ):
        data = """measure,fraction,label,comments\n2,0.5,abc,def"""
        with (
            patch(
                self.BY_TIME_OR_MEASURE_PATCH_TARGET,
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

    def test_on_menu_import_hierarchies_from_csv_by_time(
        self, tkui, beat_tlui, hierarchy_tlui, import_from_csv_patched_environment
    ):
        data = """start,end,level,label,comments\n10,20,1,hierarchy,imported"""
        with (
            patch(self.BY_TIME_OR_MEASURE_PATCH_TARGET, lambda _: "time"),
            patch("builtins.open", mock_open(read_data=data)),
        ):
            tkui.on_import_from_csv(TimelineKind.HIERARCHY_TIMELINE)

            created = hierarchy_tlui.timeline.ordered_hierarchies[0]
            assert created.start == 10
            assert created.end == 20
            assert created.label == "hierarchy"
            assert created.comments == "imported"

            hierarchy_tlui.timeline.on_request_to_delete_components([created])

    def test_on_menu_import_hierarchies_from_csv_by_measure(
        self, tkui, beat_tlui, hierarchy_tlui, import_from_csv_patched_environment
    ):
        data = (
            "start,start_fraction,end,end_fraction,level,label,comments\n"
            "1,0.5,2,0.1,1,mylabel,fromcsv"
        )
        with (
            patch(self.BY_TIME_OR_MEASURE_PATCH_TARGET, lambda _: "measure"),
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

    def test_on_menu_import_markers_from_csv_shows_out_of_bounds_errors_during_creation(
        self, tkui, import_from_csv_patched_environment
    ):
        data = "time,label,comments\n101,,\n102,,\n103,,"
        with (
            patch(self.BY_TIME_OR_MEASURE_PATCH_TARGET, lambda _: "time"),
            patch("builtins.open", mock_open(read_data=data)),
        ):
            with PatchPost(
                "tilia.ui.tkinterui", Post.REQUEST_DISPLAY_ERROR
            ) as post_mock:
                tkui.on_import_from_csv(TimelineKind.MARKER_TIMELINE)

                post_mock.assert_called_once()
                assert "101" in post_mock.call_args.args[2]
                assert "102" in post_mock.call_args.args[2]
                assert "103" in post_mock.call_args.args[2]

    def test_on_menu_import_markers_from_csv_shows_no_measure_errors_during_creation(
        self,
        tkui,
        beat_tlui,
        import_from_csv_patched_environment,
    ):
        data = """measure,fraction,label,comments\n999,0.5,,"""
        BEAT_TLUI_MODULE = "tilia.ui.timelines.beat.timeline.BeatTimelineUI"
        with (
            patch(
                self.BY_TIME_OR_MEASURE_PATCH_TARGET,
                lambda _: "measure",
            ),
            patch("builtins.open", mock_open(read_data=data)),
            patch(f"{BEAT_TLUI_MODULE}.on_beat_position_change"),
            patch(f"{BEAT_TLUI_MODULE}.on_timeline_component_deleted"),
        ):
            with PatchPost(
                "tilia.ui.tkinterui", Post.REQUEST_DISPLAY_ERROR
            ) as post_mock:
                beat_tlui.create_beat(1)
                tkui.on_import_from_csv(TimelineKind.MARKER_TIMELINE)

                assert "999" in post_mock.call_args.args[2]

    def test_on_menu_import_hierarchies_from_csv_shows_hierarchy_out_of_bounds_errors(
        self, tkui, import_from_csv_patched_environment
    ):
        data = "start,end,level\n101,2,1\n102,2,1\n103,2,1"
        with (
            patch(self.BY_TIME_OR_MEASURE_PATCH_TARGET, lambda _: "time"),
            patch("builtins.open", mock_open(read_data=data)),
        ):
            with PatchPost(
                "tilia.ui.tkinterui", Post.REQUEST_DISPLAY_ERROR
            ) as post_mock:
                tkui.on_import_from_csv(TimelineKind.HIERARCHY_TIMELINE)

                post_mock.assert_called_once()
                assert "101" in post_mock.call_args.args[2]
                assert "102" in post_mock.call_args.args[2]
                assert "103" in post_mock.call_args.args[2]

    def test_on_menu_import_hierarchies_from_csv_displays_create_hierarchy_errors_measure_not_found(  # noqa: E501
        self, tkui, beat_tlui, import_from_csv_patched_environment
    ):
        data = """start,start_fraction,end,level,label,comments\n999,0.5,2,1,,"""
        BEAT_TLUI_MODULE = "tilia.ui.timelines.beat.timeline.BeatTimelineUI"
        with (
            patch(
                self.BY_TIME_OR_MEASURE_PATCH_TARGET,
                lambda _: "measure",
            ),
            patch("builtins.open", mock_open(read_data=data)),
            patch(f"{BEAT_TLUI_MODULE}.on_beat_position_change"),
            patch(f"{BEAT_TLUI_MODULE}.on_timeline_component_deleted"),
        ):
            with PatchPost(
                "tilia.ui.tkinterui", Post.REQUEST_DISPLAY_ERROR
            ) as post_mock:
                beat_tlui.create_beat(1)

                tkui.on_import_from_csv(TimelineKind.HIERARCHY_TIMELINE)

                assert "999" in post_mock.call_args.args[2]

    def test_on_display_error_crops_long_message(self, tkui):
        message = "\n".join(["." for _ in range(50)])  # 50 lines with a dot each

        with patch("tkinter.messagebox.showerror") as showerror_mock:
            post(Post.REQUEST_DISPLAY_ERROR, "", message)

        assert showerror_mock.call_args.args[1].count("\n") == 35

    def test_on_menu_import_beats_from_csv(
        self, tkui, beat_tlui, import_from_csv_patched_environment
    ):
        data = "time\n5\n10\n15\n20"
        with (patch("builtins.open", mock_open(read_data=data)),):
            tkui.on_import_from_csv(TimelineKind.BEAT_TIMELINE)

            beats = sorted(beat_tlui.timeline.components)
            assert beats[0].time == 5
            assert beats[1].time == 10
            assert beats[2].time == 15
            assert beats[3].time == 20
