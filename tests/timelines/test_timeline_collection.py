import pytest

from tests.mock import PatchPost
from tilia.requests import Post
from tilia.timelines import hash_timelines
from tilia.timelines.timeline_kinds import TimelineKind


class TestTimelines:
    def test_posts_timeline_kind_instanced_event(self, tkui, tls):
        with PatchPost(
            "tilia.timelines.collection", Post.TIMELINE_KIND_INSTANCED
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

        tkui._on_timeline_kind_instanced(TimelineKind.HIERARCHY_TIMELINE)

        tls.clear()

    def test_posts_timeline_kind_uninstanced_event(self, tls):
        with PatchPost(
            "tilia.timelines.collection", Post.TIMELINE_KIND_UNINSTANCED
        ) as post_mock:
            tl1 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
            tl2 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

            tls.delete_timeline(tl1)

            with pytest.raises(AssertionError):
                post_mock.assert_called_with(
                    Post.TIMELINE_KIND_UNINSTANCED, TimelineKind.HIERARCHY_TIMELINE
                )

            tls.delete_timeline(tl2)

            post_mock.assert_called_with(
                Post.TIMELINE_KIND_UNINSTANCED, TimelineKind.HIERARCHY_TIMELINE
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

    def test_swap_timeline_order(self, tls):
        tl1 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl2 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        with PatchPost(
            "tilia.timelines.collection", Post.TIMELINE_ORDER_SWAPPED
        ) as post_mock:
            tls.swap_timeline_order(tl1, tl2)

        assert tl1.ordinal == 2
        assert tl2.ordinal == 1

        # The order doesn't matter for the function, but it does for the assertion,
        # which is not ideal.
        post_mock.assert_called_with(Post.TIMELINE_ORDER_SWAPPED, tl1.id, tl2.id)

    def test_move_up_in_order(self, tls):
        tl1 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl2 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        tls.on_move_up_in_order(tl2.id)

        assert tl2.ordinal == 1
        assert tl1.ordinal == 2

    def test_move_down_in_order(self, tls):
        tl1 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl2 = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        tls.on_move_down_in_order(tl1.id)

        assert tl2.ordinal == 1
        assert tl1.ordinal == 2

    def test_deserialize_timelines_with_display_position(self, tls):
        """
        'display_position' was modified and renamed to 'ordinal'.
        Loading should still work for backwards compatibility.
        """
        data = {
            0: {
                "height": 220,
                "is_visible": True,
                "name": "test1",
                "display_position": 0,
                "components": {},
                "kind": "HIERARCHY_TIMELINE",
            },
            1: {
                "height": 220,
                "is_visible": True,
                "name": "test2",
                "display_position": 1,
                "components": {},
                "kind": "MARKER_TIMELINE",
            },
        }

        # can't call tls.deserialize_data or two ask_for_user_name arguments
        # would be passed
        for tl_data in data.values():
            tls.create_timeline(**tl_data)

        # check if ordinal property was created
        assert tls.get_timeline_by_attr("ordinal", 1).name == "test1"
        assert tls.get_timeline_by_attr("ordinal", 2).name == "test2"

        # ensure that display_position propoerty was not created
        with pytest.raises(AttributeError):
            _ = tls.get_timeline_by_attr("ordinall", 1).display_position
        with pytest.raises(AttributeError):
            _ = tls.get_timeline_by_attr("ordinall", 2).display_position

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


