from typing import Optional

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QInputDialog, QMessageBox, QFileDialog


def ask_for_color(initial: str):
    return QColorDialog().getColor(QColor(initial))


def ask_for_int(title: str, prompt: str, initial: Optional[int] = 0) -> str:
    return QInputDialog().getInt(None, title, prompt, initial)


def ask_for_string(title: str, prompt: str, initial: Optional[str] = "") -> str:
    return QInputDialog().getText(None, title, prompt, text=initial)


def ask_for_float(title: str, prompt: str, initial: Optional[float] = 0.0):
    return QInputDialog().getDouble(None, title, prompt, initial)


def ask_yes_no_or_cancel(title: str, prompt: str) -> tuple[bool, bool]:
    result = QMessageBox().question(
        None,
        title,
        prompt,
        buttons=QMessageBox.StandardButton(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        ),
    )

    return (
        result != QMessageBox.StandardButton.Cancel,
        result == QMessageBox.StandardButton.Yes,
    )


def ask_yes_or_no(title: str, prompt: str) -> bool:
    return QMessageBox().question(None, title, prompt) == QMessageBox.StandardButton.Yes


def ask_for_directory(title: str) -> str | None:
    return QFileDialog.getExistingDirectory(None, title)


def _truncate_error_message(message: str):
    if len(lines := message.split("\n")) > 35:
        message = "\n".join(lines[:35]) + "\n..."
    return message


def display_error(title: str, message: str):
    message = _truncate_error_message(message)
    QMessageBox(
        QMessageBox.Icon.Critical, title, message, QMessageBox.StandardButton.Close
    ).exec()
