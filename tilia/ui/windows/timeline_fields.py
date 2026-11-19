"""The fields window: a timeline's fields, edited like the file's in the Metadata
window (FR-092; `contracts/controls.md`, rows 8 and 9).

A field's value is a text or a list of texts. A list shows its texts separated by
commas, and stays a list when it is edited, split at its commas. The window writes a
field only if its text was edited, and each Apply, or each change of the names, is
one edit that undo covers. `role` and `vocabulary` are fields like any other: TiLiA
checks none of them, and the core warns about what it would warn about on reading.

The window isn't modal: one per timeline, closed when its timeline goes.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from tilia.log import logger
from tilia.requests import Get, Post, get, listen, stop_listening_to_all
from tilia.settings import settings
from tilia.ui import commands

if TYPE_CHECKING:
    from tilia.timelines.base.timeline import Timeline

Fields = dict[str, Any]

TITLE = "Fields of {}"
QUESTION_TITLE = "Save field edits"


def field_text(value: Any) -> str:
    """A field's value as TiLiA shows it: a list's texts separated by commas."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


# The line breaks `str.splitlines` knows, as the warnings dialog has them.
_LINE_BREAK = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85  ]")


def fields_lines(fields: Fields) -> str:
    """A component's fields as its inspector shows them, one line per field:
    `tags: cadence, half` (`contracts/controls.md`, row 10). A line break in a
    name or a value is a space, as in the warnings dialog."""
    return "\n".join(
        _LINE_BREAK.sub(" ", f"{name}: {field_text(value)}")
        for name, value in fields.items()
    )


def field_value(text: str, was: Any) -> Any:
    """The value `text` gives a field whose value was `was`: a list stays a list,
    its texts split at the commas, without the spaces around them or empty ones."""
    if isinstance(was, list):
        return [item.strip() for item in text.split(",") if item.strip()]
    return text


def with_names(fields: Fields, names: list[str]) -> Fields:
    """`fields` with `names` as its names. A name kept keeps its value and its place,
    and a name gone goes. A new one is added last, empty, as the document adds a
    field it didn't have. As in the Metadata window, a list of names as long as
    before, where a name at some place is gone and the one there is new, renames
    that field: it keeps its value, but goes last as any new name does."""
    renamed: dict[str, str] = {}
    if len(names) == len(fields):
        renamed = {
            new: was
            for was, new in zip(fields, names, strict=True)
            if was != new and was not in names and new not in fields
        }
    result = {name: value for name, value in fields.items() if name in names}
    for name in names:
        if name not in result:
            result[name] = (
                copy.deepcopy(fields[renamed[name]]) if name in renamed else ""
            )
    return result


