import functools

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import tilia.errors
from tilia.requests import Get, Post, get, listen, post, stop_listening_to_all
from tilia.settings import settings
from tilia.ui.format import MEDIA_TIME_PATTERN, format_media_time, parse_media_time
from tilia.ui.windows import WindowKind
from tilia.ui.windows.metadata_edit_fields import EditMetadataFieldsDialog
from tilia.ui.windows.metadata_edit_notes import EditNotesDialog


class MediaMetadataWindow(QDialog):
    KIND = WindowKind.MEDIA_METADATA

    SEPARATE_WINDOW_FIELDS = ["notes"]
    READ_ONLY_FIELDS = {
        "media length": functools.partial(get, Get.MEDIA_DURATION),
        "media path": functools.partial(get, Get.MEDIA_PATH),
    }

    def __init__(self):
        super().__init__(get(Get.MAIN_WINDOW))
        self.setWindowTitle("Metadata")
        self.metadata = {}
        self.metadata_original = {}
        self.fields_to_formatters = {"media length": format_media_time}
        self.setMinimumSize(settings.get("media_metadata", "window_width"), 0)
        # The window is modal, but media can still finish loading while it is
        # open: loading runs nested event loops, in which keys open menus,
        # and a YouTube video's length arrives after the video has loaded.
        # Loading media changes the length, and whether it can be edited.
        listen(self, Post.PLAYER_URL_CHANGED, lambda _: self.update_read_only_fields())
        listen(self, Post.FILE_MEDIA_DURATION_CHANGED, self.on_media_duration_changed)
        self.setLayout(QVBoxLayout())
        self.setup_layout()
        # Like the dialogs it opens: while it is open, the main window takes no
        # input, so nothing else changes the metadata, and undo can't run.
        self.setModal(True)
        self.show()

        post(Post.WINDOW_OPEN_DONE, WindowKind.MEDIA_METADATA)

    def setup_layout(self):
        self._setup_widgets()
        self._setup_window_buttons()
        self._setup_fields()

    def _setup_fields(self):
        self.populate_with_editable_fields()
        self.add_separator()
        self.populate_with_read_only_fields()
        self.setup_buttons()
        self.adjustSize()

    def _setup_widgets(self):
        self.form_layout = QFormLayout()
        content = QWidget()
        content.setLayout(self.form_layout)
        self.layout().addWidget(content)

    def _setup_window_buttons(self):
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        # Enter in a field neither applies nor cancels: no button is the
        # default, and none becomes it when it gets the focus.
        for button in self.button_box.buttons():
            button.setAutoDefault(False)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.apply_fields
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            self.close
        )
        self.layout().addWidget(self.button_box)

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
        self.read_only_labels = {}
        for name in self.READ_ONLY_FIELDS:
            value_label = QLabel()
            value_label.setWordWrap(True)
            self.read_only_labels[name] = value_label
            field = value_label
            if name == "media length":
                field = self._setup_media_length_field(value_label)
            self.form_layout.addRow(QLabel(name.capitalize()), field)
        self.update_read_only_fields()

    def _setup_media_length_field(self, value_label: QLabel) -> QWidget:
        # With no media loaded, the length is the user's to set, as the dialog
        # for adding a timeline without media and the command line let them.
        # With media, it is the media's.
        self.media_length_edit = QLineEdit()
        self.media_length_edit.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(MEDIA_TIME_PATTERN), self.media_length_edit
            )
        )
        # One of the two is hidden, and takes no room.
        self.media_length_field = QWidget()
        layout = QHBoxLayout(self.media_length_field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(value_label)
        layout.addWidget(self.media_length_edit)
        return self.media_length_field

    def on_media_duration_changed(
        self, duration: float, is_confirmation: bool = False
    ) -> None:
        # This is posted before Get.MEDIA_DURATION serves the new length.
        self.update_read_only_fields(media_length=duration)

    def update_read_only_fields(self, media_length: float | None = None) -> None:
        for name, getter in self.READ_ONLY_FIELDS.items():
            value = getter()
            if name == "media length" and media_length is not None:
                value = media_length
            if name in self.fields_to_formatters:
                value = self.fields_to_formatters[name](value)
            self.read_only_labels[name].setText(value)

        # A length typed but not applied is dropped: the one it was to replace
        # has changed, and media may have been loaded.
        self.media_length_original = self.read_only_labels["media length"].text()
        self.media_length_edit.setText(self.media_length_original)
        is_media_loaded = bool(get(Get.MEDIA_PATH))
        self.read_only_labels["media length"].setVisible(is_media_loaded)
        self.media_length_edit.setVisible(not is_media_loaded)

    def setup_buttons(self):
        edit_notes_button = QPushButton("Edit notes...")
        # Like Apply and Cancel, so that Enter in a field doesn't click it.
        edit_notes_button.setAutoDefault(False)
        edit_notes_button.clicked.connect(self.on_edit_notes_button)
        self.form_layout.addRow(edit_notes_button)

        edit_fields_button = QPushButton("Edit fields...")
        edit_fields_button.setAutoDefault(False)
        edit_fields_button.clicked.connect(self.on_edit_metadata_fields_button)
        self.form_layout.addRow(edit_fields_button)

    def on_edit_notes_button(self):
        dialog = EditNotesDialog(self)
        accepted = dialog.exec()
        if accepted:
            post(Post.MEDIA_METADATA_FIELD_SET, "notes", dialog.get_result())

    def on_edit_metadata_fields_button(self):
        edited_fields = self._get_edits()
        if edited_fields and not get(
            Get.FROM_USER_YES_OR_NO,
            "Save metadata edits",
            "Leave window without saving changes?",
        ):
            return
        self._save_edits(edited_fields)
        dialog = EditMetadataFieldsDialog(self)
        accepted = dialog.exec()
        if accepted:
            valid_fields, invalid_fields = dialog.get_result()
            if invalid_fields:
                self.display_invalid_field_error(invalid_fields)

            self.update_metadata_fields(valid_fields)
            self.refresh_fields()

    @staticmethod
    def display_invalid_field_error(invalid_fields: list[str]):
        tilia.errors.display(
            tilia.errors.METADATA_FIELD_INVALID, "\n".join(invalid_fields)
        )

    def refresh_fields(self) -> None:
        self.clear_layout()
        self._setup_fields()

    def focus(self):
        pass  # TODO: set focus on self

    def reject(self) -> None:
        # Escape: like Cancel, through closeEvent, which asks about edits not
        # applied and lets the window be opened again.
        self.close()

    def closeEvent(self, event):
        edited_fields = self._get_edits()
        if edited_fields and not get(
            Get.FROM_USER_YES_OR_NO,
            "Save metadata edits",
            "Close window without saving changes?",
        ):
            event.ignore()
            return
        stop_listening_to_all(self)
        post(Post.WINDOW_CLOSE_DONE, WindowKind.MEDIA_METADATA)
        # Not QDialog.closeEvent, which would call reject() again.
        event.accept()

    def update_metadata_fields(self, new_fields: list[str]):
        fields_without_required = [
            item
            for item in self.metadata.keys()
            if item not in get(Get.MEDIA_METADATA_REQUIRED_FIELDS)
        ]

        if not fields_without_required == new_fields:
            # The edit-fields dialog is a plain text box, so a rename can only
            # be told apart from a removal plus an addition by comparing the
            # old and new lists. Only a same-length list where a name at some
            # position is gone and its replacement is new counts as a rename;
            # removals, insertions and reorders shift positions and must keep
            # each value under its own name.
            renamed_fields = (
                {
                    old_name: new_name
                    for old_name, new_name in zip(
                        fields_without_required, new_fields, strict=True
                    )
                    if old_name != new_name
                    and old_name not in new_fields
                    and new_name not in fields_without_required
                }
                if len(fields_without_required) == len(new_fields)
                else {}
            )
            post(
                Post.METADATA_UPDATE_FIELDS,
                get(Get.MEDIA_METADATA_REQUIRED_FIELDS) + new_fields,
                renamed_fields=renamed_fields,
            )

    def apply_fields(self):
        self._save_edits(self._get_edits())
        self.clear_layout()
        self._setup_fields()

    def _get_edits(self) -> dict:
        edits = {
            name: self.metadata[name].text()
            for name in self.metadata
            if name in self.metadata_original
            and self.metadata[name].text() != self.metadata_original[name]
        }
        # Compared as times: the length shown is rounded to a tenth of a
        # second, and typing it back changes nothing.
        length_text = self.media_length_edit.text()
        if parse_media_time(length_text) != parse_media_time(
            self.media_length_original
        ):
            edits["media length"] = length_text
        return edits

    def _save_edits(self, edited_fields: dict) -> None:
        edited_fields = dict(edited_fields)
        media_length = edited_fields.pop("media length", None)
        for name, value in edited_fields.items():
            post(Post.MEDIA_METADATA_FIELD_SET, name, value)
        # Last, so that the undo step it records holds the other edits too.
        if media_length is not None:
            self._set_media_length(media_length)

    @staticmethod
    def _set_media_length(text: str) -> None:
        if not text:
            tilia.errors.display(tilia.errors.MEDIA_LENGTH_EMPTY)
            return
        length = parse_media_time(text)
        if length is None or length <= 0:
            tilia.errors.display(tilia.errors.MEDIA_METADATA_SET_DATA_FAILED, text)
            return
        if length == get(Get.MEDIA_DURATION):
            return
        # As the dialog for adding a timeline without media and the command
        # line do, so that it asks whether to scale the timelines the same way.
        post(Post.PLAYER_DURATION_AVAILABLE, length, scale_timelines="prompt")
        post(Post.APP_STATE_RECORD, "media length set")
