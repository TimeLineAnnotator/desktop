from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QObject, Qt
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QToolBar

from tilia.requests import Get, LongOperation, Post, get, listen

_PROGRESS_THROTTLE_MS = 100

_BLOCKED_MOUSE_EVENTS = {
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseButtonDblClick,
}


class _WindowFilter(QObject):
    """Installed on the application's windows while a long operation runs.

    Swallows their mouse button events while `is_blocking_input()` is true,
    and calls `on_blocked_changed(window, blocked)` when a modal dialog blocks
    or unblocks one of them.

    It goes on each window rather than on the application: an application
    filter written in Python makes PySide handle every event sent to every
    object, and doing that inside processEvents() corrupts the heap (#694).
    """

    def __init__(
        self,
        is_blocking_input: Callable[[], bool],
        on_blocked_changed: Callable[[QWindow, bool], None],
    ) -> None:
        super().__init__()
        self._is_blocking_input = is_blocking_input
        self._on_blocked_changed = on_blocked_changed

    def eventFilter(self, window: QObject, event: QEvent) -> bool:
        match event.type():
            case QEvent.Type.WindowBlocked:
                self._on_blocked_changed(window, True)
            case QEvent.Type.WindowUnblocked:
                self._on_blocked_changed(window, False)
            case event_type if event_type in _BLOCKED_MOUSE_EVENTS:
                return self._is_blocking_input()
        return False


class LongOperationToolbar(QToolBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMovable(False)
        self.setFloatable(False)
        self.setMaximumHeight(30)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedWidth(200)
        self._bar_action = self.addWidget(self._bar)

        self._label = QLabel()
        self._label.setContentsMargins(4, 0, 4, 0)
        self._label_action = self.addWidget(self._label)

        self.hide()

        self._stack: list[str] = []
        self._progress_timer = QElapsedTimer()
        self._window_filter = _WindowFilter(
            lambda: self._is_wait_cursor_set, self._on_window_blocked_changed
        )
        self._filtered_windows: list[QWindow] = []
        # Filtered windows that a modal dialog blocks. The wait cursor is
        # lifted while there are any, so that the dialog gets a normal one.
        self._blocked_windows: set[QWindow] = set()
        self._is_wait_cursor_set = False

        listen(self, Post.LONG_OPERATION, self._on_long_operation)

    def _on_long_operation(self, phase: LongOperation, *args) -> None:
        match phase:
            case LongOperation.STARTED:
                self._on_started(*args)
            case LongOperation.PROGRESS:
                self._on_progress(*args)
            case LongOperation.DONE:
                self._on_done()

    def _show_current(self) -> None:
        self._label.setText(self._stack[-1])
        self._bar.setMaximum(0)
        self._bar.setValue(0)
        self.show()

    def _pump(self) -> None:
        # See commit message for why this isn't just processEvents().
        if get(Get.MEDIA_TYPE) == "youtube":
            QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
            self.repaint()
        else:
            QApplication.processEvents()

    def _install_window_filter(self) -> None:
        windows = [
            window
            for widget in QApplication.topLevelWidgets()
            if widget.isVisible()
            and not isinstance(widget, QDialog)
            and (window := widget.windowHandle()) is not None
        ]
        self._filtered_windows = []
        for window in windows:
            try:
                window.installEventFilter(self._window_filter)
            except RuntimeError:
                # Already deleted. A widget that recreates its native window,
                # as the video window does, can hand back the wrapper of a
                # deleted one, and the garbage collector can delete a window
                # between any two lines here, so checking first wouldn't do.
                continue
            self._filtered_windows.append(window)
        if QApplication.activeModalWidget() is not None:
            # Qt only reports changes, so windows that an open modal dialog
            # blocks already would never be reported blocked.
            self._blocked_windows = set(self._filtered_windows)

    def _remove_window_filter(self) -> None:
        for window in self._filtered_windows:
            try:
                window.removeEventFilter(self._window_filter)
            except RuntimeError:
                pass  # Deleted during the operation, and its filter with it.
        self._filtered_windows = []
        self._blocked_windows = set()

    def _on_window_blocked_changed(self, window: QWindow, blocked: bool) -> None:
        if blocked:
            self._blocked_windows.add(window)
        else:
            self._blocked_windows.discard(window)
        self._update_wait_cursor()

    def _update_wait_cursor(self) -> None:
        should_be_set = bool(self._stack) and not self._blocked_windows
        if should_be_set and not self._is_wait_cursor_set:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        elif not should_be_set and self._is_wait_cursor_set:
            QApplication.restoreOverrideCursor()
        self._is_wait_cursor_set = should_be_set

    def _on_started(self, label: str) -> None:
        self._stack.append(label)
        self._show_current()
        if len(self._stack) == 1:
            self._install_window_filter()
            self._update_wait_cursor()
        self._progress_timer.start()
        self._pump()

    def _on_progress(self, value: int, maximum: int) -> None:
        if not self._stack:
            return
        if self._bar.maximum() != maximum:
            self._bar.setMaximum(maximum)
        self._bar.setValue(value)
        if self._progress_timer.elapsed() < _PROGRESS_THROTTLE_MS:
            return
        self._progress_timer.restart()
        self._pump()

    def _on_done(self) -> None:
        if not self._stack:
            return
        self._stack.pop()
        if self._stack:
            self._show_current()
        else:
            self.hide()
            self._label.setText("")
            self._bar.setMaximum(0)
            self._bar.setValue(0)
            self._remove_window_filter()
            self._update_wait_cursor()
