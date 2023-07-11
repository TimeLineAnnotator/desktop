import sys
import tkinter as tk
from tkinter import scrolledtext as tk_scrolledtext
import tkinter.font as tk_font

import logging
from collections import OrderedDict
from typing import Any

from tilia.requests import get, Get, listen, post, Post
from tilia.ui.windows import WindowKind
from tilia.ui.common import destroy_children_recursively, format_media_time

logger = logging.getLogger(__name__)

PERMANENT_FIELDS = ["notes"]


class LabelAndEntry(tk.Frame):
    """Create a tk.Label(), tk.Entry() pair and a associated tk.StrVar()"""

    width = 32

    def __init__(self, parent, label, attr_to_link=None):
        super().__init__(parent)
        label_text = label + ":"
        self.label = tk.Label(parent, text=label_text)

        self.entry = tk.Entry(parent)
        self.entry_var = tk.StringVar()
        self.entry.config(textvariable=self.entry_var)

        self.linked_attr = attr_to_link


class MediaMetadataWindow:
    """Configure top parent on Edit>Metadata... menu"""

    KIND = WindowKind.MEDIA_METADATA

    NON_EDITABLE_FIELDS = ["media_path", "media length"]
    SEPARATE_WINDOW_FIELDS = ["notes"]

    def __init__(
        self,
        parent: tk.Tk,
        media_metadata: OrderedDict,
    ):
        self.non_editable_fields = {
            "media length": get(Get.MEDIA_DURATION),
            "media path": get(Get.MEDIA_PATH),
        }

        self.fields_to_formatters = {"media length": format_media_time}

        self.mf_window = None
        self.notes_window = None
        logger.debug("Opening media metadata window... ")

        self.toplevel = tk.Toplevel(parent)
        self.toplevel.transient(parent)
        self.toplevel.title("Media metadata")
        self.toplevel.protocol("WM_DELETE_WINDOW", self.destroy)
        self.media_metadata = media_metadata

        self.widgets_to_varnames = None
        self.fieldnames_to_widgets = None
        self.row_count = 0
        self.setup_widgets()

        self.focus()

        post(Post.METADATA_WINDOW_OPENED)

    def make_editable_row(
        self, label: str, value: Any
    ) -> tuple[tk.Label, tk.Entry, tk.StringVar]:
        entry = tk.Entry(self.toplevel)
        entry.str_var = tk.StringVar()
        entry.config(textvariable=entry.str_var)
        entry.insert(0, value)
        entry.str_var.trace_add("write", self.on_entry_edited)

        label = tk.Label(self.toplevel, text=label + ":")

        return label, entry, entry.str_var

    def make_non_editable_row(self, label: str, value: Any) -> tuple[tk.Label, tk.Text]:
        label = tk.Label(self.toplevel, text=label)
        text_widget = tk.Text(self.toplevel, height=1, borderwidth=0, width=40)

        text_widget.insert(1.0, value)
        if sys.platform in ['linux', 'darwin']:
            # may look ugly, but ensures that text will be visible when in dark mode
            text_widget.config(state="disabled")
        else:
            text_widget.config(state="disabled", font=("Arial", 10), bg="#F0F0F0")

        return label, text_widget

    def grid_row(self, left_widget: tk.Widget, right_widget: tk.Widget) -> None:
        left_widget.grid(row=self.row_count, column=0, sticky=tk.W)
        right_widget.grid(row=self.row_count, column=1, padx=5, pady=2, sticky=tk.EW)
        self.row_count += 1

    def update_dicts(self, field_name: str, entry: tk.Entry, str_var: tk.StringVar):
        self.fieldnames_to_widgets[field_name] = entry
        self.widgets_to_varnames[str(str_var)] = field_name

    def setup_widgets(self) -> None:
        self.row_count = 0
        self.fieldnames_to_widgets = {}
        self.widgets_to_varnames = {}

        self.toplevel.grid_columnconfigure(1, weight=1)

        # setup editable fields
        for field_name, value in self.media_metadata.items():
            if field_name in self.SEPARATE_WINDOW_FIELDS + self.NON_EDITABLE_FIELDS:
                continue
            elif field_name in self.fields_to_formatters:
                value = self.fields_to_formatters[field_name](value)

            label, entry, str_var = self.make_editable_row(
                field_name.capitalize(), value
            )

            self.grid_row(label, entry)
            self.update_dicts(field_name, entry, str_var)

        # setup non-editable fields
        for field_name, value in self.non_editable_fields.items():
            if field_name in self.fields_to_formatters:
                value = self.fields_to_formatters[field_name](value)

            label, text_widget = self.make_non_editable_row(
                field_name.capitalize(), value
            )
            self.grid_row(label, text_widget)

            self.fieldnames_to_widgets[field_name] = text_widget
            self.widgets_to_varnames[value] = field_name

        # setup notes field
        notes_label = tk.Label(self.toplevel, text="Notes:")
        notes_button = tk.Button(
            self.toplevel,
            text="Open notes...",
            command=self.on_notes_button,
        )

        self.grid_row(notes_label, notes_button)

        # setup edit metadata fields button
        edit_metadata_fields_button = tk.Button(
            self.toplevel,
            text="Edit metadata fields...",
            command=self.on_edit_metadata_fields_button,
        )

        edit_metadata_fields_button.grid(
            row=len(self.media_metadata) + len(self.non_editable_fields) + 1,
            column=0,
            columnspan=2,
            pady=(10, 5),
        )

    def on_edit_metadata_fields_button(self):
        logger.debug("User requested to open edit metadata fields window.")
        if self.mf_window:
            logger.debug("Window is already open.")
            return

        self.mf_window = EditMetadataFieldsWindow(
            self, self.toplevel, list(self.media_metadata)
        )
        self.mf_window.wait_window()
        self.refresh_fields()
        self.mf_window = None

    def on_metadata_edited(self, field_name: str, value: str | float) -> None:
        if field_name == "notes":
            logger.debug(f"Updating metadata value on {self}")
            self.media_metadata["notes"] = value

    def on_notes_button(self):
        logger.debug("User requested to open notes window.")
        if self.notes_window:
            logger.debug("Window is already open.")
            return

        listen(self, Post.REQUEST_SET_MEDIA_METADATA_FIELD, self.on_metadata_edited)

        self.notes_window = NotesWindow(self.toplevel, self.media_metadata["notes"])
        self.notes_window.wait_window()
        self.refresh_fields()
        self.notes_window = None

    def refresh_fields(self) -> None:
        destroy_children_recursively(self.toplevel)
        self.setup_widgets()

    def on_entry_edited(self, var_name: str, *_):
        logger.debug("Media metadata entry edited.")
        field_name = self.widgets_to_varnames[var_name]
        logger.debug(f"Field name is '{field_name}'")
        entry = self.fieldnames_to_widgets[field_name]
        value = entry.get()
        logger.debug(f"Value is '{value}'")
        post(Post.REQUEST_SET_MEDIA_METADATA_FIELD, field_name, value)

    def focus(self):
        self.toplevel.focus_set()

    def destroy(self):
        self.toplevel.destroy()
        post(Post.METADATA_WINDOW_CLOSED)

    def update_metadata_fields(self, new_fields: list[str]):
        metadata_fields = list(self.media_metadata)

        if metadata_fields == new_fields:
            return

        new_metadata = {f: "" for f in new_fields}

        for i, field in enumerate(new_fields):
            if field not in metadata_fields:
                post(Post.REQUEST_ADD_MEDIA_METADATA_FIELD, field, i)
            else:
                new_metadata[field] = self.media_metadata[field]

        for field in metadata_fields:
            if field not in new_fields:
                post(Post.REQUEST_REMOVE_MEDIA_METADATA_FIELD, field)

        self.media_metadata = new_metadata


