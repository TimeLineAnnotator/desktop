from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QInputDialog, QMessageBox

from tilia.requests import Get, get


def ask_for_color(
    initial: str = "#333333",
):  # feel free to change this arbitrary default
    color = QColorDialog.getColor(QColor(initial), get(Get.MAIN_WINDOW))
    return color.isValid(), color  # returned color is invalid if user cancels


def ask_for_int(title: str, prompt: str, **kwargs) -> tuple[bool, int]:
    number, accepted = QInputDialog.getInt(
        get(Get.MAIN_WINDOW), title, prompt, **kwargs
    )
    return accepted, number


def ask_for_string(title: str, prompt: str, **kwargs) -> tuple[bool, str]:
    string, accepted = QInputDialog.getText(
        get(Get.MAIN_WINDOW), title, prompt, **kwargs
    )
    return accepted, string


def ask_for_float(title: str, prompt: str, **kwargs) -> tuple[bool, float]:
    number, accepted = QInputDialog.getDouble(
        get(Get.MAIN_WINDOW), title, prompt, **kwargs
    )
    return accepted, number


def ask_yes_no_or_cancel(title: str, prompt: str) -> tuple[bool, bool]:
    result = QMessageBox(
        QMessageBox.Icon.Question,
        title,
        prompt,
        QMessageBox.StandardButton.Yes
        | QMessageBox.StandardButton.No
        | QMessageBox.StandardButton.Cancel,
        get(Get.MAIN_WINDOW),
    ).exec()

    return (
        result != QMessageBox.StandardButton.Cancel,  # success
        result == QMessageBox.StandardButton.Yes,  # result
    )


def ask_yes_or_no(title: str, prompt: str) -> bool:
    return (
        QMessageBox.question(get(Get.MAIN_WINDOW), title, prompt)
        == QMessageBox.StandardButton.Yes
    )


def _truncate_error_message(message: str):
    if len(lines := message.split("\n")) > 35:
        message = "\n".join(lines[:35]) + "\n..."
    return message


def display_error(title: str, message: str):
    message = _truncate_error_message(message)
    QMessageBox(
        QMessageBox.Icon.Critical,
        title,
        message,
        QMessageBox.StandardButton.Close,
        get(Get.MAIN_WINDOW),
    ).exec()
