from PySide6.QtWidgets import (
    QDialog,
    QComboBox,
    QGridLayout,
    QLabel,
    QDialogButtonBox,
)

from tilia.timelines.harmony.constants import MODE_TYPES
from tilia.ui.timelines.harmony.constants import (
    NOTE_NAME_TO_INT,
    ACCIDENTAL_TO_INT,
)


class SelectModeParams(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Add key")
        layout = QGridLayout()
        self.setLayout(layout)

        step_combobox = self.step_combobox = QComboBox()
        for name, n in NOTE_NAME_TO_INT.items():
            step_combobox.addItem(name, n)

        accidental_combobox = self.accidental_combobox = QComboBox()
        for accidental, i in ACCIDENTAL_TO_INT.items():
            accidental_combobox.addItem(accidental, i)

        type_combobox = self.type_combobox = QComboBox()
        type_combobox.setStyleSheet("combobox-popup: 0;")
        for type_ in MODE_TYPES:
            type_combobox.addItem(type_, type_)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(QLabel("step"), 0, 0, 1, 2)
        layout.addWidget(step_combobox, 1, 0)
        layout.addWidget(accidental_combobox, 1, 1)

        layout.addWidget(QLabel("type"), 0, 2)
        layout.addWidget(type_combobox, 1, 2)

        layout.addWidget(button_box, 2, 0, 1, 3)

        self.show()

    def get_result(self):
        return {
            "step": self.step_combobox.currentData(),
            "accidental": self.accidental_combobox.currentData(),
            "type": self.type_combobox.currentData(),
            "level": 2,
        }

    @classmethod
    def select(cls) -> tuple[bool, None | dict[str, str | int]]:
        instance = cls()
        return (
            (True, instance.get_result())
            if instance.exec() == QDialog.DialogCode.Accepted
            else (False, None)
        )


def ask_for_mode_params() -> tuple[bool, None | dict[str, str | int]]:
    return SelectModeParams.select()
