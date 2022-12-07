import tkinter as tk
from tkinter import scrolledtext

import logging
from collections import OrderedDict

from tilia import events
from tilia.events import EventName
from tilia.ui.tkinter.windows import WindowKind, UniqueWindowDuplicate
from tilia.ui.tkinter.common import destroy_children_recursively

logger = logging.getLogger(__name__)

PERMANENT_FIELDS = ['notes']

class LabelAndEntry(tk.Frame):
    """Create a tk.Label(), tk.Entry() pair and a associated tk.StrVar()"""

    width = 32

    def __init__(self, parent, label, attr_to_link=None):

        super(LabelAndEntry, self).__init__(parent)
        label_text = label + ":"
        self.label = tk.Label(parent, text=label_text)

        self.entry = tk.Entry(parent)
        self.entry_var = tk.StringVar()
        self.entry.config(textvariable=self.entry_var)

        self.linked_attr = attr_to_link


class MetadataWindow:
    """Configure top frame on Edit>Metadata... menu"""

    _instanced = False
    KIND = WindowKind.METADATA

    NON_EDITABLE_FIELDS = ['media_path', 'media length']
    SEPARATE_WINDOW_FIELDS = ['notes']

    def __init__(self, app_ui, media_metadata: OrderedDict, non_editable_fields: OrderedDict):
        # super(MetadataFrame, self).__init__(parent, width=300, height=0)

        if self._instanced:
            raise UniqueWindowDuplicate(self.KIND)

        logger.debug(f"Opening manage timelines window... ")
        logger.debug(f"{media_metadata=}")

        self._app_ui = app_ui

        self._toplevel = tk.Toplevel()
        self._toplevel.title("Manage timelines")
        self._toplevel.protocol("WM_DELETE_WINDOW", self.destroy)
        self._metadata = media_metadata
        self._non_editable_fields = non_editable_fields

        self.setup_widgets()

        MetadataWindow._instanced = True

        events.post(EventName.METADATA_WINDOW_OPENED)

    def setup_widgets(self) -> None:

        self.fieldnames_to_widgets = {}
        self.widgets_to_varnames = {}

        self._toplevel.grid_columnconfigure(1, weight=1)

        # setup customizable fields
        row_number = 0
        for field_name in self._metadata:

            if field_name in self.SEPARATE_WINDOW_FIELDS:
                continue

            label_and_entry = LabelAndEntry(self._toplevel, field_name.capitalize())
            left_widget = label_and_entry.label
            right_widget = label_and_entry.entry
            right_widget.insert(0, self._metadata[field_name])
            value_var = label_and_entry.entry_var
            value_var.trace_add("write", self.on_entry_edited)

            left_widget.grid(row=row_number, column=0, sticky=tk.W)
            right_widget.grid(row=row_number, column=1, padx=5, pady=2, sticky=tk.EW)
            row_number += 1

            self.fieldnames_to_widgets[field_name] = right_widget
            self.widgets_to_varnames[str(value_var)] = field_name


        for field_name, value in self._non_editable_fields.items():
            left_widget = tk.Label(self._toplevel, text=field_name.capitalize())
            right_widget = tk.Text(self._toplevel, height=1, borderwidth=0, width=40)
            right_widget.insert(1.0, value)
            right_widget.config(state='disabled', font=('Arial', 9), bg='#F0F0F0')

            left_widget.grid(row=row_number, column=0, sticky=tk.W)
            right_widget.grid(row=row_number, column=1, padx=5, pady=2, sticky=tk.EW)
            row_number += 1

            self.fieldnames_to_widgets[field_name] = right_widget
            self.widgets_to_varnames[value] = field_name


        # setup notes field
        notes_label = tk.Label(self._toplevel, text='Notes:')
        notes_button = tk.Button(
            self._toplevel,
            text='Open notes...',
            command=lambda: NotesWindow(
                self._toplevel,
                self._metadata['notes']
            )
        )

        notes_label.grid(row=row_number + 1, column=0, sticky=tk.W)
        notes_button.grid(row=row_number + 1, column=1, padx=5, pady=2, sticky=tk.EW)

        # def on_ctrl_z(event):
        #     """To be called when Ctrl+z is pressed with Metadata window open"""
        #     app_globals.METADATA.state_stack.undo()
        #     # reinsert values in windows entries
        #     self.load()
        #
        # def on_ctrl_y(event):
        #     """To be called when Ctrl+y is pressed with Metadata window open"""
        #     app_globals.METADATA.state_stack.redo()
        #     # reinsert values in windows entries
        #     self.load()
        #
        # self.bind('<Control-z>', on_ctrl_z)
        # self.bind('<Control-y>', on_ctrl_y)

        self._edit_metadata_fields_button = tk.Button(
            self._toplevel,
            text='Edit metadata fields...',
            command=self.on_edit_metadata_fields_button
        )
        self._edit_metadata_fields_button.grid(row=len(self._metadata) + len(self._non_editable_fields) + 1, column=0, columnspan=2, pady=(0, 5))

    def on_edit_metadata_fields_button(self):
        mfw = EditMetadataFieldsWindow(self, self._toplevel, list(self._metadata))
        mfw.wait_window()
        self.refresh_fields()

    def refresh_fields(self) -> None:
        destroy_children_recursively(self._toplevel)
        self.setup_widgets()

    def on_entry_edited(self, var_name: str, *_):
        field_name = self.widgets_to_varnames[var_name]
        entry = self.fieldnames_to_widgets[field_name]
        events.post(
            EventName.METADATA_FIELD_EDITED, field_name, entry.get()
        )

    def destroy(self):
        self._toplevel.destroy()
        MetadataWindow._instanced = False

    def update_metadata_fields(self, new_fields: list[str]):

        if list(self._metadata) == new_fields:
            return

        new_metadata = OrderedDict()
        for field in new_fields:
            new_metadata[field] = ''

            if field in self._metadata:
                new_metadata[field] = self._metadata[field]

        self._metadata = new_metadata


