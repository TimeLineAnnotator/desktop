from types import SimpleNamespace
from unittest.mock import mock_open, patch

import pytest
from PySide6.QtCore import QtMsgType

from tests.conftest import parametrize_tlui
from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import Serve
from tests.utils import get_actions_in_menu, get_main_window_menu
from tilia.requests import Get, Post, post
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.commands import get_qaction
from tilia.ui.qtui import TiliaMainWindow
from tilia.ui.timelines.marker import MarkerTimelineUI
from tilia.ui.windows import WindowKind


class TestImport:
    patch_target = (
        "tilia.ui.timelines.collection.import_._get_by_time_or_by_measure_from_user"
    )

    def test_timeline_gets_restored_if_import_fails(self, qtui, marker_tl):
        for i in range(100):
            marker_tl.create_marker(i)

        prev_state = marker_tl.get_state()

        with patch(
            self.patch_target,
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
                self.patch_target,
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
        tilia_errors.assert_in_error_title("Import")
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
        tilia_errors.assert_in_error_title("Import")
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
            "edit.undo",
            "edit.redo",
            "timeline.component.copy",
            "timeline.component.paste",
            "timeline.component.paste_complete",
            "window.open.settings",
        ]
        expected = [get_qaction(action) for action in expected]
        assert set(actions) == set(expected)


class TestHandleQtLogMessage:
    def _ctx(self, file="widget.cpp", line=42):
        return SimpleNamespace(file=file, line=line)

    def test_fatal_message_raises_exception(self):
        with pytest.raises(Exception, match=r"\[QtFatalMsg\] widget\.cpp:42 - boom"):
            TiliaMainWindow.handle_qt_log_message(
                QtMsgType.QtFatalMsg, self._ctx(), "boom"
            )

    def test_fatal_exception_message_includes_file_and_line(self):
        with pytest.raises(Exception) as exc_info:
            TiliaMainWindow.handle_qt_log_message(
                QtMsgType.QtFatalMsg, self._ctx(file="core.cpp", line=99), "fatal"
            )
        assert "core.cpp:99" in str(exc_info.value)

    @pytest.mark.parametrize(
        "msg_type",
        [
            QtMsgType.QtDebugMsg,
            QtMsgType.QtInfoMsg,
            QtMsgType.QtWarningMsg,
            QtMsgType.QtCriticalMsg,
        ],
    )
    def test_non_fatal_message_calls_logger_error(self, msg_type):
        ctx = self._ctx(file="view.cpp", line=7)
        with patch("tilia.ui.qtui.logger") as mock_logger:
            TiliaMainWindow.handle_qt_log_message(msg_type, ctx, "something happened")
        mock_logger.error.assert_called_once_with(
            f"[{msg_type.name}] view.cpp:7 - something happened"
        )

    def test_non_fatal_message_does_not_raise(self):
        with patch("tilia.ui.qtui.logger"):
            TiliaMainWindow.handle_qt_log_message(
                QtMsgType.QtWarningMsg, self._ctx(), "non-fatal"
            )

    def test_context_file_none_does_not_raise(self):
        with patch("tilia.ui.qtui.logger"):
            TiliaMainWindow.handle_qt_log_message(
                QtMsgType.QtWarningMsg, self._ctx(file=None, line=-1), "msg"
            )
