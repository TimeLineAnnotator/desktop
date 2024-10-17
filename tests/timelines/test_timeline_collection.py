import pytest

from tests.mock import PatchPost
from tilia.requests import Post
from tilia.timelines import hash_timelines
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.dialogs.scale_or_crop import ScaleOrCrop
from unittest.mock import patch


class TestCreate:
    @pytest.mark.parametrize("kind", list(TimelineKind))
    def test_create(self, kind, tls):
        if kind == TimelineKind.PDF_TIMELINE:
            return
            # PDF timeline requires setup that's
            # hard to do here.
        assert tls.is_empty
        tls.create_timeline(kind)
        assert not tls.is_empty


class TestTimelines:
    def tests_scales_timelines_when_media_duration_changes(
        self, marker_tl, tilia_state, monkeypatch
    ):
        monkeypatch.setattr(
            "tilia.ui.dialogs.scale_or_crop.ScaleOrCrop.select",
            lambda *args: (True, ScaleOrCrop.ActionToTake.SCALE),
        )
        marker_tl.create_marker(10)
        tilia_state.duration = 200
        assert marker_tl[0].get_data("time") == 20

    def tests_crops_timelines_when_media_duration_changes(
        self, marker_tl, tilia_state, monkeypatch
    ):
        monkeypatch.setattr(
            "tilia.ui.dialogs.scale_or_crop.ScaleOrCrop.select",
            lambda *args: (True, ScaleOrCrop.ActionToTake.CROP),
        )
        marker_tl.create_marker(10)
        tilia_state.duration = 200
        assert marker_tl[0].get_data("time") == 10

    def test_scale_timeline_is_not_offered_when_there_is_only_a_slider_timeline(
        self, tilia_state
    ):
        with patch("tilia.ui.dialogs.scale_or_crop.ScaleOrCrop.select") as mock:
            tilia_state.duration = 50
        assert not mock.called

    def test_crops_timeline_when_media_duration_changes_if_user_confirms(
        self, marker_tl, tilia_state, monkeypatch
    ):
        monkeypatch.setattr(
            "tilia.ui.dialogs.scale_or_crop.ScaleOrCrop.select",
            lambda *args: (True, ScaleOrCrop.ActionToTake.CROP),
        )
        marker_tl.create_marker(100)
        marker_tl.create_marker(50)
        tilia_state.duration = 50
        assert marker_tl[0].get_data("time") == 50
        assert len(marker_tl) == 1

    def test_posts_timeline_kind_instanced_event(self, tls):
        with PatchPost(
            "tilia.timelines.collection.collection", Post.TIMELINE_KIND_INSTANCED
        ) as post_mock:
            tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

            post_mock.assert_called_with(
                Post.TIMELINE_KIND_INSTANCED, TimelineKind.HIERARCHY_TIMELINE
            )

            tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
            tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

            post_mock.assert_called_once_with(
                Post.TIMELINE_KIND_INSTANCED, TimelineKind.HIERARCHY_TIMELINE
            )

        tls.clear()

    def test_posts_timeline_kind_uninstanced_event(self, tls):
        with PatchPost(
            "tilia.timelines.collection.collection", Post.TIMELINE_KIND_NOT_INSTANCED
        ) as post_mock:
            tl1 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
            tl2 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

            tls.delete_timeline(tl1)

            with pytest.raises(AssertionError):
                post_mock.assert_called_with(
                    Post.TIMELINE_KIND_NOT_INSTANCED, TimelineKind.HIERARCHY_TIMELINE
                )

            tls.delete_timeline(tl2)

            post_mock.assert_called_with(
                Post.TIMELINE_KIND_NOT_INSTANCED, TimelineKind.HIERARCHY_TIMELINE
            )

    def test_serve_ordinal_for_new_timeline(self, tls):
        assert tls.serve_ordinal_for_new_timeline() == 1
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        assert tls.serve_ordinal_for_new_timeline() == 2
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
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
                "kind": TimelineKind.HIERARCHY_TIMELINE,
            },
            1: {
                "height": 220,
                "is_visible": True,
                "name": "test2",
                "display_position": 1,
                "components": {},
                "kind": TimelineKind.MARKER_TIMELINE,
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
        tl1 = tls.create_timeline(TimelineKind.SLIDER_TIMELINE)
        tl2 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl3 = tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        tl4 = tls.create_timeline(TimelineKind.BEAT_TIMELINE, beat_pattern=[2])

        serialized = tls.serialize_timelines()

        assert serialized[tl1.id]["ordinal"] == 1
        assert serialized[tl1.id]["kind"] == "SLIDER_TIMELINE"
        assert serialized[tl2.id]["ordinal"] == 2
        assert serialized[tl2.id]["kind"] == "HIERARCHY_TIMELINE"
        assert serialized[tl3.id]["ordinal"] == 3
        assert serialized[tl3.id]["kind"] == "MARKER_TIMELINE"
        assert serialized[tl4.id]["ordinal"] == 4
        assert serialized[tl4.id]["kind"] == "BEAT_TIMELINE"

    def test_hash_timelines(self, tls):
        tls.create_timeline(TimelineKind.SLIDER_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        tls.create_timeline(TimelineKind.BEAT_TIMELINE, beat_pattern=[2])

        # assert that no error is raised
        hash_timelines.hash_timeline_collection_data(tls.serialize_timelines())

    def test_delete_timeline_updates_ordinals_correctly(self, tls):
        tl1 = tls.create_timeline(TimelineKind.SLIDER_TIMELINE)
        tl2 = tls.create_timeline(TimelineKind.SLIDER_TIMELINE)
        tl3 = tls.create_timeline(TimelineKind.SLIDER_TIMELINE)
        tl4 = tls.create_timeline(TimelineKind.SLIDER_TIMELINE)
        tl5 = tls.create_timeline(TimelineKind.SLIDER_TIMELINE)

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
