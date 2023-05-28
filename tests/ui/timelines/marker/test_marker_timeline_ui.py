from unittest.mock import patch

import pytest

from tilia import events, settings
from tilia.events import Event
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind as TlKind


class TestMarkerTimelineUI:
    @patch("tilia.ui.common.ask_for_color")
    def test_right_click_change_color(self, ask_for_color_mock, marker_tlui):
        ask_for_color_mock.return_value = "#000000"

        mrk, ui = marker_tlui.create_marker(time=0)

        marker_tlui.right_clicked_element = ui

        marker_tlui.right_click_menu_change_color()

        assert mrk.color == "#000000"

    @patch("tilia.ui.common.ask_for_color")
    def test_right_click_reset_color(self, ask_for_color_mock, marker_tlui):
        ask_for_color_mock.return_value = "#000000"

        mrk, ui = marker_tlui.create_marker(time=0)

        marker_tlui.right_clicked_element = ui

        marker_tlui.right_click_menu_change_color()
        marker_tlui.right_click_menu_reset_color()

        assert mrk.color == settings.get("marker_timeline", "marker_default_color")

    def test_on_add_marker_button(self, marker_tlui, tlui_clct):
        with patch(
            "tilia.ui.timelines.collection.TimelineUICollection.get_current_playback_time",
            lambda _: 0.101,
        ):
            events.post(Event.MARKER_TOOLBAR_BUTTON_ADD)

        assert len(marker_tlui.elements) == 1
        assert list(marker_tlui.elements)[0].time == 0.101

    def test_undo_redo_add_marker(self, marker_tlui, tlui_clct):
        events.post(Event.REQUEST_RECORD_STATE, Action.TEST_STATE)

        with patch(
            "tilia.ui.timelines.collection.TimelineUICollection.get_current_playback_time",
            lambda _: 0.101,
        ):
            tlui_clct.on_timeline_toolbar_button(TlKind.MARKER_TIMELINE, "add")

        events.post(Event.REQUEST_TO_UNDO)
        assert len(marker_tlui.elements) == 0

        events.post(Event.REQUEST_TO_REDO)
        assert len(marker_tlui.elements) == 1

    def test_on_delete_marker_button(self, marker_tlui):
        marker_tlui.create_marker(0)
        marker_tlui.select_element(list(marker_tlui.elements)[0])
        events.post(Event.MARKER_TOOLBAR_BUTTON_DELETE)

        assert len(marker_tlui.elements) == 0

    def test_on_delete_marker_button_multiple_markers(self, marker_tlui, tlui_clct):
        marker_tlui.create_marker(0)
        marker_tlui.create_marker(0.1)
        marker_tlui.create_marker(0.2)

        for marker_ui in list(marker_tlui.elements):
            marker_tlui.select_element(marker_ui)

        events.post(Event.MARKER_TOOLBAR_BUTTON_DELETE)

        assert len(marker_tlui.elements) == 0

    def test_undo_redo_delete_marker_multiple_markers(self, marker_tlui, tlui_clct):
        marker_tlui.create_marker(0)
        marker_tlui.create_marker(0.1)
        marker_tlui.create_marker(0.2)

        for marker_ui in list(marker_tlui.elements):
            marker_tlui.select_element(marker_ui)

        events.post(Event.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tlui_clct.on_timeline_toolbar_button(TlKind.MARKER_TIMELINE, "delete")

        events.post(Event.REQUEST_TO_UNDO)
        assert len(marker_tlui.elements) == 3

        events.post(Event.REQUEST_TO_REDO)
        assert len(marker_tlui.elements) == 0

    def test_undo_redo_delete_marker(self, marker_tlui, tlui_clct):
        # 'tlui_clct' is needed as it subscriber to toolbar event
        # and forwards it to marker timeline

        marker_tlui.create_marker(0)

        events.post(Event.REQUEST_RECORD_STATE, Action.TEST_STATE)

        marker_tlui.select_element(list(marker_tlui.elements)[0])
        tlui_clct.on_timeline_toolbar_button(TlKind.MARKER_TIMELINE, "delete")

        events.post(Event.REQUEST_TO_UNDO)
        assert len(marker_tlui.elements) == 1

        events.post(Event.REQUEST_TO_REDO)
        assert len(marker_tlui.elements) == 0
