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
from tilia.requests import get, Get


class ScaleOrCrop(QDialog):
    class ActionToTake(Enum):
        SCALE = 0
        CROP = 1
        PROMPT = 2

    def __init__(self, scale_text, crop_text, prompt_text):
        def get_result() -> int:
            return ScaleOrCrop.ActionToTake(_options.checkedId() % 2)

        super().__init__(
            None, Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
        )
        self.setWindowTitle("Scale or crop")

        self.setLayout(QVBoxLayout())

        _scale_button = QRadioButton()
        _crop_button = QRadioButton()
        _options = QButtonGroup(self)

        _scale_button.setText(scale_text)
        _crop_button.setText(crop_text)
        _options.addButton(_scale_button, 0)
        _options.addButton(_crop_button, 1)
        _scale_button.setChecked(True)

        self._prompt = QLabel(prompt_text)

        _button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply, self)
        _button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.accept
        )

        self.layout().addWidget(self._prompt)
        for button in _options.buttons():
            self.layout().addWidget(button)
        self.layout().addWidget(_button_box)

        self.get_result = get_result

    @staticmethod
    def get_text(
        old_start: float, old_end: float, new_start: float, new_end: float
    ) -> list[str]:

        if old_end - old_start == new_end - new_start:
            scale_text = "Shift timelines to new time."
            crop_text = "Delete timeline elements ouside of new time and fill the remaining difference."

        elif old_start <= new_start and old_end >= new_end:
            scale_text = "Compress timelines to new time."
            crop_text = "Delete timeline elements outside of new time."

        elif old_start >= new_start and old_end <= new_end:
            scale_text = "Stretch timelines to new time."
            crop_text = "Fill timelines with empty space."

        elif old_end - old_start > new_end - new_start:
            scale_text = "Compress timelines to new time."
            crop_text = "Delete timeline elements ouside of new time and fill the remaining difference."

        else:
            scale_text = "Stretch timelines to new time."
            crop_text = "Delete timeline elements ouside of new time and fill the remaining difference."

        prompt_text = (
            "Existing timelines need to be adjusted to the new playback duration."
            + f"\nCurrent time:\t{format_media_time(old_start, False)} - {format_media_time(old_end, False)}"
            + f"\nNew time:\t{format_media_time(new_start, False)} - {format_media_time(new_end, False)}"
            + "\n\nPlease select one of the following options:"
        )

        return scale_text, crop_text, prompt_text

    @classmethod
    def select(cls, old_start: float, old_end: float, new_start: float, new_end: float):
        scale_text, crop_text, prompt_text = ScaleOrCrop.get_text(
            old_start, old_end, new_start, new_end
        )
        if get(Get.UI_TYPE) == "QtUI":
            dialog = cls(scale_text, crop_text, prompt_text)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                return True, dialog.get_result()
            else:
                return False, None

        def get_result():
            return input(f"\n{prompt_text}\n{scale_text} (1)\n{crop_text} (2)\n")

        result = get_result()
        while result not in {"1", "2"}:
            print("\n\nInvalid response. Please select option '1' or '2'.")
            result = get_result()
        if result == "1":
            return True, ScaleOrCrop.ActionToTake.SCALE
        elif result == "2":
            return True, ScaleOrCrop.ActionToTake.CROP
        else:  # never reached
            return False, None
