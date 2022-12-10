import itertools
from unittest.mock import MagicMock, PropertyMock

import pytest

from tilia import events
from tilia.events import unsubscribe_from_all, Event
from tilia.timelines.hierarchy.timeline import HierarchyTimeline, HierarchyTLComponentManager
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.collection import TimelineCollection


@pytest.fixture
def tl_coll():
    _tl_coll = TimelineCollection(MagicMock())
    yield _tl_coll
    unsubscribe_from_all(_tl_coll)

class TestTimelineCollection:
    # TEST CONSTRUCTORS
    def test_constructor(self):
        TimelineCollection(MagicMock())

    def test_create_hierarchy_timeline(self, tl_coll):
        tl_coll = TimelineCollection(MagicMock())
        tl_coll.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        assert len(tl_coll._timelines) == 1

    # TEST SERIALIZER
    def test_serialize_timelines(self, tl_coll):
        tl1 = tl_coll.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl2 = tl_coll.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl3 = tl_coll.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        tl1.ui = MagicMock()
        tl2.ui = MagicMock()
        tl3.ui = MagicMock()

        serialized_tlcoll = tl_coll.serialize_timelines()

        for tl in [tl1, tl2, tl3]:
            assert tl.id in serialized_tlcoll

    def test_clear(self, tl_coll):
        tl_coll._timeline_ui_collection = MagicMock()
        tl2 = tl_coll.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tl2.ui = MagicMock()

        tl_coll.clear()

        assert not tl_coll._timelines




