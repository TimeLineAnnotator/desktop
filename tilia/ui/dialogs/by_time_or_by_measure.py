from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QDialogButtonBox,
)
from tilia.requests import get, Get


class ByTimeOrByMeasure(QDialog):
    def __init__(self):
        super().__init__(get(Get.MAIN_WINDOW))
        self.setWindowTitle("Import by time or measure")
        self.setFixedSize(300, 110)
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        prompt = QLabel("Import using:")
        self.time_radio = QRadioButton("Time")
        measure_and_fraction_radio = QRadioButton("Measure")
        self.time_radio.setChecked(True)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(prompt)
        layout.addWidget(self.time_radio)
        layout.addWidget(measure_and_fraction_radio)
        layout.addWidget(button_box)

    def get_option(self):
        return "time" if self.time_radio.isChecked() else "measure"
