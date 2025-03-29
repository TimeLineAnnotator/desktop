from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
)


class ResizeRect(QDialog):
    def __init__(self, old_width: float, old_height: float):
        super().__init__()
        self.old_width = old_width
        self.old_height = old_height
        self.old_ratio = old_width / old_height
        self.setWindowTitle("Resize Timelines")
        self.setLayout(QFormLayout())

        original_dim = QLabel(f"Original: {old_width} x {old_height}")
        self.layout().addRow(original_dim)

        self.new_width = QDoubleSpinBox()
        self.new_width.setRange(1, 16777215)
        self.new_width.setValue(old_width)
        self.new_width.valueChanged.connect(self.update_height)
        self.layout().addRow("New Width", self.new_width)

        self.new_height = QDoubleSpinBox()
        self.new_height.setRange(1, 16777215)
        self.new_height.setValue(old_height)
        self.new_height.valueChanged.connect(self.update_width)
        self.layout().addRow("New Height", self.new_height)

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

    def update_height(self, width: float):
        self.new_height.blockSignals(True)
        self.new_height.setValue(width / self.old_ratio)
        self.new_height.blockSignals(False)

    def update_width(self, height: float):
        self.new_width.blockSignals(True)
        self.new_width.setValue(height * self.old_ratio)
        self.new_width.blockSignals(False)

    def reset(self):
        self.blockSignals(True)
        self.new_height.setValue(self.old_height)
        self.new_width.setValue(self.old_width)
        self.blockSignals(False)

    @classmethod
    def new_size(
        cls, old_width: float, old_height: float
    ) -> tuple[bool, tuple[float, float] | None]:
        instance = cls(old_width, old_height)
        accept = instance.exec()

        if accept == QDialog.DialogCode.Accepted:
            return True, (instance.new_width.value(), instance.new_height.value())
        return False, None
