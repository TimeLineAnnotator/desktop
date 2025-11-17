from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QRadioButton,
    QButtonGroup,
    QDialogButtonBox,
    QLabel,
)

import tilia.ui.strings


class AddTimelineWithoutMedia(QDialog):
    class Result(Enum):
        LOAD_MEDIA = 0
        SET_DURATION = 1

    def __init__(self):
        super().__init__(
            None, Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
        )
        self.setWindowTitle(
            tilia.ui.strings.ASK_ADD_TIMELINE_WITHOUT_MEDIA_DIALOG_TITLE
        )

        self.setLayout(QVBoxLayout())

        _load_media_button = QRadioButton()
        _set_media_duration_button = QRadioButton()
        self._options = QButtonGroup(self)

        self._prompt = QLabel(
            tilia.ui.strings.ASK_ADD_TIMELINE_WITHOUT_MEDIA_DIALOG_PROMPT
        )
        _load_media_button.setText(
            tilia.ui.strings.ASK_ADD_TIMELINE_WITHOUT_MEDIA_DIALOG_LOAD_MEDIA
        )
        _set_media_duration_button.setText(
            tilia.ui.strings.ASK_ADD_TIMELINE_WITHOUT_MEDIA_DIALOG_SET_MEDIA_DURATION
        )
        self._options.addButton(_load_media_button, 0)
        self._options.addButton(_set_media_duration_button, 1)
        _load_media_button.setChecked(True)

        _button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        _button_box.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(
            self.accept
        )
        _button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            self.reject
        )

        self.layout().addWidget(self._prompt)
        for button in self._options.buttons():
            self.layout().addWidget(button)
        self.layout().addWidget(_button_box)

    def _get_result(self):
        return AddTimelineWithoutMedia.Result(self._options.checkedId())

    @classmethod
    def select(cls) -> tuple[bool, Result | None]:
        instance = cls()
        accept = instance.exec()

        if accept == QDialog.DialogCode.Accepted:
            return True, instance._get_result()
        else:
            return False, None