class EditMetadataFieldsWindow(tk.Toplevel):
    def __init__(
        self,
        metadata_window: MediaMetadataWindow,
        metadata_toplevel: tk.Toplevel,
        metadata_fields: list[str],
    ):
        super().__init__()
        self.title("Edit metadata fields")
        self.metadata_window = metadata_window
        self.transient(metadata_toplevel)

        self.scrolled_text = tk_scrolledtext.ScrolledText(self)
        self.scrolled_text.insert(1.0, self.get_metadata_fields_as_str(metadata_fields))
        self.scrolled_text.pack()

        self.button_frame = tk.Frame(self)
        self.button_frame.pack()

        self.cancel_button = tk.Button(
            self.button_frame, text="Cancel", command=self.on_cancel
        )
        self.save_button = tk.Button(
            self.button_frame, text="Save", command=self.on_save
        )

        self.cancel_button.pack(pady=5, padx=5, side=tk.LEFT)
        self.save_button.pack(pady=5, padx=5, side=tk.RIGHT)

    @staticmethod
    def get_metadata_fields_as_str(metadata_fields: list[str]):
        metadata_str = ""
        for field in metadata_fields:
            metadata_str += field + "\n"

        return metadata_str[:-1]

    def on_cancel(self) -> None:
        print("Cancelling changes")
        self.destroy()

    def on_save(self) -> None:
        new_metadata_fields = self.get_metadata_fields_from_widget()
        self.metadata_window.update_metadata_fields(new_metadata_fields)
        self.destroy()

    def get_metadata_fields_from_widget(self):
        fields_list = list(
            map(lambda x: x.strip(), self.scrolled_text.get(1.0, "end-1c").split("\n"))
        )
        fields_list += PERMANENT_FIELDS
        return list(filter(lambda x: x != "", fields_list))


class NotesWindow(tk.Toplevel):
    def __init__(self, metadata_toplevel: tk.Toplevel, notes_metadata_value: str):
        super().__init__(metadata_toplevel)
        self.transient(metadata_toplevel)
        self.title("Notes")

        self.scrolled_text = tk_scrolledtext.ScrolledText(self)
        self.scrolled_text.insert(1.0, notes_metadata_value)
        self.scrolled_text.pack()
        self.scrolled_text.bind("<<Modified>>", self.on_notes_edited)

    def on_notes_edited(self, *_):
        if self.scrolled_text.edit_modified():
            post(
                Post.REQUEST_SET_MEDIA_METADATA_FIELD,
                "notes",
                self.get_notes(),
            )

            self.scrolled_text.edit_modified(False)

    def get_notes(self):
        return self.scrolled_text.get(1.0, "end-1c")
