from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QLabel,
    QComboBox,
    QVBoxLayout,
    QDialogButtonBox,
)


class ChooseDialog(QDialog):
    def __init__(
        self,
        parent: QMainWindow,
        title: str,
        prompt_text: str,
        options: list[tuple[str, Any]],
    ):
        super().__init__(parent)
        self.setWindowTitle(title)

        layout = QVBoxLayout()
        self.setLayout(layout)

        prompt = QLabel(prompt_text)
        combo_box = QComboBox()
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(prompt)
        layout.addWidget(combo_box)
        layout.addWidget(button_box)

        for i, (name, data) in enumerate(options):
            combo_box.insertItem(i, name, data)

        def get_option():
            return combo_box.currentData()

        self.get_option = get_option
