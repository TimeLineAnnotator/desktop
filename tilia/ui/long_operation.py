from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QToolBar

from tilia.requests import LongOperation, Post, listen
from tilia.ui.webengine_tracking import any_web_engine_view_created

_PROGRESS_THROTTLE_MS = 100


class _DialogCursorFilter(QObject):
    """Restores the application override cursor while any QDialog is visible,
    then re-sets it when all dialogs close.  Installed on QApplication while a
    long operation is running and removed when the operation finishes."""

    def __init__(self, stack: list[str]) -> None:
        super().__init__()
        self._stack = stack
        self._open_count = 0

    def reset(self) -> None:
        self._open_count = 0

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if not isinstance(obj, QDialog):
            return False

        if event.type() == QEvent.Type.Show:
            if self._open_count == 0 and QApplication.overrideCursor():
                QApplication.restoreOverrideCursor()
            self._open_count += 1
        elif event.type() == QEvent.Type.Hide:
            self._open_count = max(0, self._open_count - 1)
            if self._open_count == 0 and self._stack:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        return False


_BLOCKED_MOUSE_EVENTS = {
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseButtonDblClick,
}


class _InputBlockFilter(QObject):
    """Swallows mouse button events while the application override cursor is set."""

    def eventFilter(self, _: QObject, event: QEvent) -> bool:
        return (
            event.type() in _BLOCKED_MOUSE_EVENTS
            and QApplication.overrideCursor() is not None
        )


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
        self._dialog_cursor_filter = _DialogCursorFilter(self._stack)
        self._input_block_filter = _InputBlockFilter()
        self._app: QApplication = QApplication.instance()  # type: ignore[assignment]

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
        if any_web_engine_view_created():
            QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
            self.repaint()
        else:
            QApplication.processEvents()

    def _on_started(self, label: str) -> None:
        self._stack.append(label)
        self._show_current()
        if len(self._stack) == 1:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._app.installEventFilter(self._dialog_cursor_filter)
            self._app.installEventFilter(self._input_block_filter)
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
            self._app.removeEventFilter(self._dialog_cursor_filter)
            self._app.removeEventFilter(self._input_block_filter)
            self._dialog_cursor_filter.reset()
            QApplication.restoreOverrideCursor()
