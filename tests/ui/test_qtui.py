from unittest.mock import patch, mock_open

from tests.conftest import parametrize_tlui
from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import Serve
from tests.utils import get_main_window_menu, get_actions_in_menu
from tilia.requests import Post, post, Get
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.actions import get_qaction, TiliaAction
from tilia.ui.timelines.marker import MarkerTimelineUI
from tilia.ui.windows import WindowKind


class TestImport:
    def test_timeline_gets_restored_if_import_fails(self, qtui, marker_tl):
        for i in range(100):
            marker_tl.create_marker(i)

        prev_state = marker_tl.get_state()

        with patch(
            "tilia.ui.ui_import._get_by_time_or_by_measure_from_user",
            return_value=(True, "time"),
        ):
            with patch("builtins.open", mock_open(read_data="nonsense")):
                with Serve(Get.FROM_USER_FILE_PATH, (True, "")):
                    with Serve(
                        Get.FROM_USER_YES_OR_NO, True
                    ):  # confirm overwriting components
                        post(Post.IMPORT_CSV, TimelineKind.MARKER_TIMELINE)

        assert marker_tl.get_state() == prev_state

    def test_raises_error_if_invalid_csv(
        self, qtui, marker_tlui, tilia_errors, resources
    ):
        with (
            patch(
                "tilia.ui.ui_import._get_by_time_or_by_measure_from_user",
                return_value=(True, "time"),
            ),
            Serve(
                Get.FROM_USER_FILE_PATH,
                (
                    True,
                    (resources / EXAMPLE_MEDIA_PATH).resolve().__str__(),
                ),  # we use a media file as garbage
            ),
        ):
            post(Post.IMPORT_CSV, TimelineKind.MARKER_TIMELINE)

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_title("import")
        tilia_errors.assert_in_error_message("CSV")

    def test_raises_error_if_invalid_musicXML(
        self, qtui, score_tlui, beat_tlui, tilia_errors, resources
    ):
        with Serve(
            Get.FROM_USER_FILE_PATH,
            (
                True,
                (resources / EXAMPLE_MEDIA_PATH).resolve().__str__(),
            ),  # we use a media file as garbage
        ):
            post(Post.IMPORT_MUSICXML)

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_title("import")
        tilia_errors.assert_in_error_message("musicXML")


class TestCreateTimeline:
    def test_create(self, tls, hierarchy_tlui):
        assert not tls.is_empty

    def test_open_inspector_window(self, qtui, tls, tluis):
        tls.create_timeline("hierarchy")
        tluis[0].select_all_elements()

        assert qtui.open_inspect_window() is not None

    def test_open_multiple_inspector_windows_fails(self, qtui, tls, tluis):
        tls.create_timeline("hierarchy")
        tluis[0].select_all_elements()
        qtui.on_window_open(WindowKind.INSPECT)

        with patch("tilia.ui.windows.inspect.Inspect") as mock:
            qtui.on_window_open(WindowKind.INSPECT)

        mock.assert_not_called()


def get_toolbars_of_class(qtui, toolbar_class):
    return [x for x in qtui.main_window.children() if isinstance(x, toolbar_class)]


def is_toolbar_visible(qtui, toolbar_class):
    toolbar = get_toolbars_of_class(qtui, toolbar_class)

    return not toolbar[0].isHidden() if toolbar else False


class TestTimelineToolbars:
    @parametrize_tlui
    def test_is_visible_when_timeline_is_instantiated(self, qtui, tlui, request):
        tlui = request.getfixturevalue(tlui)
        toolbar_class = tlui.TOOLBAR_CLASS
        if toolbar_class:
            assert is_toolbar_visible(qtui, tlui.TOOLBAR_CLASS)

    @parametrize_tlui
    def test_is_not_visible_when_timeline_is_deleted(self, qtui, tlui, tls, request):
        tlui = request.getfixturevalue(tlui)
        if not tlui.TOOLBAR_CLASS:
            return
        tls.delete_timeline(tls[0])

        assert not is_toolbar_visible(qtui, tlui.TOOLBAR_CLASS)

    def test_is_not_duplicated_when_multiple_timelines_are_present(self, qtui, tls):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)

        assert len(get_toolbars_of_class(qtui, MarkerTimelineUI.TOOLBAR_CLASS)) == 1

    def test_is_not_hidden_when_second_instance_of_timeline_is_deleted(
        self, qtui, marker_tlui, tls
    ):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        tls.delete_timeline(tls[1])

        assert is_toolbar_visible(qtui, marker_tlui.TOOLBAR_CLASS)

    def test_is_hidden_when_timeline_is_hidden(self, qtui, tls, marker_tl):
        tls.set_timeline_data(marker_tl.id, "is_visible", False)

        assert not is_toolbar_visible(qtui, MarkerTimelineUI.TOOLBAR_CLASS)

    def test_is_not_hidden_when_second_instance_of_timeline_is_hidden(self, qtui, tls):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        tls.set_timeline_data(tls[1].id, "is_visible", False)

        assert is_toolbar_visible(qtui, MarkerTimelineUI.TOOLBAR_CLASS)

    def test_is_visible_if_timeline_is_made_visible_again(self, qtui, tls, marker_tl):
        tls.set_timeline_data(marker_tl.id, "is_visible", False)
        tls.set_timeline_data(marker_tl.id, "is_visible", True)

        assert is_toolbar_visible(qtui, MarkerTimelineUI.TOOLBAR_CLASS)


class TestMenus:
    def test_edit_menu_has_right_actions(self, qtui):
        menu = get_main_window_menu(qtui, "Edit")
        actions = get_actions_in_menu(menu)
        expected = [
            TiliaAction.EDIT_UNDO,
            TiliaAction.EDIT_REDO,
            TiliaAction.TIMELINE_ELEMENT_COPY,
            TiliaAction.TIMELINE_ELEMENT_PASTE,
            TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE,
            TiliaAction.SETTINGS_WINDOW_OPEN,
        ]
        expected = [get_qaction(action) for action in expected]
        assert set(actions) == set(expected)
