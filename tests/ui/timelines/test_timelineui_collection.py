from unittest.mock import patch

from tests.mock import PatchGet
from tilia.requests import Post, post
from tilia.requests import Get
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import (
    TimelineKind as TlKind,
    TimelineKind,
)
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI
from tilia.ui.timelines.slider import SliderTimelineUI


class TestTimelineUICollection:
    def test_create_timeline_ui_hierarchy_timeline(self, tls, tluis):
        tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test")

        ui = list(tluis.get_timeline_uis())[0]

        assert ui.__class__ == HierarchyTimelineUI
        assert ui in tluis._timeline_uis
        assert tluis._select_order[0] == ui

        # cleanup
        tls.delete_timeline(ui.timeline)

    def test_create_timeline_ui_slider_timeline(self, tls, tluis):
        tls.create_timeline(TlKind.SLIDER_TIMELINE, name="test")

        ui = list(tluis.get_timeline_uis())[0]

        assert ui.__class__ == SliderTimelineUI
        assert ui in tluis._timeline_uis
        assert tluis._select_order[0] == ui

        # cleanup
        tls.delete_timeline(ui.timeline)

    def test_create_two_timeline_uis(self, tls, tluis):
        tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test1")

        tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test2")

        ui1, ui2 = tluis._select_order

        assert ui1.name == "test2"
        assert ui2.name == "test1"

        # cleanup
        tls.delete_timeline(ui1.timeline)
        tls.delete_timeline(ui2.timeline)

    def test_create_timeline_uis_of_all_kinds(self, tls, tluis):
        for kind in TimelineKind:
            with PatchGet(
                "tilia.timelines.collection", Get.BEAT_PATTERN_FROM_USER, [1]
            ):
                tls.create_timeline(kind)

        assert len(tluis.get_timeline_uis()) == len(TimelineKind)

        for timeline in tls._timelines.copy():
            tls.delete_timeline(timeline)

    def test_delete_timeline_ui(self, tls, tluis):
        tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test")

        tlui = list(tluis.get_timeline_uis())[0]

        tls.delete_timeline(tlui.timeline)

        assert not tluis._timeline_uis
        assert not tluis._select_order

    def test_update_select_order(self, tls, tluis):
        tl1 = tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test1")

        tl2 = tls.create_timeline(TlKind.HIERARCHY_TIMELINE, name="test2")

        tlui1 = tluis.get_timeline_ui(tl1.id)
        tlui2 = tluis.get_timeline_ui(tl2.id)

        assert tluis._select_order[0] == tlui2

        with patch("tilia.ui.timelines.collection.SelectionBox", lambda *_: None):
            post(Post.CANVAS_LEFT_CLICK, tlui1.canvas, 0, 0, 0, None, double=False)

        assert tluis._select_order[0] == tlui1

        with patch("tilia.ui.timelines.collection.SelectionBox", lambda *_: None):
            post(Post.CANVAS_LEFT_CLICK, tlui2.canvas, 0, 0, 0, None, double=False)

        assert tluis._select_order[0] == tlui2

        tls.delete_timeline(tlui1.timeline)
        tls.delete_timeline(tlui2.timeline)

    def test_on_timeline_toolbar_button(self, tluis):
        TIMELINE_UIS_MODULE = "tilia.ui.timelines.collection.TimelineUIs"
        for kind in tluis.tlkind_to_action_to_call_type:
            for button, call_type in tluis.tlkind_to_action_to_call_type[kind].items():
                with (
                    patch(
                        TIMELINE_UIS_MODULE + ".timeline_toolbar_button_call_on_all"
                    ) as call_on_all_mock,
                    patch(
                        TIMELINE_UIS_MODULE + ".timeline_toolbar_button_call_on_first"
                    ) as call_on_first_mock,
                    patch(
                        TIMELINE_UIS_MODULE + ".timeline_toolbar_button_record"
                    ) as record_mock,
                ):
                    tluis.on_timeline_toolbar_button(kind, button)
                if call_type == "all":
                    call_on_all_mock.assert_called_with(kind, button)
                else:
                    call_on_first_mock.assert_called_with(kind, button)

                record_mock.assert_called_with(button)

    def test_on_delete_button(self, tluis, beat_tlui, hierarchy_tlui, marker_tlui):
        marker, marker_ui = marker_tlui.create_marker(0)
        marker_tlui.select_element(marker_ui)
        hierarchy, hierarchy_ui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(hierarchy_ui)
        beat = beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui.get_component_ui(beat))

        tluis._on_delete_press()

        assert not marker_tlui.elements
        assert not hierarchy_tlui.elements
        assert not beat_tlui.elements

    def test_undo_redo_delete_button(
        self, tluis, beat_tlui, hierarchy_tlui, marker_tlui
    ):
        _, marker_ui = marker_tlui.create_marker(0)
        marker_tlui.select_element(marker_ui)
        _, hierarchy_ui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(hierarchy_ui)
        beat = beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui.get_component_ui(beat))

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tluis._on_delete_press()

        post(Post.REQUEST_TO_UNDO)
        assert len(marker_tlui.elements) == 1
        assert len(hierarchy_tlui.elements) == 1
        assert len(beat_tlui.elements) == 1

        post(Post.REQUEST_TO_REDO)
        assert not marker_tlui.elements
        assert not hierarchy_tlui.elements
        assert not beat_tlui.elements

    def test_ask_choose_timeline(self, tluis, beat_tlui, hierarchy_tlui, marker_tlui):
        with patch("tilia.ui.timelines.collection.ChooseDialog.ask", lambda _: 1):
            assert tluis.ask_choose_timeline("", "") == beat_tlui.timeline

        with patch("tilia.ui.timelines.collection.ChooseDialog.ask", lambda _: 2):
            assert tluis.ask_choose_timeline("", "") == hierarchy_tlui.timeline

        with patch("tilia.ui.timelines.collection.ChooseDialog.ask", lambda _: 3):
            assert tluis.ask_choose_timeline("", "") == marker_tlui.timeline

    def test_ask_choose_timeline_restrict_kind(
        self, tkui, tluis, beat_tlui, hierarchy_tlui, marker_tlui
    ):
        with (
            patch("tilia.ui.timelines.collection.ChooseDialog") as choose_window_mock,
        ):

            class ChooseWindowDummy:
                call_count = 0

                def ask(self):
                    """
                    ChooseDialog.ask must return the ordinal of
                    'hierarchy_tlui' and 'marker_tlui', respectively.
                    That is, 2 and 3.
                    """
                    self.call_count += 1
                    return self.call_count + 1

            choose_window_mock.return_value = ChooseWindowDummy()

            tluis.ask_choose_timeline("title", "prompt", TlKind.HIERARCHY_TIMELINE)

            choose_window_mock.assert_called_with(
                tkui.root, "title", "prompt", [(2, str(hierarchy_tlui))]
            )

            tluis.ask_choose_timeline("title", "prompt", TlKind.MARKER_TIMELINE)

            choose_window_mock.assert_called_with(
                tkui.root, "title", "prompt", [(3, str(marker_tlui))]
            )

    def test_import_markers_by_time_from_csv(self, tluis, beat_tlui, marker_tlui):
        pass

    def test_import_markers_by_measure_from_csv(self, tluis, beat_tlui, marker_tlui):
        pass
