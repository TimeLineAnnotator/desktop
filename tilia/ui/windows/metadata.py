import functools

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QPushButton,
)

from tilia.requests import get, Get, post, Post
from tilia.ui.strings import (
    INVALID_METADATA_FIELD_ERROR_TITLE,
    INVALID_METADATA_FIELD_ERROR_PROMPT,
)
from tilia.ui.windows import WindowKind
from tilia.ui.format import format_media_time
from tilia.ui.windows.metadata_edit_notes import EditNotesDialog
from tilia.ui.windows.metadata_edit_fields import EditMetadataFieldsDialog


class MediaMetadataWindow(QDialog):
    KIND = WindowKind.MEDIA_METADATA

    SEPARATE_WINDOW_FIELDS = ["notes"]
    READ_ONLY_FIELDS = {
        "media length": functools.partial(get, Get.MEDIA_DURATION),
        "media path": functools.partial(get, Get.MEDIA_PATH),
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Metadata")
        self.metadata = {}
        self.fields_to_formatters = {"media length": format_media_time}
        self._setup_widgets()
        self.show()

        post(Post.WINDOW_METADATA_OPENED)

    def _setup_widgets(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.form_layout = QFormLayout()
        layout.addLayout(self.form_layout)
        self.setup_form_layout()

        self.button_layout = QVBoxLayout()
        layout.addLayout(self.button_layout)
        self.setup_button_layout()

    def setup_button_layout(self):
        edit_notes_button = QPushButton("Edit notes...")
        self.button_layout.addWidget(edit_notes_button)
        edit_notes_button.clicked.connect(self.on_edit_notes_button)

        edit_fields_button = QPushButton("Edit fields...")
        self.button_layout.addWidget(edit_fields_button)
        edit_fields_button.clicked.connect(self.on_edit_metadata_fields_button)

    def setup_form_layout(self):
        self.populate_with_editable_fields()
        self.add_separator_to_form()
        self.populate_with_read_only_fields()

    def add_separator_to_form(self):
        self.form_layout.addWidget(QLabel("-" * 50))

    def clear_form_layout(self):
        for _ in range(self.form_layout.rowCount()):
            self.form_layout.removeRow(0)

    def populate_with_editable_fields(self):
        metadata = get(Get.MEDIA_METADATA)
        self.metadata.clear()
        for name, value in metadata.items():
            if name in list(self.READ_ONLY_FIELDS) + self.SEPARATE_WINDOW_FIELDS:
                continue
            line_edit = QLineEdit(str(value))
            line_edit.textEdited.connect(functools.partial(self.on_text_edited, name))
            self.form_layout.addRow(QLabel(name.capitalize()), line_edit)
            self.metadata[name] = value

    def populate_with_read_only_fields(self):
        for name, getter in self.READ_ONLY_FIELDS.items():
            value = getter()
            if name in self.fields_to_formatters:
                value = self.fields_to_formatters[name](value)
            self.form_layout.addRow(QLabel(name.capitalize()), QLabel(value))

    def on_edit_notes_button(self):
        dialog = EditNotesDialog()
        accepted = dialog.exec()
        if accepted:
            self.on_text_edited("notes", dialog.result())

    def on_edit_metadata_fields_button(self):
        dialog = EditMetadataFieldsDialog()
        accepted = dialog.exec()
        if accepted:
            valid_fields, invalid_fields = dialog.result()
            if invalid_fields:
                self.display_invalid_field_error(invalid_fields)

            self.update_metadata_fields(valid_fields)
            self.refresh_fields()

    @staticmethod
    def display_invalid_field_error(invalid_fields: list[str]):
        post(
            Post.DISPLAY_ERROR,
            INVALID_METADATA_FIELD_ERROR_TITLE,
            INVALID_METADATA_FIELD_ERROR_PROMPT + "\n".join(invalid_fields),
        )

    def refresh_fields(self) -> None:
        self.clear_form_layout()
        self.setup_form_layout()

    @staticmethod
    def on_text_edited(field, value):
        post(Post.MEDIA_METADATA_FIELD_SET, field, value)

    def focus(self):
        pass  # TODO: set focus on self

    def closeEvent(self, event, **kwargs):
        post(Post.WINDOW_METADATA_CLOSED)
        super().closeEvent(event)

    def update_metadata_fields(self, new_fields: list[str]):
        fields_without_required = [
            item for item in self.metadata.keys() 
            if item not in get(Get.MEDIA_METADATA_REQUIRED_FIELDS)
        ]
        
        if not fields_without_required == new_fields:
            post(Post.METADATA_UPDATE_FIELDS, new_fields)
