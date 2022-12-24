import tkinter as tk
from typing import TYPE_CHECKING

from tilia import events
from tilia.events import Event
from tilia.misc_enums import UpOrDown

if TYPE_CHECKING:
    from tilia.ui.tkinterui import TkinterUI

import logging



logger = logging.getLogger(__name__)


class ManageTimelines:
    def __init__(
        self, app_ui, timeline_ids_and_display_strings: list[tuple[int, str]]
    ):
        """
        Window that allow user to change the order, toggle visibility
        and delete timelines.
        """
        logger.debug(f"Opening manage timelines window... ")

        self._app_ui = app_ui

        self.toplevel = tk.Toplevel()
        self.toplevel.title("Manage timelines")
        self.toplevel.protocol("WM_DELETE_WINDOW", self.on_close)
        self.transient(self._app_ui.root)

        logger.debug(f"Existing timelines ids and display strings are {timeline_ids_and_display_strings}")
        self.tl_ids_and_strings = timeline_ids_and_display_strings

        self._setup_widgets()

        self.list_box.bind("<<ListboxSelect>>", self.on_select)

        self.initial_config()

    def _setup_widgets(self):

        self.outer_frame = tk.Frame(self.toplevel)

        # create right parent
        self.right_frame = tk.Frame(self.outer_frame)
        self.up_button = tk.Button(
            self.right_frame, text="▲", width=3, command=self.move_up
        )
        self.down_button = tk.Button(
            self.right_frame, text="▼", width=3, command=self.move_down
        )
        self.delete_button = tk.Button(
            self.right_frame, text="Delete", command=self.on_delete_button
        )
        # self.clear_button = tk.Button(
        #     self.right_frame, text="Clear", command=self.on_clear_button
        # ) TODO implement clear button

        # create checkbox
        self.visible_checkbox_var = tk.BooleanVar()
        self.visible_checkbox = tk.Checkbutton(
            self.right_frame,
            text="Visible",
            variable=self.visible_checkbox_var,
            onvalue=True,
            offvalue=False,
            command=self.on_checkbox_value_change,
        )

        # grid and pack elements
        self.up_button.grid(column=1, row=0, sticky=tk.EW)
        self.down_button.grid(column=1, row=1, sticky=tk.EW)
        self.visible_checkbox.grid(column=1, row=2, sticky=tk.EW)
        self.delete_button.grid(column=1, row=3, sticky=tk.EW)
        # self.clear_button.grid(column=1, row=4, sticky=tk.EW)

        self.list_box = tk.Listbox(self.outer_frame, width=40, activestyle="none")
        self.list_box.insert(
            "end",
            *[display_str for _, display_str in self.tl_ids_and_strings],
        )

        self.scrollbar = tk.Scrollbar(self.outer_frame, orient=tk.VERTICAL)
        self.scrollbar.config(command=self.list_box.yview)
        self.list_box.config(yscrollcommand=self.scrollbar.set)

        self.right_frame.pack(expand=tk.YES, fill=tk.BOTH, side=tk.RIGHT)
        self.list_box.pack(expand=True, side=tk.LEFT)
        self.scrollbar.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)

        self.toplevel.grid_columnconfigure(0, weight=1)
        self.outer_frame.pack(expand=True)

    def initial_config(self) -> None:
        """Set focus to window and select first element"""
        self.list_box.focus_set()
        self.list_box.select_set(0)
        self.on_select()

    def on_select(self, _=None):
        """Updates checkbox to reflect visibility status of the selected timeline"""
        item = self.list_box.get(self.list_box.curselection())
        index = self.list_box.index(self.list_box.curselection())
        logger.debug(f"Selected manage timelines item '{item}' at index '{index}'")

        selected_timeline_id = self.tl_ids_and_strings[index][0]

        is_visible = self._app_ui.get_timeline_ui_attribute_by_id(selected_timeline_id, 'is_visible')

        if is_visible:
            self.visible_checkbox.select()
        else:
            self.visible_checkbox.deselect()

    def on_checkbox_value_change(self):
        """Toggles visibility of selected timeline"""
        index = self.list_box.index(self.list_box.curselection())
        selected_timeline_id = self.tl_ids_and_strings[index][0]

        is_checked = self.visible_checkbox_var.get()

        if is_checked:
            events.post(Event.TIMELINES_REQUEST_TO_SHOW_TIMELINE, selected_timeline_id)
        else:
            events.post(Event.TIMELINES_REQUEST_TO_HIDE_TIMELINE, selected_timeline_id)

    def move_up(self):
        """Move timeline up"""
        item = self.list_box.get(self.list_box.curselection())
        index = self.list_box.index(self.list_box.curselection())
        if index == 0:
            logger.debug(f"Item is already at top.")
            return

        timeline_id = self.tl_ids_and_strings[index][0]
        self.move_listbox_item(index, item, UpOrDown.UP)
        events.post(Event.TIMELINES_REQUEST_MOVE_UP_IN_DISPLAY_ORDER, timeline_id)

    def move_down(self):
        """Move timeline down"""
        item = self.list_box.get(self.list_box.curselection())
        index = self.list_box.index(self.list_box.curselection())
        if index == self.list_box.index("end") - 1:
            logger.debug(f"Item is already at bottom.")
            return  # already at bottom

        timeline_id = self.tl_ids_and_strings[index][0]
        self.move_listbox_item(index, item, UpOrDown.DOWN)
        events.post(Event.TIMELINES_REQUEST_MOVE_DOWN_IN_DISPLAY_ORDER, timeline_id)

    def move_listbox_item(self, index: int, item: str, direction: UpOrDown) -> None:

        self.list_box.delete(index, index)

        index_difference = direction.value * -1
        self.list_box.insert(index + index_difference, item)
        self.list_box.activate(index + index_difference)
        self.list_box.select_set(index + index_difference)

        self.move_item_in_ids_and_display_string_order(index, direction)

    def move_item_in_ids_and_display_string_order(self, index, direction):

        (
            self.tl_ids_and_strings[index],
            self.tl_ids_and_strings[index - direction.value]
        ) = (
            self.tl_ids_and_strings[index - direction.value],
            self.tl_ids_and_strings[index]
        )


    def on_delete_button(self):
        index = self.list_box.index(self.list_box.curselection())
        timeline_id = self.tl_ids_and_strings[index][0]

        events.post(Event.TIMELINES_REQUEST_TO_DELETE_TIMELINE, timeline_id)

        self.update_tl_ids_and_strings()


    def on_clear_button(self):
        raise NotImplementedError

    def on_close(self):
        self.toplevel.destroy()
        events.post(Event.MANAGE_TIMELINES_WINDOW_CLOSED)

    def update_tl_ids_and_strings(self):
        self.tl_ids_and_strings = self._app_ui.get_timeline_info_for_manage_timelines_window()
        self.list_box.delete(0, "end")
        self.list_box.insert(
            "end",
            *[display_str for _, display_str in self.tl_ids_and_strings],
        )