class FieldNamesDialog(QDialog):
    """The names of a timeline's fields, one per line, as the Metadata window's
    "Edit fields..." dialog has the file's."""

    def __init__(self, parent: QWidget, names: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit fields")
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlainText("".join(name + "\n" for name in names))
        layout.addWidget(self.text_edit)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def names(self) -> list[str]:
        """The names typed, as typed: the format takes any name. A blank line is
        skipped, and a name typed twice is one field."""
        names = self.text_edit.toPlainText().split("\n")
        return list(dict.fromkeys(name for name in names if name.strip()))


class TimelineFieldsWindow(QDialog):
    _open: ClassVar[dict[str, TimelineFieldsWindow]] = {}

    @classmethod
    def show_for(cls, timeline_id: str) -> TimelineFieldsWindow:
        """Shows the timeline's window, opening it if it isn't open."""
        window = cls._open.get(timeline_id)
        if window is None:
            window = cls(timeline_id)
            cls._open[timeline_id] = window
        window.show()
        window.activateWindow()
        window.raise_()
        return window

    @classmethod
    def of(cls, timeline_id: str) -> TimelineFieldsWindow | None:
        """The timeline's window, if it is open."""
        return cls._open.get(timeline_id)

    @classmethod
    def open_windows(cls) -> Iterator[TimelineFieldsWindow]:
        return iter(cls._open.values())

    def __init__(self, timeline_id: str) -> None:
        super().__init__(get(Get.MAIN_WINDOW))
        self.timeline_id = timeline_id
        self.line_edits: dict[str, QLineEdit] = {}
        # By name: the value shown, and the text its line edit had then.
        self._shown: dict[str, tuple[Any, str]] = {}
        self._timeline_gone = False
        self.setWindowTitle(TITLE.format(get(Get.TIMELINE, timeline_id).name))
        self.setMinimumSize(settings.get("media_metadata", "window_width"), 0)
        self.setLayout(QVBoxLayout())
        self._setup_widgets()
        self._setup_window_buttons()
        self._setup_fields()
        listen(self, Post.TIMELINE_DELETE_DONE, self.on_timeline_delete_done)

    def _timeline(self) -> Timeline | None:
        return get(Get.TIMELINE, self.timeline_id)

    def _fields(self) -> Fields:
        timeline = self._timeline()
        return timeline.get_data("fields") if timeline is not None else {}

    def _setup_widgets(self) -> None:
        self.form_layout = QFormLayout()
        content = QWidget()
        content.setLayout(self.form_layout)
        self.layout().addWidget(content)

    def _setup_window_buttons(self) -> None:
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        for button in self.button_box.buttons():
            button.setAutoDefault(False)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.apply
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            self.close
        )
        self.layout().addWidget(self.button_box)

    def _setup_fields(self) -> None:
        self.line_edits.clear()
        self._shown.clear()
        for name, value in self._fields().items():
            line_edit = QLineEdit(field_text(value))
            # The Metadata window's label, as plain text: a name is the file's.
            label = QLabel(name.capitalize())
            label.setTextFormat(Qt.TextFormat.PlainText)
            self.form_layout.addRow(label, line_edit)
            self.line_edits[name] = line_edit
            self._shown[name] = (copy.deepcopy(value), line_edit.text())
        self.edit_names_button = QPushButton("Edit fields…")
        # Enter in a field neither applies nor cancels: no button is the default.
        self.edit_names_button.setAutoDefault(False)
        self.edit_names_button.clicked.connect(self.on_edit_names)
        self.form_layout.addRow(self.edit_names_button)
        self.adjustSize()

    def refresh(self) -> None:
        while self.form_layout.rowCount():
            self.form_layout.removeRow(0)
        self._setup_fields()

    def edits(self) -> Fields:
        """The values of the fields whose text was edited."""
        return {
            name: field_value(self.line_edits[name].text(), value)
            for name, (value, text) in self._shown.items()
            if self.line_edits[name].text() != text
        }

    def apply(self) -> None:
        """Writes the values edited, over the timeline's fields as they are now: the
        others stay as they are, whatever TiLiA did to them meanwhile."""
        fields = copy.deepcopy(self._fields())
        fields.update(self.edits())
        self._set_fields(fields)
        self.refresh()

    def _set_fields(self, fields: Fields) -> None:
        # The window closes when its timeline goes, so this is a stale window's.
        timeline_ui = get(Get.TIMELINE_UI, self.timeline_id)
        if timeline_ui is None:
            logger.error(f"No timeline {self.timeline_id} to set the fields of.")
            return
        commands.execute("timeline.set_fields", timeline_ui, fields)

    def on_edit_names(self) -> None:
        if self.edits() and not get(
            Get.FROM_USER_YES_OR_NO,
            QUESTION_TITLE,
            "Leave window without saving changes?",
        ):
            return
        fields = self._fields()
        dialog = FieldNamesDialog(self, list(fields))
        if not dialog.exec():
            return
        self._set_fields(with_names(fields, dialog.names()))
        self.refresh()

    def on_timeline_delete_done(self, timeline_id: str) -> None:
        if timeline_id != self.timeline_id:
            return
        self._timeline_gone = True
        self.close()

    def reject(self) -> None:
        """Escape acts as Cancel, through the close event."""
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            not self._timeline_gone
            and self.edits()
            and not get(
                Get.FROM_USER_YES_OR_NO,
                QUESTION_TITLE,
                "Close window without saving changes?",
            )
        ):
            event.ignore()
            return
        stop_listening_to_all(self)
        if self._open.get(self.timeline_id) is self:
            del self._open[self.timeline_id]
        # Not QDialog's closeEvent, which would call reject() again.
        event.accept()
