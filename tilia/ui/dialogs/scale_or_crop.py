from PyQt6.QtWidgets import (
    QDialog,
    QButtonGroup,
    QRadioButton,
    QVBoxLayout,
    QDialogButtonBox,
    QLabel,
)
from PyQt6.QtCore import Qt
from enum import Enum

from tilia.ui.format import format_media_time


class ScaleOrCrop(QDialog):
    class ActionToTake(Enum):
        SCALE = 0
        CROP = 1
        PROMPT = 2

    def __init__(
        self, old_start: float, old_end: float, new_start: float, new_end: float
    ):
        def set_button_text():
            if old_end - old_start == new_end - new_start:
                _scale_button.setText("Shift timelines to new time.")
                _crop_button.setText(
                    "Delete timeline elements ouside of new time and fill the remaining difference."
                )

            elif old_start <= new_start and old_end >= new_end:
                _scale_button.setText("Compress timelines to new time.")
                _crop_button.setText("Delete timeline elements outside of new time.")

            elif old_start >= new_start and old_end <= new_end:
                _scale_button.setText("Stretch timelines to new time.")
                _crop_button.setText("Fill timelines with empty space.")

            elif old_end - old_start > new_end - new_start:
                _scale_button.setText("Compress timelines to new time.")
                _crop_button.setText(
                    "Delete timeline elements ouside of new time and fill the remaining difference."
                )

            else:
                _scale_button.setText("Stretch timelines to new time.")
                _crop_button.setText(
                    "Delete timeline elements ouside of new time and fill the remaining difference."
                )

            _options.addButton(_scale_button, 0)
            _options.addButton(_crop_button, 1)
            _scale_button.setChecked(True)

        def get_result() -> int:
            return ScaleOrCrop.ActionToTake(_options.checkedId() % 2)

        super().__init__(
            None, Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
        )
        self.setWindowTitle("Scale or crop")

        self.setLayout(QVBoxLayout())

        _prompt = QLabel(
            "Existing timelines need to be adjusted to the new playback duration."
            + f"\nCurrent time:\t{format_media_time(old_start, False)} - {format_media_time(old_end, False)}"
            + f"\nNew time:\t{format_media_time(new_start, False)} - {format_media_time(new_end, False)}"
            + "\n\nPlease select one of the following options:"
        )

        _scale_button = QRadioButton()
        _crop_button = QRadioButton()
        _options = QButtonGroup(self)
        set_button_text()

        _button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply, self)
        _button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.accept
        )

        self.layout().addWidget(_prompt)
        for button in _options.buttons():
            self.layout().addWidget(button)
        self.layout().addWidget(_button_box)

        self.get_result = get_result

    @classmethod
    def select(cls, old_start: float, old_end: float, new_start: float, new_end: float):
        dialog = cls(old_start, old_end, new_start, new_end)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return True, dialog.get_result()
        else:
            return False, None
