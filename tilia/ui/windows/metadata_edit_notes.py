from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox

from tilia.requests import Get, get


class EditNotesDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Notes")
        self._setup_widgets()

    def _setup_widgets(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)
        self.text_edit.setText(get(Get.MEDIA_METADATA)["notes"])

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(button_box)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def get_result(self):
        return self.text_edit.toPlainText()
