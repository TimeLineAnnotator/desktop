from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

import tilia.ui.strings
from tilia.requests import Get, get


def ask_for_beat_unit_scope() -> tuple[bool, bool]:
    """
    Asks where a time signature edited in the inspector applies. Returns
    whether the user answered, and whether the edit applies to this measure
    only.
    """
    box = QMessageBox(get(Get.MAIN_WINDOW))
    box.setWindowTitle(tilia.ui.strings.TIME_SIGNATURE_SCOPE_TITLE)
    box.setText(tilia.ui.strings.BEAT_UNIT_SCOPE_PROMPT)
    onward = box.addButton(
        tilia.ui.strings.BEAT_UNIT_SCOPE_ONWARD, QMessageBox.ButtonRole.AcceptRole
    )
    measure = box.addButton(
        tilia.ui.strings.BEAT_UNIT_SCOPE_MEASURE, QMessageBox.ButtonRole.AcceptRole
    )
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(onward)
    box.exec()
    clicked = box.clickedButton()
    if clicked not in (onward, measure):
        return False, False
    return True, clicked is measure
