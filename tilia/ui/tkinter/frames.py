from __future__ import annotations

from tilia.ui.tkinter.common import LabelAndEntry


import tkinter as tk
from tkinter import scrolledtext

from tilia import globals_

import logging

logger = logging.getLogger(__name__)

LOGGER = logging.getLogger(__name__)


class MetadataLabelAndEntry(LabelAndEntry):
    def __init__(self, parent, title, trace_func=""):
        super(MetadataLabelAndEntry, self).__init__(parent, title)
        self.metadata_field = ""

    def change_field(self, x=None, y=None, z=None, field=None):
        """Callback to change MediaMetadata field"""

        globals_.METADATA.state_stack.record(
            f"metadata_edit - {str(self.metadata_field)}: {getattr(globals_.METADATA, self.metadata_field)}"
        )

        setattr(globals_.METADATA, self.metadata_field, self.entry_var.get())


class MetadataFrame(tk.Toplevel):
    """Configure top parent on Edit>MediaMetadata... menu"""

    def __init__(self, parent):
        super(MetadataFrame, self).__init__(parent, width=300, height=0)
        self.load()
        self.metadata = globals_.APP._media_metadata
        self.transient(parent)

    def load(self):
        # tuple containing (field name, widget type, corresponding attribute)
        label_entry_list = [
            ("Title", "entry", "title"),
            ("Composer", "entry", "composer"),
            ("Tonality", "entry", "tonality"),
            ("Time signature", "entry", "time_signature"),
            ("Comp. year", "entry", "composition_year"),
            ("Performer", "entry", "performer"),
            ("Perf. year", "entry", "performance_year"),
            ("Audio path", "label", globals_.CURRENT_AUDIO),
            ("Audio length", "label", globals_.CONVERTED_AUDIO_LENGTH),
            ("Form", "entry", "form"),
        ]

        for row_count, field in enumerate(label_entry_list):
            if field[1] == "entry":
                attr = field[0].lower()
                label_and_entry = MetadataLabelAndEntry(self, field[0])

                setattr(self, attr, label_and_entry)
                label_and_entry.metadata_field = field[2]
                label_and_entry.entry_var.set(getattr(globals_.METADATA, field[2]))
                label_and_entry.entry_var.trace_add(
                    "write", label_and_entry.change_field
                )

                widget1 = label_and_entry.label
                widget2 = label_and_entry.entry

            elif field[1] == "label":
                widget1 = tk.Label(self, text=f"{field[0]}:")
                widget2 = tk.Text(self, height=1, borderwidth=0, width=40)
                try:
                    widget2.insert(1.0, field[2])
                except tk.TclError:
                    widget2.insert(1.0, "ERROR WHEN INSERTING VALUE.")
                widget2.config(state="disabled", font=("Arial", 9), bg="#F0F0F0")

            widget1.grid(row=row_count, column=0, sticky=tk.W)
            widget2.grid(row=row_count, column=1, padx=5, pady=2, sticky=tk.EW)

        self.grid_columnconfigure(1, weight=1)

        # Additional field for unstructured notes
        notes_label = tk.Label(self, text="Notes:")
        notes_button = tk.Button(
            self, text="Open notes...", command=lambda: NotesWindow()
        )

        notes_label.grid(row=len(label_entry_list), column=0, sticky=tk.W)
        notes_button.grid(
            row=len(label_entry_list), column=1, padx=5, pady=2, sticky=tk.EW
        )

        def on_ctrl_z(event):
            """To be called when Ctrl+z is pressed with MediaMetadata window open"""
            globals_.METADATA.state_stack.undo()
            # reinsert values in windows entries
            self.load()

        def on_ctrl_y(event):
            """To be called when Ctrl+y is pressed with MediaMetadata window open"""
            globals_.METADATA.state_stack.redo()
            # reinsert values in windows entries
            self.load()

        self.bind("<Control-z>", on_ctrl_z)
        self.bind("<Control-y>", on_ctrl_y)


class NotesWindow(tk.Toplevel):
    def __init__(self):
        super(NotesWindow, self).__init__(globals_.APP)
        self.transient(globals_.APP)
        self.title("Notes")

        self.scrolled_text = tk.scrolledtext.ScrolledText(self)
        self.scrolled_text.insert(1.0, globals_.METADATA.notes)
        self.scrolled_text.pack()
        self.scrolled_text.bind("<<Modified>>", self.on_modified)

    def on_modified(self, _):
        if not self.scrolled_text.edit_modified():
            return

        globals_.METADATA.notes = self.scrolled_text.get(1.0, "end-1c")
        self.scrolled_text.edit_modified(False)
