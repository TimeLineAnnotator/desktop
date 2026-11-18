"""The warnings a file opened with, in one dialog (FR-061): the file's name and how
many there are, then one line each, with a button that copies the lines."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import tilia.errors
from tilia.requests import Get, get

COPY = "Copy"


class ProblemsDialog(QDialog):
    def __init__(self, name: str, lines: list[str], parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tilia.errors.OPEN_FILE_PROBLEMS.title)
        self.lines = lines

        layout = QVBoxLayout(self)

        self.message = QLabel(tilia.errors.problems_message(name, len(lines)))
        self.message.setTextFormat(Qt.TextFormat.PlainText)  # a name isn't markup
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        # However many there are, each can be read and selected
        # (TimeLineAnnotator/project-management#597, point 5).
        self.lines_view = QPlainTextEdit("\n".join(lines))
        self.lines_view.setReadOnly(True)
        self.lines_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.lines_view.setMinimumWidth(600)
        layout.addWidget(self.lines_view)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        # An action: it leaves the dialog open.
        self.copy_button: QPushButton = self.buttons.addButton(
            COPY, QDialogButtonBox.ButtonRole.ActionRole
        )
        self.copy_button.clicked.connect(self.copy)
        self.buttons.accepted.connect(self.accept)
        layout.addWidget(self.buttons)

    def copy(self) -> None:
        QGuiApplication.clipboard().setText("\n".join(self.lines))


def show_problems(name: str, lines: list[str]) -> None:
    """Shows the dialog over TiLiA's window. A file named when TiLiA starts opens
    before the window shows: its dialog waits for the window."""
    window = get(Get.MAIN_WINDOW)

    def show() -> None:
        dialog = ProblemsDialog(name, lines, window)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.exec()

    if window.isVisible():
        show()
    else:
        _OnceShown(window, show)


class _OnceShown(QObject):
    """Calls `callback` from the event loop once `window` has shown, so that what it
    shows comes over the window."""

    def __init__(self, window: QWidget, callback: Callable[[], None]) -> None:
        super().__init__(window)  # the window keeps it until it has shown
        self.callback = callback
        window.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show:
            watched.removeEventFilter(self)
            QTimer.singleShot(0, watched, self.callback)
            self.deleteLater()
        return False
