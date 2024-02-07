from tests.mock import PatchGet
from tilia import settings
from tilia.requests import Post, Get, post
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind as TlKind


class TestMarkerTimelineUI:
    def test_right_click_change_color(self, marker_tlui):
        with PatchGet(
            "tilia.ui.timelines.marker.timeline", Get.COLOR_FROM_USER, "#000000"
        ):
            mrk, ui = marker_tlui.create_marker(time=0)

            marker_tlui.right_clicked_element = ui

            marker_tlui.right_click_menu_change_color()

            assert mrk.color == "#000000"

    def test_right_click_reset_color(self, marker_tlui):
        with PatchGet(
            "tilia.ui.timelines.marker.timeline", Get.COLOR_FROM_USER, "#000000"
        ):
            mrk, ui = marker_tlui.create_marker(time=0)

            marker_tlui.right_clicked_element = ui

            marker_tlui.right_click_menu_change_color()
            marker_tlui.right_click_menu_reset_color()

            assert mrk.color == settings.get("marker_timeline", "marker_default_color")

    def test_on_add_marker_button(self, marker_tlui, tluis):
        with PatchGet(
            "tilia.ui.timelines.marker.timeline", Get.CURRENT_PLAYBACK_TIME, 0.101
        ):
            post(Post.MARKER_TOOLBAR_BUTTON_ADD)

        assert len(marker_tlui.elements) == 1
        assert list(marker_tlui.elements)[0].time == 0.101

    def test_undo_redo_add_marker(self, marker_tlui, tluis):
        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        with PatchGet(
            "tilia.ui.timelines.marker.timeline", Get.CURRENT_PLAYBACK_TIME, 0.101
        ):
            tluis.on_timeline_toolbar_button(TlKind.MARKER_TIMELINE, "add")

        post(Post.REQUEST_TO_UNDO)
        assert len(marker_tlui.elements) == 0

        post(Post.REQUEST_TO_REDO)
        assert len(marker_tlui.elements) == 1

    def test_on_delete_marker_button(self, marker_tlui):
        marker_tlui.create_marker(0)
        marker_tlui.select_element(list(marker_tlui.elements)[0])
        post(Post.MARKER_TOOLBAR_BUTTON_DELETE)

        assert len(marker_tlui.elements) == 0

    def test_on_delete_marker_button_multiple_markers(self, marker_tlui, tluis):
        marker_tlui.create_marker(0)
        marker_tlui.create_marker(0.1)
        marker_tlui.create_marker(0.2)

        for marker_ui in list(marker_tlui.elements):
            marker_tlui.select_element(marker_ui)

        post(Post.MARKER_TOOLBAR_BUTTON_DELETE)

        assert len(marker_tlui.elements) == 0

    def test_undo_redo_delete_marker_multiple_markers(self, marker_tlui, tluis):
        marker_tlui.create_marker(0)
        marker_tlui.create_marker(0.1)
        marker_tlui.create_marker(0.2)

        for marker_ui in list(marker_tlui.elements):
            marker_tlui.select_element(marker_ui)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tluis.on_timeline_toolbar_button(TlKind.MARKER_TIMELINE, "delete")

        post(Post.REQUEST_TO_UNDO)
        assert len(marker_tlui.elements) == 3

        post(Post.REQUEST_TO_REDO)
        assert len(marker_tlui.elements) == 0

    def test_undo_redo_delete_marker(self, marker_tlui, tluis):
        # 'tlui_clct' is needed as it subscriber to toolbar event
        # and forwards it to marker timeline

        marker_tlui.create_marker(0)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        marker_tlui.select_element(list(marker_tlui.elements)[0])
        tluis.on_timeline_toolbar_button(TlKind.MARKER_TIMELINE, "delete")

        post(Post.REQUEST_TO_UNDO)
        assert len(marker_tlui.elements) == 1

        post(Post.REQUEST_TO_REDO)
        assert len(marker_tlui.elements) == 0
