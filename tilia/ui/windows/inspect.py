"""
Defines the Inspect class.
A window that allows the user to sse the relevant attributes of a TimelineComponent or its
UI.
"""

from __future__ import annotations

import logging
from tkinter import ttk

import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from tilia import events
from tilia.events import Event, subscribe, unsubscribe_from_all
from tilia.timelines.common import TimelineComponent
from tilia.ui.windows.kinds import WindowKind

PADX = 5
PADY = 5

logger = logging.getLogger(__name__)


class Inspect:
    """
    A window that allows the user to sse the relevant attributes of a TimelineComponent or its UI.
    Listens for a inspectable element selected event and updates according to a dict send alongside it.
    Keeps track of selected inspectable and listens for a deselect inspectable event to allow for
    correct updating.
    """

    KIND = WindowKind.INSPECT

    def __init__(self, parent) -> None:

        subscribe(
            self,
            Event.INSPECTABLE_ELEMENT_SELECTED,
            self.on_timeline_component_selected,
        )
        subscribe(
            self,
            Event.INSPECTABLE_ELEMENT_DESELECTED,
            self.on_timeline_component_deselected,
        )

        self.inspected_objects_stack = []
        self.element_id = ""
        self.toplevel = tk.Toplevel(parent)
        self.toplevel.transient(parent)
        self.toplevel.title("Inspect")
        self.toplevel.protocol("WM_DELETE_WINDOW", self.destroy)
        self.toplevel.focus()

        self.currently_inspected_class = None
        self.fieldname_to_widgets = None
        self.strvar_to_fieldname = None
        self.inspector_frame = tk.Frame(self.toplevel)
        self.inspector_frame.pack()
        self.display_not_selected_frame()

        self.toplevel.bind(
            "<Escape>", lambda _: events.post(Event.REQUEST_FOCUS_TIMELINES)
        )
        events.post(Event.INSPECTOR_WINDOW_OPENED)

    def focus(self):
        self.toplevel.focus_set()

        if self.starting_focus_widget:
            self.starting_focus_widget.focus_set()
            self.starting_focus_widget.selection_range(0, tk.END)

    def destroy(self):
        unsubscribe_from_all(self)
        self.toplevel.destroy()
        events.post(Event.INSPECT_WINDOW_CLOSED)

    def display_not_selected_frame(self):
        tk.Label(
            self.inspector_frame,
            text="No object selected",
            font=("Helvetica", 16),
        ).pack(padx=PADX, pady=PADY)

    def on_timeline_component_selected(
        self,
        element_class: type(TimelineComponent),
        inspector_fields: tuple[str, str],
        inspector_values: dict[str:str],
        element_id: str,
    ):

        self.update_frame(element_class, inspector_fields)
        self.update_values(inspector_values, element_id)
        self.update_inspected_object_stack(
            element_class, inspector_fields, inspector_values, element_id
        )

    def update_inspected_object_stack(self, *uielement_args):
        if uielement_args not in self.inspected_objects_stack:
            self.inspected_objects_stack.append(uielement_args)

    def update_frame(
        self,
        element_class: type(TimelineComponent),
        inspector_fields: tuple[str, str],
    ):
        if element_class != self.currently_inspected_class:
            self.inspector_frame.destroy()
            self.inspector_frame = self.create_inspector_frame(inspector_fields)
            self.inspector_frame.pack(padx=5, pady=5, expand=True, fill=tk.X)
            self.currently_inspected_class = element_class

    def on_timeline_component_deselected(self, element_id: str):
        try:
            element_index = [
                self.inspected_objects_stack.index(obj)
                for obj in self.inspected_objects_stack
                if obj[-1] == element_id
            ][0]
        except IndexError:
            return

        self.inspected_objects_stack.pop(element_index)

        if self.inspected_objects_stack:
            (
                element_class,
                inspector_fields,
                inspector_values,
                element_id,
            ) = self.inspected_objects_stack[-1]

            self.update_frame(element_class, inspector_fields)
            self.update_values(inspector_values, element_id)
        else:
            self.clear_values()
            for _, widget in self.fieldname_to_widgets.items():
                widget.config(state="disabled")

    def update_values(self, field_values: dict[str:str], element_id: str):

        self.element_id = element_id
        for field_name, value in field_values.items():
            try:
                widget = self.fieldname_to_widgets[field_name]
            except KeyError:
                logging.warning(f"Inspect has no field named {field_name}")
                continue

            widget.config(state="normal")
            if type(widget) == tk.Label:
                widget.config(text=value)
            elif type(widget) == tk.Entry:
                # pause strvar trace
                strvar = self.widgets_to_strvars[widget]
                strvar.trace_vdelete('w', strvar.trace_id)
                # change entry value
                widget.delete(0, "end")
                widget.insert(0, value)
                # resume strvar trace
                strvar.trace_id = strvar.trace_add("write", self.on_entry_edited)
            elif type(widget) == ScrolledText:
                widget.delete(1.0, "end")
                widget.insert(1.0, value)
            else:
                raise TypeError(
                    f"Non recognized widget type {type(widget)} for inspector field."
                )

            if self.starting_focus_widget:
                self.starting_focus_widget.selection_range(0, tk.END)

    def clear_values(self):
        clearing_dict = {}
        for key in self.fieldname_to_widgets.keys():
            clearing_dict[key] = ""

        self.update_values(clearing_dict, "id_cleared")

    def create_inspector_frame(self, field_tuples: tuple[str, str]):
        frame = tk.Frame(self.toplevel)
        widget1 = None
        widget2 = None
        self.starting_focus_widget = None
        self.fieldname_to_widgets = {}
        self.strvar_to_fieldname = {}
        self.widgets_to_strvars = {}

        for row, field_tuple in enumerate(field_tuples):
            field_name = field_tuple[0]
            field_kind = field_tuple[1]
            strvar = None
            if field_kind == "entry":

                label_and_entry = LabelAndEntry(frame, field_name)
                widget1 = label_and_entry.label
                widget2 = label_and_entry.entry
                strvar = label_and_entry.entry_var
                strvar.trace_id = strvar.trace_add("write", self.on_entry_edited)
                if not self.starting_focus_widget:
                    self.starting_focus_widget = widget2

            elif field_kind == "label":
                widget1 = tk.Label(frame, text=f"{field_name}:")
                widget2 = tk.Label(frame)
            elif field_kind == "scrolled_text":
                label_and_scrolled_text = LabelAndScrolledText(
                    frame, field_name, self.on_scrolled_text_edited
                )
                widget1 = label_and_scrolled_text.label
                widget2 = label_and_scrolled_text.scrolled_text
                if not self.starting_focus_widget:
                    self.starting_focus_widget = widget2
            elif field_kind == "separator":
                widget1 = tk.Label(frame, text=f"{field_name}")
                widget2 = ttk.Separator(frame, orient=tk.HORIZONTAL)

            widget1.grid(row=row, column=0, sticky=tk.W)
            widget2.grid(row=row, column=1, padx=5, pady=2, sticky=tk.EW)

            self.fieldname_to_widgets[field_name] = widget2
            if strvar:
                self.strvar_to_fieldname[str(strvar)] = field_name
                self.widgets_to_strvars[widget2] = strvar

            frame.columnconfigure(1, weight=1)

            if self.starting_focus_widget:
                self.starting_focus_widget.focus_set()

        return frame

    def on_entry_edited(self, var_name: str, *_):
        field_name = self.strvar_to_fieldname[var_name]
        entry = self.fieldname_to_widgets[field_name]
        events.post(
            Event.INSPECTOR_FIELD_EDITED, field_name, entry.get(), self.element_id
        )

    def on_scrolled_text_edited(self, widget: ScrolledText, value: str):
        fieldname = self.widgets_to_fieldnames[widget]
        logger.debug(f"{fieldname=}")
        logger.debug(f"{value=}")

        events.post(
            Event.INSPECTOR_FIELD_EDITED, fieldname, value, self.element_id
        )

    @property
    def widgets_to_fieldnames(self):
        return {widget: fieldname for fieldname, widget in self.fieldname_to_widgets.items()}


class LabelAndEntry(tk.Frame):
    """Create a tk.Label(), tk.Entry() pair and a associated tk.StrVar()"""

    WIDTH = 32

    def __init__(self, parent, label, attr_to_link=None):
        super().__init__(parent)
        label_text = label + ":"
        self.label = tk.Label(parent, text=label_text)

        self.entry = tk.Entry(parent)
        self.entry_var = tk.StringVar()
        self.entry.config(textvariable=self.entry_var)

        self.linked_attr = attr_to_link


class LabelAndScrolledText:
    HEIGHT = 5
    WIDTH = 20

    def __init__(
        self,
        parent,
        name,
        callback: Callable[[ScrolledText, str], None],
        text: str = "",
    ):
        self.label = tk.Label(parent, text=f"{name}:")
        self.callback = callback
        self.scrolled_text = ScrolledText(parent, height=self.HEIGHT, width=self.WIDTH)
        self.scrolled_text.insert(1.0, text)
        self.scrolled_text.edit_modified(False)
        self.scrolled_text.bind("<<Modified>>", self.on_modified)


    def on_modified(self, _):
        self.callback(self.scrolled_text, self.scrolled_text.get(1.0, 'end-1c'))
        self.scrolled_text.edit_modified(False)