from unittest.mock import patch

import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from tests.mock import Serve
from tilia.requests import Get, LongOperation, Post, post
from tilia.ui import commands


@pytest.fixture(autouse=True)
def drain_stack(qtui):
    yield
    toolbar = qtui._long_op_toolbar
    while toolbar._stack:
        post(Post.LONG_OPERATION, LongOperation.DONE)


class _FakeElapsedTimer:
    """Deterministic stand-in for QElapsedTimer so throttle tests don't
    depend on real wall-clock timing."""

    def __init__(self):
        self.elapsed_ms = 0

    def start(self):
        self.elapsed_ms = 0

    def restart(self):
        self.elapsed_ms = 0

    def elapsed(self):
        return self.elapsed_ms


class TestLongOperationToolbar:
    def test_toolbar_hidden_initially(self, qtui):
        assert qtui._long_op_toolbar.isHidden()

    def test_toolbar_shows_on_started(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        assert not qtui._long_op_toolbar.isHidden()

    def test_toolbar_hides_after_done(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert qtui._long_op_toolbar.isHidden()

    def test_label_text_set_on_started(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Loading file")
        assert qtui._long_op_toolbar._label.text() == "Loading file"

    def test_bar_indeterminate_on_started(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        assert qtui._long_op_toolbar._bar.maximum() == 0

    def test_bar_updates_on_progress(self, qtui):
        toolbar = qtui._long_op_toolbar
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        post(Post.LONG_OPERATION, LongOperation.PROGRESS, 5, 10)
        assert toolbar._bar.maximum() == 10
        assert toolbar._bar.value() == 5

    def test_nested_toolbar_stays_visible_after_inner_done(self, qtui):
        toolbar = qtui._long_op_toolbar
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Outer")
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Inner")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert not toolbar.isHidden()

    def test_nested_toolbar_hides_after_outer_done(self, qtui):
        toolbar = qtui._long_op_toolbar
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Outer")
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Inner")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert toolbar.isHidden()

    def test_nested_restores_outer_label_after_inner_done(self, qtui):
        toolbar = qtui._long_op_toolbar
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Outer")
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Inner")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert toolbar._label.text() == "Outer"

    def test_done_without_started_is_safe(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert qtui._long_op_toolbar.isHidden()

    def test_progress_throttles_process_events(self, qtui):
        toolbar = qtui._long_op_toolbar
        toolbar._progress_timer = _FakeElapsedTimer()
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        with patch("tilia.ui.long_operation.QApplication.processEvents") as mock_pe:
            for i in range(50):
                post(Post.LONG_OPERATION, LongOperation.PROGRESS, i, 50)
            assert mock_pe.call_count == 0
            assert toolbar._bar.value() == 49

    def test_progress_processes_events_after_throttle_elapses(self, qtui):
        toolbar = qtui._long_op_toolbar
        fake_timer = _FakeElapsedTimer()
        toolbar._progress_timer = fake_timer
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        fake_timer.elapsed_ms = 150
        with patch("tilia.ui.long_operation.QApplication.processEvents") as mock_pe:
            post(Post.LONG_OPERATION, LongOperation.PROGRESS, 1, 50)
            assert mock_pe.call_count == 1

    def test_started_avoids_process_events_for_youtube_player(self, qtui):
        with (
            Serve(Get.MEDIA_TYPE, "youtube"),
            patch("tilia.ui.long_operation.QApplication.processEvents") as mock_pe,
            patch(
                "tilia.ui.long_operation.QCoreApplication.sendPostedEvents"
            ) as mock_spe,
        ):
            post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
            assert mock_pe.call_count == 0
            assert mock_spe.call_count == 1


def _click_through_window(widget):
    # Through the window, as a user's click arrives: QTest.mouseClick(widget)
    # hands the event straight to the widget.
    top_level = widget.window()
    position = widget.mapTo(top_level, widget.rect().center())
    QTest.mouseClick(
        top_level.windowHandle(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        position,
    )


@pytest.fixture
def main_window(qtui):
    """The main window, shown, as it is in the app. Until it is, it has no
    window for the long operation to filter."""
    qtui.main_window.show()
    QTest.qWaitForWindowExposed(qtui.main_window)
    yield qtui.main_window
    qtui.main_window.hide()


@pytest.fixture
def zoom_in_clicks(qtui, main_window):
    """Clicks the zoom-in button; returns how many times its action was
    triggered."""
    action = commands.get_qaction("view.zoom.in")
    triggered = []
    action.triggered.connect(lambda: triggered.append(True))

    def click():
        _click_through_window(qtui._zoom_toolbar.widgetForAction(action))
        return len(triggered)

    yield click
    action.triggered.disconnect()


@pytest.fixture
def modal_dialog(main_window):
    """A modal dialog over the main window, closed even if the test fails, so
    that it can't block the next test's clicks."""
    dialog = QDialog(main_window)
    dialog.setModal(True)
    yield dialog
    dialog.close()


def _is_wait_cursor_shown():
    cursor = QApplication.overrideCursor()
    return cursor is not None and cursor.shape() == Qt.CursorShape.WaitCursor


class TestInputDuringOperation:
    def test_clicks_are_ignored_during_operation(self, zoom_in_clicks):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        assert zoom_in_clicks() == 0

    def test_clicks_work_after_operation(self, zoom_in_clicks):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert zoom_in_clicks() == 1

    def test_starts_while_a_window_hands_back_a_deleted_window(self, qtui):
        # As the video window can, after recreating its native window.
        deleted = QWindow()
        shiboken6.delete(deleted)

        class Window(QWidget):
            def windowHandle(self):
                return deleted

        window = Window()
        window.show()
        try:
            post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
            assert not qtui._long_op_toolbar.isHidden()
        finally:
            window.close()

    def test_finishes_after_a_window_is_deleted_during_it(self, qtui):
        window = QWidget()
        window.show()
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        shiboken6.delete(window)

        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert qtui._long_op_toolbar.isHidden()

    def test_does_not_filter_events_of_the_whole_application(self, qtui):
        # An application-wide event filter written in Python corrupts the heap
        # when events are processed during the operation (#694).
        app = QApplication.instance()
        with patch.object(app, "installEventFilter") as install:
            post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        install.assert_not_called()


class TestCursorDuringOperation:
    def test_wait_cursor_is_shown_during_operation(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        assert _is_wait_cursor_shown()

    def test_wait_cursor_is_removed_after_operation(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert QApplication.overrideCursor() is None

    def test_wait_cursor_is_lifted_while_a_modal_dialog_is_open(self, modal_dialog):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        modal_dialog.show()
        assert QApplication.overrideCursor() is None

        modal_dialog.close()
        assert _is_wait_cursor_shown()

    def test_clicks_are_still_ignored_once_a_modal_dialog_closes(
        self, modal_dialog, zoom_in_clicks
    ):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        modal_dialog.show()
        modal_dialog.close()

        assert zoom_in_clicks() == 0

    def test_operation_started_behind_a_modal_dialog(self, modal_dialog):
        modal_dialog.show()
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        assert QApplication.overrideCursor() is None

        modal_dialog.close()
        assert _is_wait_cursor_shown()
