from PySide6.QtWidgets import QInputDialog

import tilia.ui.strings


class AskBeatPattern(QInputDialog):
    def __init__(self):
        super().__init__()
        self.setOption(QInputDialog.InputDialogOption.UsePlainTextEditForTextInput)

    def ask(self):
        result, accept = self.getMultiLineText(
            None,
            tilia.ui.strings.BEAT_PATTERN_DIALOG_TITLE,
            tilia.ui.strings.BEAT_PATTERN_DIALOG_PROMPT,
        )

        if accept:
            result = result.split()

        return result, accept
