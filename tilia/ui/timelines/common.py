from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Generic, TypeVar

from tilia.ui.canvas_tags import CURSOR_ARROWS, CURSOR_HAND, TAG_TO_CURSOR

if TYPE_CHECKING:
    pass

import logging

logger = logging.getLogger(__name__)
import tkinter as tk
import tkinter.messagebox

from tilia.events import Event, subscribe
from tilia.timelines.common import log_object_creation

SomeTimelineComponent = TypeVar("SomeTimelineComponent", bound="TimelineComponent")
SomeTimelineUI = TypeVar("SomeTimelineUI", bound="TimelineUI")


class TimelineCanvas(tk.Canvas):
    """Interface for the canvas that composes a timeline.
    Is, right now, an actual tk.Canvas. Will hopefully be replaced with a class that redirects
    draw requests to the appropriate coords in a single canvas for all the timelines."""

    DEFAULT_BG = "#FFFFFF"
    LABEL_PAD = 20

    @log_object_creation
    def __init__(
        self,
        parent: tk.Frame,
        scrollbar: tk.Scrollbar,
        width: int,
        left_margin_width: int,
        height: int,
        initial_name: str,
    ):
        super().__init__(
            parent,
            height=height,
            width=width,
            bg=self.DEFAULT_BG,
            highlightthickness=0,
        )

        subscribe(self, Event.ROOT_WINDOW_RESIZED, self.on_root_window_resized)

        self._label_width = left_margin_width

        self._setup_label(initial_name)

        self.config(scrollregion=(0, 0, width, height))
        self.config(xscrollcommand=scrollbar.set)
        self.focus_set()

        self._setup_cursors()

    def _setup_cursors(self):
        for tag, cursor_name in TAG_TO_CURSOR.items():
            self.tag_bind(
                tag, "<Enter>", lambda x, name=cursor_name: self.config(cursor=name)
            )
            self.tag_bind(tag, "<Leave>", lambda x: self.config(cursor=""))

    def _setup_label(self, initial_name: str):
        self.label_bg = self.create_rectangle(
            *self._get_label_bg_coords, fill="white", width=0
        )

        self.label_in_canvas = self.create_text(
            self._get_label_coords, anchor="nw", text=initial_name
        )

    def update_label(self, new_name: str):
        self.itemconfig(self.label_in_canvas, text=new_name)

    def update_height(self, new_height: int):
        self.config(height=new_height)
        self.coords(self.label_in_canvas, self._get_label_coords)

    def on_root_window_resized(self, width: int, _):
        try:
            self.config(width=width)
        except tkinter.TclError:
            # canvas does not exist, for some reason
            pass

    @property
    def _get_label_coords(self):
        return self.LABEL_PAD, self.winfo_reqheight() / 2

    @property
    def _get_label_bg_coords(self):
        return 0, 0, self._label_width, self.winfo_reqheight()


class TimelineUIElement(ABC):
    """Interface for the tkinter ui objects corresponding to to a TimelineComponent instance.
    E.g.: the HierarchyUI in the ui element corresponding to the Hierarchy timeline component."""

    def __init__(
        self,
        *args,
        tl_component: Generic[SomeTimelineComponent],
        timeline_ui: Generic[SomeTimelineUI],
        canvas: tk.Canvas,
        **kwargs,
    ):
        super().__init__()

        self.tl_component = tl_component
        self.timeline_ui = timeline_ui
        self.id = timeline_ui.get_id()
        self.canvas = canvas

    @abstractmethod
    def delete(self):
        ...


class TimelineToolbar(tk.LabelFrame):
    """
    Toolbar that enables users to edit TimelineComponents.
    Keeps track of how maby timeilnes of a certain kind are instanced and hides itself
    in case there are none.
    There must be only one instance of a toolbar of a certain kind at any given moment.
    """

    PACK_ARGS = {"side": "left"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.button_info = None
        self.visible = False
        self._visible_timelines_count = 0

    def create_buttons(self):
        if not self.button_info:
            raise ValueError(f"No button info found for {self}")

        for info in self.button_info:
            file_name, callback, tooltip_text = info[:3]

            # sets attribute with same name as image
            setattr(
                self,
                file_name,
                tk.PhotoImage(master=self, file=Path("ui", "img", f"{file_name}.png")),
            )

            # create and pack a button with img as image and command = f'on_{img}'
            button = tk.Button(
                self,
                image=getattr(self, file_name),
                borderwidth=0,
                command=callback,
                takefocus=False,
            )

            button.pack(side=tk.LEFT, padx=6)
            create_tool_tip(button, tooltip_text)

            # if attribute name is provided, set button as toolbar attribute to allow future modification.
            try:
                setattr(self, info[3] + "_button", button)
            except IndexError:
                pass

    def _increment_decrement_timelines_count(self, increment: bool) -> None:
        """Increments timelines count if 'increment' is True,
        decrements timelines count if 'increment' is False.

        Raises ValueError if final count is negative."""
        if increment:
            logging.debug(f"Incremeting visible timelines count...")
            self._visible_timelines_count += 1
        else:
            logging.debug(f"Decrementing visible timelines count...")
            self._visible_timelines_count -= 1

        if self._visible_timelines_count < 0:
            raise ValueError(
                f"Visible timeline count of {self} decremented below zero."
            )

        logging.debug(
            f"New is_visible timeline count is {self._visible_timelines_count}"
        )

    def process_visiblity_change(self, visible: bool):
        """increments or decrements is_visible timeline count accordingly.
        Hides toolbar if final count > 1, displays toolbar if count = 0"""
        self._increment_decrement_timelines_count(visible)
        self._show_display_according_to_visible_timelines_count()

    def _show_display_according_to_visible_timelines_count(self):
        if self._visible_timelines_count > 0 and not self.visible:
            logging.debug(f"Displaying toolbar.")
            self.visible = True
            self.pack(**self.PACK_ARGS)
        elif self._visible_timelines_count == 0 and self.visible:
            logging.debug(f"Hiding toolbar.")
            self.visible = False
            self.pack_forget()

    def on_timeline_delete(self):
        """Decrements visible count and hides timelines if count reaches zero."""
        self._increment_decrement_timelines_count(False)
        self._show_display_according_to_visible_timelines_count()

    def on_timeline_create(self):
        self._increment_decrement_timelines_count(True)
        self._show_display_according_to_visible_timelines_count()

    def delete(self):
        logger.debug(f"Deleting timeline toolbar {self}.")
        self.destroy()


class ToolTip(object):
    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None
        self.id = None
        self.text = ""
        self.label = None

    def showtip(self, text):
        """Display text in tooltip window"""

        self.text = text
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + self.widget.winfo_width() - 5
        y = y + cy + self.widget.winfo_rooty() + self.widget.winfo_height() - 5

        self.tipwindow = tw = tk.Toplevel(self.widget)

        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        self.label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("tahoma", "8", "normal"),
        )
        self.label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

    def change_tip_text(self, new_text: str) -> None:
        self.label.config(text=new_text)


def create_tool_tip(widget, text):
    toolTip = ToolTip(widget)

    def enter(_):
        toolTip.showtip(text)

    def leave(_):
        toolTip.hidetip()

    widget.bind("<Enter>", enter)
    widget.bind("<Leave>", leave)
