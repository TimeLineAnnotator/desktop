from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
)
from tilia.requests import get, Get


class ResizeRect(QDialog):
    def __init__(self, old_width: float, old_height: float):
        super().__init__(get(Get.MAIN_WINDOW))
        self.old_width = old_width
        self.setWindowTitle("Set Image Output Width")
        self.setLayout(QFormLayout())

        self.new_width = QDoubleSpinBox()
        self.new_width.setRange(1, 16777215)
        self.new_width.setValue(old_width)
        self.layout().addRow("Width", self.new_width)

        self.layout().addRow("Height", QLabel(str(old_height)))

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Reset
            | QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            self.reset
        )
        button_box.button(QDialogButtonBox.StandardButton.Save).clicked.connect(
            self.accept
        )
        button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            self.reject
        )
        self.layout().addRow(button_box)

    def reset(self):
        self.blockSignals(True)
        self.new_width.setValue(self.old_width)
        self.blockSignals(False)

    @classmethod
    def new_size(cls, old_width: float, old_height: float) -> tuple[bool, float | None]:
        instance = cls(old_width, old_height)
        accept = instance.exec()

        if accept == QDialog.DialogCode.Accepted:
            return True, instance.new_width.value()
        return False, None
