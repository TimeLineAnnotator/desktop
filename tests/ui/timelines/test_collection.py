from unittest.mock import patch

import pytest

from tilia import events
from tilia.events import Event
from tilia.timelines.create import create_timeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI
from tilia.ui.timelines.slider import SliderTimelineUI


class TestTimelineUICollection:
    def test_create_timeline_ui_hierarchy_timeline(self, tl_clct, tlui_clct):

        tlui = create_timeline(
            TlKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        assert tlui.__class__ == HierarchyTimelineUI
        assert tlui in tlui_clct._timeline_uis
        assert tlui_clct._select_order[0] == tlui

        tl_clct.delete_timeline(tlui.timeline)

    def test_create_timeline_ui_slider_timeline(self, tl_clct, tlui_clct):
        tlui = create_timeline(
            TlKind.SLIDER_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        assert tlui.__class__ == SliderTimelineUI
        assert tlui in tlui_clct._timeline_uis
        assert tlui_clct._select_order[0] == tlui

        tl_clct.delete_timeline(tlui.timeline)

    def test_create_two_timeline_uis(self, tl_clct, tlui_clct):
        tlui1 = create_timeline(
            TlKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        tlui2 = create_timeline(
            TlKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        assert tlui1 in tlui_clct._timeline_uis
        assert tlui2 in tlui_clct._timeline_uis
        assert tlui_clct._select_order[0] == tlui2

        tl_clct.delete_timeline(tlui1.timeline)
        tl_clct.delete_timeline(tlui2.timeline)

    def test_delete_timeline_ui(self, tl_clct, tlui_clct):

        tlui = create_timeline(
            TlKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test"
        ).ui

        tl_clct.delete_timeline(tlui.timeline)

        assert not tlui_clct._timeline_uis
        assert not tlui_clct._select_order
        assert not tlui_clct._display_order

    def test_update_select_order(self, tl_clct, tlui_clct):

        tlui1 = create_timeline(
            TlKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test1"
        ).ui

        tlui2 = create_timeline(
            TlKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct, name="test2"
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

    def test_on_timeline_toolbar_button(self, tlui_clct):

        for kind in tlui_clct.tlkind_to_action_to_call_type:
            for button, call_type in tlui_clct.tlkind_to_action_to_call_type[
                kind
            ].items():
                with (
                    patch(
                        "tilia.ui.timelines.collection.TimelineUICollection.timeline_toolbar_button_call_on_all"
                    ) as call_on_all_mock,
                    patch(
                        "tilia.ui.timelines.collection.TimelineUICollection.timeline_toolbar_button_call_on_first"
                    ) as call_on_first_mock,
                    patch(
                        "tilia.ui.timelines.collection.TimelineUICollection.timeline_toolbar_button_record"
                    ) as record_mock,
                ):
                    tlui_clct.on_timeline_toolbar_button(kind, button)
                if call_type == "all":
                    call_on_all_mock.assert_called_with(kind, button)
                else:
                    call_on_first_mock.assert_called_with(kind, button)

                record_mock.assert_called_with(button)
