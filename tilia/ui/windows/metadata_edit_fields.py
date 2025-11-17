import functools

from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox

from tilia.requests import Get, get


class EditMetadataFieldsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Edit metadata fields")
        self._setup_widgets()

    def _setup_widgets(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)
        self.populate()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(button_box)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def populate(self):
        def append_next_name(text, name):
            return text + name + "\n"

        field_names = list(get(Get.MEDIA_METADATA))
        for field in get(Get.MEDIA_METADATA_REQUIRED_FIELDS):
            field_names.remove(field)
        self.text_edit.setText(functools.reduce(append_next_name, field_names, ""))

    def get_fields_list(self):
        return self.text_edit.toPlainText().split("\n")

    def split_fields_by_validness(self):
        invalid = []
        valid = []
        for field in self.get_fields_list():
            if field == "":
                continue
            elif not field.replace(" ", "").isalnum():
                invalid.append(field)
            else:
                valid.append(field)

        return valid, invalid

    def get_result(self):
        return self.split_fields_by_validness()
