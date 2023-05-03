from unittest.mock import patch

import pytest

from tilia.events import Event
from tilia.timelines.create import create_timeline
from tilia.timelines.timeline_kinds import TimelineKind


class TestTimelineCollection:
    def test_posts_timeline_kind_instanced_event(self, tl_clct, tlui_clct):
        with patch("tilia.timelines.collection.events") as events_mock:
            create_timeline(TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct)

            events_mock.post.assert_called_with(
                Event.TIMELINE_KIND_INSTANCED, TimelineKind.HIERARCHY_TIMELINE
            )

            create_timeline(TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct)

            create_timeline(TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct)

            events_mock.post.assert_called_once_with(
                Event.TIMELINE_KIND_INSTANCED, TimelineKind.HIERARCHY_TIMELINE
            )

        tl_clct.clear()

    def test_posts_timeline_kind_uninstanced_event(self, tl_clct, tlui_clct):
        with patch("tilia.timelines.collection.events") as events_mock:
            tl1 = create_timeline(TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct)

            tl2 = create_timeline(TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct)

            tl_clct.delete_timeline(tl1)

            with pytest.raises(AssertionError):
                events_mock.post.assert_called_with(
                    Event.TIMELINE_KIND_UNINSTANCED, TimelineKind.HIERARCHY_TIMELINE
                )

            tl_clct.delete_timeline(tl2)

            events_mock.post.assert_called_with(
                Event.TIMELINE_KIND_UNINSTANCED, TimelineKind.HIERARCHY_TIMELINE
            )
