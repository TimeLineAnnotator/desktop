import pytest

from tests.mock import PatchPost, Serve, ServeSequence, patch_yes_or_no_dialog
from tilia.requests import Get, Post
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.pdf.timeline import PdfTimeline
from tilia.timelines.slider.timeline import SliderTimeline


class TestCreate:
    @pytest.mark.parametrize("kind", Timeline.subclasses())
    def test_create(self, kind, tls):
        if kind == PdfTimeline:
            return
            # PDF timeline requires setup that's
            # hard to do here.
        assert tls.is_empty
        tls.create_timeline(kind)
        assert not tls.is_empty


class TestTimelines:
    def tests_scales_timelines_when_media_duration_changes(
        self, marker_tl, tilia_state, tluis  # needed for patch_yes_or_no
    ):
        marker_tl.create_marker(10)
        with patch_yes_or_no_dialog(True):
            tilia_state.duration = 200
        assert marker_tl[0].get_data("time") == 20

    def tests_does_not_scale_timelines_when_media_duration_changes_if_user_refuses(
        self, marker_tl, tilia_state, tluis  # needed for patch_yes_or_no
    ):
        marker_tl.create_marker(10)
        with patch_yes_or_no_dialog(False):
            tilia_state.duration = 200
        assert marker_tl[0].get_data("time") == 10

    def test_scale_timeline_when_media_duration_changes_if_user_refuses_crop(
        self, marker_tlui, tilia_state, tluis  # needed for patch_yes_or_no
    ):
        marker_tlui.create_marker(90)
        with ServeSequence(Get.FROM_USER_YES_OR_NO, [False, False]):
            tilia_state.duration = 50
        assert marker_tlui[0].get_data("time") == 45

    def test_scale_timeline_is_not_offered_when_there_is_only_a_slider_timeline(
        self, slider_tl, tilia_state
    ):
        with Serve(Get.FROM_USER_YES_OR_NO, None) as serve:
            tilia_state.duration = 50
        assert not serve.called

    def test_crops_timeline_when_media_duration_changes_if_user_confirms(
        self, marker_tl, tilia_state
    ):
        marker_tl.create_marker(100)
        marker_tl.create_marker(50)
        with ServeSequence(Get.FROM_USER_YES_OR_NO, [False, True]):
            tilia_state.duration = 50
        assert marker_tl[0].get_data("time") == 50
        assert len(marker_tl) == 1

    def test_posts_timeline_type_instanced_event(self, qtui, tls):
        with PatchPost(
            "tilia.timelines.collection.collection", Post.TIMELINE_TYPE_INSTANCED
        ) as post_mock:
            tls.create_timeline(HierarchyTimeline)

            post_mock.assert_called_with(
                Post.TIMELINE_TYPE_INSTANCED, HierarchyTimeline
            )

            tls.create_timeline(HierarchyTimeline)
            tls.create_timeline(HierarchyTimeline)

            post_mock.assert_called_once_with(
                Post.TIMELINE_TYPE_INSTANCED, HierarchyTimeline
            )

        tls.clear()

    def test_posts_timeline_type_uninstanced_event(self, tls):
        with PatchPost(
            "tilia.timelines.collection.collection", Post.TIMELINE_TYPE_NOT_INSTANCED
        ) as post_mock:
            tl1 = tls.create_timeline(HierarchyTimeline)
            tl2 = tls.create_timeline(HierarchyTimeline)

            tls.delete_timeline(tl1)

            with pytest.raises(AssertionError):
                post_mock.assert_called_with(
                    Post.TIMELINE_TYPE_NOT_INSTANCED, HierarchyTimeline
                )

            tls.delete_timeline(tl2)

            post_mock.assert_called_with(
                Post.TIMELINE_TYPE_NOT_INSTANCED, HierarchyTimeline
            )

    def test_serve_ordinal_for_new_timeline(self, tls):
        assert tls.serve_ordinal_for_new_timeline() == 1
        tls.create_timeline(HierarchyTimeline)
        assert tls.serve_ordinal_for_new_timeline() == 2
        tls.create_timeline(HierarchyTimeline)
        assert tls.serve_ordinal_for_new_timeline() == 3
        tls.delete_timeline(tls[0])
        assert tls.serve_ordinal_for_new_timeline() == 2
        tls.delete_timeline(tls[0])
        assert tls.serve_ordinal_for_new_timeline() == 1

    def test_deserialize_timelines_with_display_position(self, tls):
        data = {
            0: {
                "height": 220,
                "is_visible": True,
                "name": "test1",
                "display_position": 0,
                "components": {},
                "kind": "Hierarchy",
            },
            1: {
                "height": 220,
                "is_visible": True,
                "name": "test2",
                "display_position": 1,
                "components": {},
                "kind": "Marker",
            },
        }

        tls.deserialize_timelines(data)

        # assert timelines where created in right order
        assert tls[0].name == "test1"
        assert tls[1].name == "test2"

        # assert ordinal property has been set
        assert tls[0].ordinal == 1
        assert tls[1].ordinal == 2

        # assert display_position attribute was not created
        assert not hasattr(tls[0], "display_position")
        assert not hasattr(tls[1], "display_position")

    def test_serialize_timelines_serializes_ordinals(self, tls):
        tl1 = tls.create_timeline(SliderTimeline)
        tl2 = tls.create_timeline(HierarchyTimeline)
        tl3 = tls.create_timeline(MarkerTimeline)
        tl4 = tls.create_timeline(BeatTimeline, beat_pattern=[2])

        serialized = tls.serialize_timelines()[0]

        assert serialized[tl1.id]["ordinal"] == 1
        assert serialized[tl1.id]["kind"] == "Slider"
        assert serialized[tl2.id]["ordinal"] == 2
        assert serialized[tl2.id]["kind"] == "Hierarchy"
        assert serialized[tl3.id]["ordinal"] == 3
        assert serialized[tl3.id]["kind"] == "Marker"
        assert serialized[tl4.id]["ordinal"] == 4
        assert serialized[tl4.id]["kind"] == "Beat"

    def test_delete_timeline_updates_ordinals_correctly(self, tls):
        tl1 = tls.create_timeline(SliderTimeline)
        tl2 = tls.create_timeline(SliderTimeline)
        tl3 = tls.create_timeline(SliderTimeline)
        tl4 = tls.create_timeline(SliderTimeline)
        tl5 = tls.create_timeline(SliderTimeline)

        tls.delete_timeline(tl2)

        assert tl1.ordinal == 1
        assert tl3.ordinal == 2
        assert tl4.ordinal == 3
        assert tl5.ordinal == 4

        tls.delete_timeline(tl5)

        assert tl1.ordinal == 1
        assert tl3.ordinal == 2
        assert tl4.ordinal == 3

        tls.delete_timeline(tl1)

        assert tl3.ordinal == 1
        assert tl4.ordinal == 2
