from PySide6.QtWidgets import QInputDialog

import tilia.ui.strings
from tilia.requests import Get, get


class AskBeatPattern(QInputDialog):
    def __init__(self):
        super().__init__()
        self.setOption(QInputDialog.InputDialogOption.UsePlainTextEditForTextInput)

    def ask(self):
        result, accept = self.getMultiLineText(
            get(Get.MAIN_WINDOW),
            tilia.ui.strings.BEAT_PATTERN_DIALOG_TITLE,
            tilia.ui.strings.BEAT_PATTERN_DIALOG_PROMPT,
        )

        if accept:
            result = result.split()

        return result, accept
