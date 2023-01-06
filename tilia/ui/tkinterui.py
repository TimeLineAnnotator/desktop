"""
Defines the TkinterUI class, which composes the TiLiA object, and its dependencies.
The TkinterUI is responsible for high-level control of the GUI.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Callable
import sys
import tkinter as tk
import tkinter.font
import tkinter.filedialog
import tkinter.messagebox
import tkinter.simpledialog
import time


from tilia import globals_, events, settings
from tilia.player import player_ui
from tilia.exceptions import UserCancelledSaveError, UserCancelledOpenError
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.events import Event, subscribe
from . import file, event_handler
from .common import ask_yes_no, ask_for_directory, format_media_time
from .menus import TkinterUIMenus
from .timelines.collection import TimelineUICollection
from .windows.manage_timelines import ManageTimelines
from .windows.metadata import MediaMetadataWindow
from .windows.about import About
from .windows.inspect import Inspect
from .windows.kinds import WindowKind

if TYPE_CHECKING:
    from tilia.main import TiLiA

import logging

logger = logging.getLogger(__name__)


def handle_exception(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return


    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    # traceback.print_tb(exc_traceback)
    time.sleep(0.1)  # needed so traceback gets fully printed before type and value
    # print(exc_type)
    # print(exc_value)


class TkinterUI:
    """
    Responsible for high-level control of the GUI:
        - Instances the tk.TK object;
        - Is composed of the high level tkinter frames (toolbar parent, timelines parent, etc...);
        - Is composed of the TkinterUIMenus class;
        - Is composed of a TkEventHandler which translates tkinter events into events.py events;
        - Keeps 'global' interface data such as window and timeline dimensions.
    """

    def __init__(self, app: TiLiA):

        subscribe(self, Event.MENU_OPTION_FILE_LOAD_MEDIA, self.on_menu_file_load_media)
        subscribe(
            self,
            Event.UI_REQUEST_WINDOW_INSPECTOR,
            lambda: self.on_request_window(WindowKind.INSPECT),
        )
        subscribe(
            self,
            Event.UI_REQUEST_WINDOW_MANAGE_TIMELINES,
            lambda: self.on_request_window(WindowKind.MANAGE_TIMELINES),
        )
        subscribe(
            self,
            Event.UI_REQUEST_WINDOW_METADATA,
            lambda: self.on_request_window(WindowKind.MEDIA_METADATA),
        )
        subscribe(
            self,
            Event.UI_REQUEST_WINDOW_ABOUT,
            lambda: self.on_request_window(WindowKind.ABOUT),
        )
        subscribe(self, Event.REQUEST_DISPLAY_ERROR, self.on_display_error)
        subscribe(
            self,
            Event.INSPECT_WINDOW_CLOSED,
            lambda: self.on_window_closed(WindowKind.INSPECT),
        )
        subscribe(
            self,
            Event.MANAGE_TIMELINES_WINDOW_CLOSED,
            lambda: self.on_window_closed(WindowKind.MANAGE_TIMELINES),
        )
        subscribe(
            self,
            Event.METADATA_WINDOW_CLOSED,
            lambda: self.on_window_closed(WindowKind.MEDIA_METADATA),
        )
        subscribe(
            self,
            Event.ABOUT_WINDOW_CLOSED,
            lambda: self.on_window_closed(WindowKind.ABOUT),
        )

        subscribe(self, Event.TILIA_FILE_LOADED, self.on_tilia_file_loaded)

        logger.debug("Starting TkinterUI...")

        self._app = app
        self._setup_tk_root()

        self.default_font = tkinter.font.nametofont("TkDefaultFont")

        self.timeline_width = globals_.DEFAULT_TIMELINE_WIDTH
        self.timeline_padx = globals_.DEFAULT_TIMELINE_PADX

        self.window_width = globals_.DEFAULT_WINDOW_WIDTH
        self.window_height = globals_.DEFAULT_WINDOW_HEIGHT

        self._setup_widgets()
        self._setup_menus()

        self._make_default_canvas_bindings()

        self._create_timeline_ui_collection()

        self._windows = {
            WindowKind.INSPECT: None,
            WindowKind.MEDIA_METADATA: None,
            WindowKind.MANAGE_TIMELINES: None,
            WindowKind.ABOUT: None,
        }

        logger.debug("Tkinter UI started.")

    def _setup_tk_root(self):
        self.root = tk.Tk()
        set_startup_geometry(self.root)
        self.root.focus_set()

        self.root.report_callback_exception = handle_exception

        self.root.title(globals_.APP_NAME)
        self.icon = tk.PhotoImage(master=self.root, file=globals_.APP_ICON_PATH)
        self.root.iconphoto(True, self.icon)

        self.root.protocol(
            "WM_DELETE_WINDOW", lambda: events.post(Event.REQUEST_CLOSE_APP)
        )

    def _make_default_canvas_bindings(self) -> None:
        for sequence, callback in event_handler.DEFAULT_CANVAS_BINDINGS:
            self.root.bind_class("Canvas", sequence, callback)

    def _setup_menus(self):
        self.root.config(menu=TkinterUIMenus())

    def launch(self):
        logger.debug("Entering Tkinter UI mainloop.")
        self.root.mainloop()

    @property
    def timeline_total_size(self):
        return self.timeline_width + 2 * self.timeline_padx

    def _create_timeline_ui_collection(self):

        self.timeline_ui_collection = TimelineUICollection(
            self, self.scrollable_frame, self.hscrollbar, self.timelines_toolbar_frame
        )

    def get_window_size(self):
        return self.root.winfo_width()

    def get_timeline_ui_collection(self):
        return self.timeline_ui_collection

    def _setup_widgets(self):
        # create frames
        self.main_frame = tk.Frame(self.root)

        self.app_toolbars_frame = AppToolbarsFrame(self.main_frame)
        self.timelines_toolbar_frame = tk.Frame(self.main_frame)

        _scrollable_frame = ScrollableFrame(self.main_frame)
        self.scrollable_frame = _scrollable_frame.frame

        self.hscrollbar = tk.Scrollbar(self.main_frame, orient=tk.HORIZONTAL)

        # pack frames
        self.app_toolbars_frame.pack(fill="x")
        self.timelines_toolbar_frame.pack(fill="x")
        self.hscrollbar.pack(fill="x", side=tk.BOTTOM)
        _scrollable_frame.pack(side=tk.TOP, fill="both", expand=True)

        self.main_frame.pack(fill="both", expand=True)

    # noinspection PyTypeChecker,PyUnresolvedReferences
    def on_request_window(self, kind: WindowKind):

        if kind == WindowKind.INSPECT:
            if not self._windows[WindowKind.INSPECT]:
                self._windows[WindowKind.INSPECT] = Inspect(self.root)
            else:
                self._windows[WindowKind.INSPECT].focus()

        elif kind == WindowKind.MANAGE_TIMELINES:
            if not self._windows[WindowKind.MANAGE_TIMELINES]:
                self._windows[WindowKind.MANAGE_TIMELINES] = ManageTimelines(
                    self, self.get_timeline_info_for_manage_timelines_window()
                )
            else:
                self._windows[WindowKind.MANAGE_TIMELINES].focus()

        elif kind == WindowKind.MEDIA_METADATA:
            if not self._windows[WindowKind.MEDIA_METADATA]:
                self._windows[WindowKind.MEDIA_METADATA] = MediaMetadataWindow(
                    self,
                    self._app.media_metadata,
                    self.get_metadata_non_editable_fields(),
                    {'media length': format_media_time})
            else:
                self._windows[WindowKind.MEDIA_METADATA].focus()
        elif kind == WindowKind.ABOUT:
            if not self._windows[WindowKind.ABOUT]:
                self._windows[WindowKind.ABOUT] = About(self.root)
            else:
                self._windows[WindowKind.ABOUT].focus()

    def on_window_closed(self, kind: WindowKind):
        self._windows[kind] = None

    def on_tilia_file_loaded(self):
        windows_to_close = [
            WindowKind.INSPECT,
            WindowKind.MANAGE_TIMELINES,
            WindowKind.MEDIA_METADATA,
        ]

        for window_kind in windows_to_close:
            if window := self._windows[window_kind]:
                window.destroy()

    @staticmethod
    def on_display_error(title: str, message: str):
        tk.messagebox.showerror(title, message)

    def get_metadata_non_editable_fields(self) -> dict[str]:

        return OrderedDict(
            {
                "media length": self._app.media_length,
                "media path": self._app.get_media_path(),
            }
        )

    def get_timeline_info_for_manage_timelines_window(self) -> list[tuple[int, str]]:
        def get_tlui_display_string(tlui):
            if tlui.TIMELINE_KIND == TimelineKind.SLIDER_TIMELINE:
                return "SliderTimeline"
            else:
                return f"{tlui.name} | {tlui.timeline.__class__.__name__}"

        return [
            (tlui.timeline.id, get_tlui_display_string(tlui))
            for tlui in sorted(
                self.timeline_ui_collection.get_timeline_uis(),
                key=lambda t: t.display_position,
            )
        ]

    def get_elements_for_pasting(self) -> dict[str : dict | TimelineKind]:
        return self._app.get_elements_for_pasting()

    def get_id(self) -> str:
        return self._app.get_id()

    def get_media_length(self):
        return self._app.media_length

    @staticmethod
    def on_menu_file_load_media():
        media_path = file.choose_media_file()
        if media_path:
            events.post(Event.REQUEST_LOAD_MEDIA, media_path)
        else:
            logger.debug(f"User cancelled media load.")

    @staticmethod
    def get_file_save_path(initial_filename: str) -> str | None:
        path = tk.filedialog.asksaveasfilename(
            defaultextension=f"{globals_.FILE_EXTENSION}",
            initialfile=initial_filename,
            filetypes=((f"{globals_.APP_NAME} files", f"*.{globals_.FILE_EXTENSION}"),),
        )

        if not path:
            raise UserCancelledSaveError("User cancelled or closed save window dialog.")

        return path

    @staticmethod
    def get_file_open_path():
        path = tk.filedialog.askopenfilename(
            title=f"Open {globals_.APP_NAME} file...",
            filetypes=((f"{globals_.APP_NAME} files", f"*.{globals_.FILE_EXTENSION}"),),
        )

        if not path:
            raise UserCancelledOpenError("User cancelled or closed open window dialog.")

        return path

    @staticmethod
    def ask_save_changes():
        return tk.messagebox.askyesnocancel(
            "Save changes?", f"Save changes to current file?"
        )

    @staticmethod
    def ask_string(title: str, prompt: str) -> str:
        return tk.simpledialog.askstring(title, prompt=prompt)

    def ask_yes_no(self, title: str, prompt: str) -> bool:
        return ask_yes_no(title, prompt)

    def get_timeline_ui_attribute_by_id(self, id_: int, attribute: str) -> Any:
        return self.timeline_ui_collection.get_timeline_ui_attribute_by_id(
            id_, attribute
        )

    @staticmethod
    def ask_for_directory(title: str) -> str | None:
        return ask_for_directory(title)


class AppToolbarsFrame(tk.Frame):
    def __init__(self, *args, **kwargs):
        super(AppToolbarsFrame, self).__init__(*args, **kwargs)

        self.playback_frame = player_ui.PlayerUI(self)

        self.auto_scroll_checkbox = CheckboxItem(
            label="Auto-scroll",
            value=settings.settings["general"]["auto-scroll"],
            set_func=lambda: settings.edit_setting(
                "general", "auto-scroll", self.auto_scroll_checkbox.variable.get()
            ),
            parent=self,
        )

        self.playback_frame.pack(side=tk.LEFT, anchor=tk.W)
        self.auto_scroll_checkbox.pack(side=tk.LEFT, anchor=tk.W)


class ScrollableFrame(tk.Frame):
    """Tk.Frame does not support scrolling. This workaround relies
    on a frame placed inside a canvas, a widget which does support scrolling.
    self.frame is the frame that must be used by outside widgets."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.frame = tk.Frame(self.canvas)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.create_window(
            (0, 0), window=self.frame, anchor="nw"
        )

        self.frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind(
            "<Configure>",
            lambda e: events.post(Event.ROOT_WINDOW_RESIZED, e.width, e.height),
        )

    def on_frame_configure(self, event):
        """Reset the scroll region to encompass the inner frame"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


class CheckboxItem(tk.Frame):
    def __init__(
        self, label: str, value: bool, set_func: Callable, parent, *args, **kwargs
    ):
        """Checkbox toolbar item to be displayed above timeline toolbars.
        value is the default boolean value of the checkbox.
        set_func is the function that will be called on checkbox change.
        set_func will be called with the checkbox itself as first parameter,
        emulating a method call (with self as first parameter)."""
        super().__init__(parent, *args, **kwargs)
        self.variable = tk.BooleanVar(value=value)
        self.checkbox = tk.Checkbutton(self, command=set_func, variable=self.variable, takefocus=False)
        self.label = tk.Label(self, text=label)

        self.checkbox.pack(side=tk.LEFT)
        self.label.pack(side=tk.LEFT)


def get_curr_screen_geometry(root):
    """
    Workaround to get the size of the current screen in a multi-screen setup.

    Returns:
        geometry (str): The standard Tk geometry string.
            [width]x[height]+[left]+[top]
    """
    root.update_idletasks()
    root.attributes("-fullscreen", True)
    geometry = root.winfo_geometry()

    return geometry


def get_startup_geometry(root: tk.Tk):
    """
    Uses get_curr_screen_geometry to return initial window size in tkinter's geometry format.
    """

    STARTUP_HEIGHT = 300

    root.update_idletasks()
    root.attributes("-fullscreen", True)
    screen_geometry = root.winfo_geometry()

    root.attributes("-fullscreen", False)

    screen_width = int(screen_geometry.split("x")[0])
    window_geometry = f"{screen_width - 50}x{STARTUP_HEIGHT}+18+10"

    return window_geometry


def set_startup_geometry(root):

    geometry = get_startup_geometry(root)
    root.overrideredirect(True)
    root.geometry(geometry)
    root.overrideredirect(False)
