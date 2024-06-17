import functools

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame
)

from tilia import settings
from tilia.requests import get, Get, post, Post
from tilia.ui.windows import WindowKind
from tilia.ui.format import format_media_time
from tilia.ui.windows.metadata_edit_notes import EditNotesDialog
from tilia.ui.windows.metadata_edit_fields import EditMetadataFieldsDialog
import tilia.errors


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
        self.metadata_original = {}
        self.fields_to_formatters = {"media length": format_media_time}
        self.setMinimumSize(settings.get("media_metadata", "window-width"), 0)
        self._setup_widgets()
        self.show()

        post(Post.WINDOW_METADATA_OPENED)

    def _setup_widgets(self):
        self.form_layout = QFormLayout(self)
        self.setLayout(self.form_layout)
        self.setup_layout()

    def setup_layout(self):
        self.populate_with_editable_fields()
        self.add_separator()
        self.populate_with_read_only_fields()
        self.setup_buttons()
        self.adjustSize()

    def add_separator(self):
        line = QFrame()
        line.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)
        self.form_layout.addRow(line)

    def clear_layout(self):
        while self.form_layout.rowCount():
            self.form_layout.removeRow(0)

    def populate_with_editable_fields(self):
        metadata = get(Get.MEDIA_METADATA)
        self.metadata.clear()
        self.metadata_original.clear()
        for name, value in metadata.items():
            if name in list(self.READ_ONLY_FIELDS) + self.SEPARATE_WINDOW_FIELDS:
                continue
            line_edit = QLineEdit(str(value))
            self.form_layout.addRow(QLabel(name.capitalize()), line_edit)
            self.metadata[name] = line_edit
            self.metadata_original[name] = value

    def populate_with_read_only_fields(self):
        for name, getter in self.READ_ONLY_FIELDS.items():
            value = getter()
            if name in self.fields_to_formatters:
                value = self.fields_to_formatters[name](value)
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            self.form_layout.addRow(QLabel(name.capitalize()), value_label)

    def setup_buttons(self):
        edit_notes_button = QPushButton("Edit notes...")
        edit_notes_button.clicked.connect(self.on_edit_notes_button)
        self.form_layout.addRow(edit_notes_button)

        edit_fields_button = QPushButton("Edit fields...")
        edit_fields_button.clicked.connect(self.on_edit_metadata_fields_button)
        self.form_layout.addRow(edit_fields_button)

    def on_edit_notes_button(self):
        dialog = EditNotesDialog()
        accepted = dialog.exec()
        if accepted:
            post(Post.MEDIA_METADATA_FIELD_SET, "notes", dialog.result())

    def on_edit_metadata_fields_button(self):
        self._save_edits()
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
        tilia.errors.display(tilia.errors.METADATA_FIELD_INVALID, "\n".join(invalid_fields))

    def refresh_fields(self) -> None:
        self.clear_layout()
        self.setup_layout()

    def focus(self):
        pass  # TODO: set focus on self

    def closeEvent(self, event, **kwargs):
        self._save_edits()
        post(Post.WINDOW_METADATA_CLOSED)
        super().closeEvent(event)

    def update_metadata_fields(self, new_fields: list[str]):
        fields_without_required = [
            item for item in self.metadata.keys() 
            if item not in get(Get.MEDIA_METADATA_REQUIRED_FIELDS)
        ]
        
        if not fields_without_required == new_fields:
            post(Post.METADATA_UPDATE_FIELDS, get(Get.MEDIA_METADATA_REQUIRED_FIELDS) + new_fields)

    def _save_edits(self):
        edited_fields = {
            name: self.metadata[name].text() 
            for name in self.metadata 
            if name in self.metadata_original 
            and self.metadata[name].text() != self.metadata_original[name]
        }
        if edited_fields and get(Get.FROM_USER_YES_OR_NO, 
                                 "Save metadata edits", 
                                 "Save edits before continuing?<br>This <i>cannot</i> be undone later."
                                 ):
            for name, value in edited_fields.items():
                post(Post.MEDIA_METADATA_FIELD_SET, name, value)
