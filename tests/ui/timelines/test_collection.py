from unittest.mock import patch

import pytest

from tilia import events
from tilia.events import Event
from tilia.timelines.create import create_timeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI
from tilia.ui.timelines.slider import SliderTimelineUI


class TestTimelineUICollection:
    def test_create_timeline_ui_hierarchy_timeline(self, tl_clct, tlui_clct):

        tlui = create_timeline(
            TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        assert tlui.__class__ == HierarchyTimelineUI
        assert tlui in tlui_clct._timeline_uis
        assert tlui_clct._select_order[0] == tlui

        tl_clct.delete_timeline(tlui.timeline)

    def test_create_timeline_ui_slider_timeline(self, tl_clct, tlui_clct):
        tlui = create_timeline(
            TimelineKind.SLIDER_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        assert tlui.__class__ == SliderTimelineUI
        assert tlui in tlui_clct._timeline_uis
        assert tlui_clct._select_order[0] == tlui

        tl_clct.delete_timeline(tlui.timeline)

    def test_create_two_timeline_uis(self, tl_clct, tlui_clct):
        tlui1 = create_timeline(
            TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        tlui2 = create_timeline(
            TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        assert tlui1 in tlui_clct._timeline_uis
        assert tlui2 in tlui_clct._timeline_uis
        assert tlui_clct._select_order[0] == tlui2

        tl_clct.delete_timeline(tlui1.timeline)
        tl_clct.delete_timeline(tlui2.timeline)

    def test_delete_timeline_ui(self, tl_clct, tlui_clct):

        tlui = create_timeline(
            TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        tl_clct.delete_timeline(tlui.timeline)

        assert not tlui_clct._timeline_uis
        assert not tlui_clct._select_order
        assert not tlui_clct._display_order

    def test_update_select_order(self, tl_clct, tlui_clct):

        tlui1 = create_timeline(
            TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test1"
        ).ui

        tlui2 = create_timeline(
            TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test2"
        ).ui

        assert tlui_clct._select_order[0] == tlui2

        with patch("tilia.ui.timelines.collection.SelectionBox", lambda *_: None):
            events.post(
                Event.CANVAS_LEFT_CLICK, tlui1.canvas, 0, 0, 0, None, double=False
            )

        assert tlui_clct._select_order[0] == tlui1

        with patch("tilia.ui.timelines.collection.SelectionBox", lambda *_: None):
            events.post(
                Event.CANVAS_LEFT_CLICK, tlui2.canvas, 0, 0, 0, None, double=False
            )

        assert tlui_clct._select_order[0] == tlui2

        tl_clct.delete_timeline(tlui1.timeline)
        tl_clct.delete_timeline(tlui2.timeline)
