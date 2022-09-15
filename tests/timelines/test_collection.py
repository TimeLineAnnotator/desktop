from unittest.mock import MagicMock

from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.collection import TimelineCollection


class TestTimelineCollection:
    # TEST CONSTRUCTORS
    def test_constructor(self):
        TimelineCollection(MagicMock())

    def test_create_hierarchy_timeline(self):
        tl_collection = TimelineCollection(MagicMock())
        tl_collection.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        assert len(tl_collection._timelines) == 1

    # TEST SERIALIZER
    def test_serialize_timelines(self):
        tlcoll = TimelineCollection(MagicMock())
        tl1 = tlcoll.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl2 = tlcoll.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl3 = tlcoll.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        tl1.ui = MagicMock()
        tl2.ui = MagicMock()
        tl3.ui = MagicMock()

        serialized_tlcoll = tlcoll.serialize_timelines()

        for tl in [tl1, tl2, tl3]:
            assert tl.id in serialized_tlcoll

    def test_clear(self):
        tlcoll = TimelineCollection(MagicMock())
        tlcoll._timeline_ui_collection = MagicMock()
        tl2 = tlcoll.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl2.ui = MagicMock()

        tlcoll.clear()

        assert not tlcoll._timelines