class EditMetadataFieldsWindow(tk.Toplevel):
    def __init__(self, metadata_window: MetadataWindow, metadata_toplevel: tk.Toplevel, metadata_fields: list[str]):
        super().__init__()
        self.title('Edit metadata fields')
        self.metadata_window = metadata_window
        self.transient(metadata_toplevel)

        self.scrolled_text = tk.scrolledtext.ScrolledText(self)
        self.scrolled_text.insert(1.0, self.get_metadata_fields_as_str(metadata_fields))
        self.scrolled_text.pack()

        self.button_frame = tk.Frame(self)
        self.button_frame.pack()

        self.cancel_button = tk.Button(self.button_frame, text='Cancel', command=self.on_cancel)
        self.save_button = tk.Button(self.button_frame, text='Save', command=self.on_save)

        self.cancel_button.pack(pady=5, padx=5, side=tk.LEFT)
        self.save_button.pack(pady=5, padx=5, side=tk.RIGHT)

    @staticmethod
    def get_metadata_fields_as_str(metadata_fields: list[str]):
        metadata_str = ''
        for field in metadata_fields:
            metadata_str += field + '\n'

        return metadata_str[:-1]


    def on_cancel(self) -> None:
        print('Cancelling changes')
        self.destroy()

    def on_save(self) -> None:
        new_metadata_fields = self.get_metadata_fields_from_widget()
        self.metadata_window.update_metadata_fields(new_metadata_fields)
        events.post(EventName.METADATA_NEW_FIELDS, new_metadata_fields)
        self.destroy()

    def get_metadata_fields_from_widget(self):
        fields_list = list(map(lambda x: x.strip(), self.scrolled_text.get(1.0, 'end-1c').split('\n')))
        fields_list += PERMANENT_FIELDS
        return list(filter(lambda x: x != '', fields_list))


class NotesWindow(tk.Toplevel):
    def __init__(
            self,
            metadata_toplevel: tk.Toplevel,
            notes_metadata_value: str
    ):
        super().__init__(metadata_toplevel)
        self.transient(metadata_toplevel)
        self.title('Notes')

        self.scrolled_text = tk.scrolledtext.ScrolledText(self)
        self.scrolled_text.insert(1.0, notes_metadata_value)
        self.scrolled_text.pack()
        self.scrolled_text.bind("<<Modified>>", self.on_notes_edited)

    def on_notes_edited(self, *_):
        if self.scrolled_text.edit_modified():

            events.post(
                EventName.METADATA_FIELD_EDITED,
                'notes',
                self.scrolled_text.get(1.0, 'end-1c')
            )

            self.scrolled_text.edit_modified(False)