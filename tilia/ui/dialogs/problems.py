"""The warnings a file opened with, in one dialog (FR-061): the file's name and how
many there are, then one line each, with a button that copies the lines."""

from __future__ import annotations

from PySide6.QtCore import Qt
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

from tilia.requests import Get, get

TITLE = "Problems in this file"
COPY = "Copy"


def problems_message(name: str, count: int) -> str:
    """What the dialog says before the lines, and the command line prints. One
    problem is in the singular (TimeLineAnnotator/project-management#597, point 1)."""
    if count == 1:
        return (
            f"'{name}' has 1 problem. TiLiA keeps it as it is, and saves it unchanged"
            " until you fix it."
        )
    return (
        f"'{name}' has {count} problems. TiLiA keeps them as they are, and saves"
        " them unchanged until you fix them."
    )


class ProblemsDialog(QDialog):
    def __init__(self, name: str, lines: list[str], parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.lines = lines

        layout = QVBoxLayout(self)

        self.message = QLabel(problems_message(name, len(lines)))
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
    dialog = ProblemsDialog(name, lines, get(Get.MAIN_WINDOW))
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.exec()
