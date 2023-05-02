from unittest.mock import patch

import pytest

from tilia import events
from tilia.events import Event
from tilia.timelines.create import create_timeline
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import (
    TimelineKind as TlKind,
    IMPLEMENTED_TIMELINE_KINDS,
)
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

    def test_crete_timeline_uis_of_all_kinds(self, tl_clct, tlui_clct):
        for kind in IMPLEMENTED_TIMELINE_KINDS:
            with patch(
                "tilia.ui.timelines.collection.TimelineUICollection.ask_beat_pattern"
            ) as mock:
                mock.return_value = [1]
                create_timeline(kind, tl_clct, tlui_clct)

        assert len(tlui_clct.get_timeline_uis()) == len(IMPLEMENTED_TIMELINE_KINDS)

        for timeline in tl_clct._timelines.copy():
            tl_clct.delete_timeline(timeline)

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

    def test_on_delete_button(self, tlui_clct, beat_tlui, hierarchy_tlui, marker_tlui):
        marker = marker_tlui.create_marker(0)
        marker_tlui.select_element(marker.ui)
        hierarchy = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(hierarchy.ui)
        beat = beat_tlui.create_beat(0)
        beat_tlui.select_element(beat.ui)

        tlui_clct._on_delete_press()

        assert not marker_tlui.elements
        assert not hierarchy_tlui.elements
        assert not beat_tlui.elements

    def test_undo_redo_delete_button(
        self, tlui_clct, beat_tlui, hierarchy_tlui, marker_tlui
    ):
        marker = marker_tlui.create_marker(0)
        marker_tlui.select_element(marker.ui)
        hierarchy = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(hierarchy.ui)
        beat = beat_tlui.create_beat(0)
        beat_tlui.select_element(beat.ui)

        events.post(Event.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tlui_clct._on_delete_press()

        events.post(Event.REQUEST_TO_UNDO)
        assert len(marker_tlui.elements) == 1
        assert len(hierarchy_tlui.elements) == 1
        assert len(beat_tlui.elements) == 1

        events.post(Event.REQUEST_TO_REDO)
        assert not marker_tlui.elements
        assert not hierarchy_tlui.elements
        assert not beat_tlui.elements

    def test_ask_choose_timeline(
        self, tlui_clct, beat_tlui, hierarchy_tlui, marker_tlui
    ):
        with patch("tilia.ui.timelines.collection.ChooseDialog.ask", lambda _: 0):
            assert tlui_clct.ask_choose_timeline("", "") == beat_tlui.timeline

        with patch("tilia.ui.timelines.collection.ChooseDialog.ask", lambda _: 1):
            assert tlui_clct.ask_choose_timeline("", "") == hierarchy_tlui.timeline

        with patch("tilia.ui.timelines.collection.ChooseDialog.ask", lambda _: 2):
            assert tlui_clct.ask_choose_timeline("", "") == marker_tlui.timeline

    def test_ask_choose_timeline_restrict_kind(
        self, tkui, tlui_clct, beat_tlui, hierarchy_tlui, marker_tlui
    ):
        with (
            patch("tilia.ui.timelines.collection.ChooseDialog") as choose_window_mock,
        ):

            class ChooseWindowDummy:
                call_count = 0

                def ask(self):
                    """
                    ChooseDialog.ask must return the display_position of
                    'hierarchy_tlui' and 'marker_tlui', respectively.
                    That is, 1 and 2.
                    """
                    self.call_count += 1
                    return self.call_count

            choose_window_mock.return_value = ChooseWindowDummy()

            tlui_clct.ask_choose_timeline("title", "prompt", TlKind.HIERARCHY_TIMELINE)

            choose_window_mock.assert_called_with(
                tkui.root, "title", "prompt", [(1, str(hierarchy_tlui))]
            )

            tlui_clct.ask_choose_timeline("title", "prompt", TlKind.MARKER_TIMELINE)

            choose_window_mock.assert_called_with(
                tkui.root, "title", "prompt", [(2, str(marker_tlui))]
            )

    def test_import_markers_by_time_from_csv(self, tlui_clct, beat_tlui, marker_tlui):
        pass

    def test_import_markers_by_measure_from_csv(
        self, tlui_clct, beat_tlui, marker_tlui
    ):
        pass
