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
import traceback


from tilia import globals_, events
from tilia.player import player_ui
from tilia.exceptions import UserCancelledSaveError, UserCancelledOpenError
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.events import EventName, Subscriber
from .event_handler import TkEventHandler
from .timelines.common import TkTimelineUICollection
from .windows.common import AppWindow
from .windows.gotomeasure import GoToMeasureWindow
from .windows.manage_timelines import ManageTimelines
from .windows.metadata import MetadataWindow
from .windows.inspect import Inspect
from .windows.kinds import WindowKind
from .. import file

if TYPE_CHECKING:
    from tilia.main import TiLiA

import logging

logger = logging.getLogger(__name__)


def handle_exception(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    traceback.print_tb(exc_traceback)
    print(exc_type)
    print(exc_value)


class TkinterUI(Subscriber):
    """
    Responsible for high-level control of the GUI:
        - Instances the tk.TK object;
        - Is composed of the high level tkinter frames (toolbar frame, timelines frame, etc...);
        - Is composed of the TkinterUIMenus class;
        - Is composed of a TkEventHandler which translates tkinter events into events.py events;
        - Keeps 'global' interface data such as window and timeline dimensions.
    """

    SUBSCRIPTIONS = [
        EventName.UI_REQUEST_WINDOW_INSPECTOR,
        EventName.UI_REQUEST_WINDOW_MANAGE_TIMELINES,
        EventName.UI_REQUEST_WINDOW_METADATA,
        EventName.MENU_OPTION_FILE_LOAD_MEDIA
    ]

    def __init__(self, app: TiLiA):
        super().__init__(subscriptions=self.SUBSCRIPTIONS)

        logger.debug("Starting TkinterUI...")

        self._app = app
        self._setup_tk_root()

        self.default_font = tkinter.font.nametofont("TkDefaultFont")

        self.timeline_width = globals_.DEFAULT_TIMELINE_WIDTH
        self.timeline_padx = globals_.DEFAULT_TIMELINE_PADX

        self.window_width = globals_.DEFAULT_WINDOW_WIDTH
        self.window_height = globals_.DEFAULT_WINDOW_HEIGHT

        self._setup_frames()
        self._setup_menus()

        self.event_handler = TkEventHandler(self.root)

        self._create_timeline_ui_collection()

        self.root.update_idletasks()  # necessary so .geometry positions windows correctly
        self.root.geometry(
            "+0+0"  # TODO set default window width and height
        )  # if called earlier will not work correctly, for some reason

        self._windows = {}

        logger.debug("Tkinter UI started.")

    def _setup_tk_root(self):
        self.root = tk.Tk()

        self.root.report_callback_exception = handle_exception

        self.root.title(globals_.APP_NAME)
        self.root.iconbitmap(globals_.APP_ICON_PATH)

        self.root.protocol(
            "WM_DELETE_WINDOW", lambda: events.post(EventName.APP_REQUEST_TO_CLOSE)
        )

    def _setup_menus(self):
        self.menus = TkinterUIMenus(self, self.root)

    def launch(self):
        logger.debug("Entering Tkinter UI mainloop.")
        self.root.mainloop()

    @property
    def timeline_total_size(self):
        return self.timeline_width + 2 * self.timeline_padx

    def _create_timeline_ui_collection(self):
        timelines_scrollbar = tk.Scrollbar(self.hscrollbar_frame, orient=tk.HORIZONTAL)
        self.timeline_ui_collection = TkTimelineUICollection(
            self, self.inner_timelines_frame, timelines_scrollbar, self.timelines_toolbar_frame
        )

    def get_timeline_ui_collection(self):
        return self.timeline_ui_collection

    def _setup_frames(self):

        # create frames
        self.main_frame = tk.Frame(self.root)

        self.app_toolbars_frame = AppToolbarsFrame(self.main_frame)
        globals_.TIMELINES_TOOLBAR = self.timelines_toolbar_frame = tk.Frame(
            self.main_frame
        )

        self.outer_timelines_frame = tk.Frame(self.main_frame)
        self.inner_timelines_frame = ScrollableFrame(self.outer_timelines_frame, bg="blue")
        self.inner_timelines_frame.grid_columnconfigure(
            0, weight=1
        )

        self.bottom_frame = tk.Frame(self.main_frame)
        self.hscrollbar_frame = tk.Frame(self.main_frame)

        # pack frames
        self.app_toolbars_frame.pack(fill="x")
        self.timelines_toolbar_frame.pack(fill="x")
        self.outer_timelines_frame.pack(fill="both", expand=True)
        self.bottom_frame.pack(fill="x")
        self.hscrollbar_frame.pack(fill="x")
        self.main_frame.pack(fill="both", expand=True)

    def on_request_window(self, kind: WindowKind):
        if kind == WindowKind.INSPECTOR:
            self._windows[WindowKind.INSPECTOR] = Inspect(self.root)
        elif kind == WindowKind.MANAGE_TIMELINES:
            self._windows[WindowKind.MANAGE_TIMELINES] = ManageTimelines(
                self, self.get_timeline_info_for_manage_timelines_window()
            )
        elif kind == WindowKind.METADATA:
            self._windows[WindowKind.METADATA] = MetadataWindow(
                self,
                self._app.media_metadata,
                self.get_metadata_non_editable_fields()
            )

    def get_metadata_non_editable_fields(self) -> dict[str]:

        return OrderedDict({
            'media length': self._app.media_length,
            'media path': self._app.get_media_path()
        })

    def get_timeline_info_for_manage_timelines_window(self) -> list[tuple[int, str]]:
        return [
            (tlui.timeline.id, str(tlui))
            for tlui in sorted(self.timeline_ui_collection.get_timeline_uis(), key=lambda t: t.timeline.id)
        ]

    def get_elements_for_pasting(self):
        return self._app.get_elements_for_pasting()

    def get_id(self) -> str:
        return self._app.get_id()

    def get_media_length(self):
        return self._app.media_length

    @staticmethod
    def on_menu_file_load_media():
        media_path = file.choose_media_file()
        # TODO validate media path

        events.post(EventName.FILE_REQUEST_TO_LOAD_MEDIA, media_path)

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

    def on_subscribed_event(
        self, event_name: EventName, *args: tuple, **kwargs: dict
    ) -> None:
        event_to_callback = {
            EventName.MENU_OPTION_FILE_LOAD_MEDIA: self.on_menu_file_load_media,
            EventName.UI_REQUEST_WINDOW_INSPECTOR: lambda: self.on_request_window(
                WindowKind.INSPECTOR
            ),
            EventName.UI_REQUEST_WINDOW_MANAGE_TIMELINES: lambda: self.on_request_window(
                WindowKind.MANAGE_TIMELINES
            ),
            EventName.UI_REQUEST_WINDOW_METADATA: lambda: self.on_request_window(
                WindowKind.METADATA
            )
        }

        event_to_callback[event_name]()

    def get_timeline_ui_attribute_by_id(self, id_: int, attribute: str) -> Any:
        return self.timeline_ui_collection.get_timeline_ui_attribute_by_id(
            id_, attribute
        )


class AppToolbarsFrame(tk.Frame):
    def __init__(self, *args, **kwargs):
        super(AppToolbarsFrame, self).__init__(*args, **kwargs)

        self.playback_frame = player_ui.PlayerUI(self)

        # TODO reimplement checkbox options
        # def set_auto_scroll(caller: CheckboxItem):
        #     globals_.settings["GENERAL"]["auto_scroll"] = caller.variable.get()
        #
        # self.auto_scroll_toolbar = CheckboxItem(
        #     label="Auto-scroll",
        #     # value=bool(globals_.settings["GENERAL"]["auto_scroll"]),
        #     value=True,
        #     set_func=set_auto_scroll,
        #     parent=self,
        # )
        #
        # def set_freeze_labels(caller: CheckboxItem):
        #     globals_.settings["GENERAL"][
        #         "freeze_timeline_labels"
        #     ] = caller.variable.get()
        #     events.post(EventName.FREEZE_LABELS_SET)
        #
        # self.freeze_labels_toolbar = CheckboxItem(
        #     label="Freeze labels",
        #     # value=bool(globals_.settings["GENERAL"]["freeze_timeline_labels"]),
        #     value=True,
        #     set_func=set_freeze_labels,
        #     parent=self,
        # )
        #

        self.playback_frame.pack(side=tk.LEFT, anchor=tk.W)

        # self.auto_scroll_toolbar.pack(side=tk.LEFT, anchor=tk.W)
        # self.freeze_labels_toolbar.pack(side=tk.LEFT, anchor=tk.W)


class ScrollableFrame(tk.Frame):
    """
    A vertically scrollable frame for the timeline UIs.
    Taken from Tarqez's answer to this question on SO:
    https://stackoverflow.com/questions/3085696/adding-a-scrollbar-to-a-group-of-widgets-in-tkinter
    """

    def __init__(self, frame, *args, **kwargs):

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, expand=False)

        self.canvas = tk.Canvas(frame, yscrollcommand=scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar.config(command=self.canvas.yview)

        super().__init__(frame, *args, **kwargs)

        self.canvas.bind("<Configure>", self.__fill_canvas)

        # assign this obj (the inner frame) to the windows item of the canvas
        self.windows_item = self.canvas.create_window(0, 0, window=self, anchor=tk.NW)

    def __fill_canvas(self, event):
        """Enlarge the windows item to the canvas width"""
        canvas_width = event.width
        self.canvas.itemconfig(self.windows_item, width=canvas_width)

    def update(self):
        """Update the canvas and the scrollregion"""
        self.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox(self.windows_item))


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
        self.checkbox = tk.Checkbutton(
            self, command=lambda: set_func(self), variable=self.variable
        )
        self.label = tk.Label(self, text=label)

        self.checkbox.pack(side=tk.LEFT)
        self.label.pack(side=tk.LEFT)


class TkinterUIMenus(tk.Menu):
    def __init__(self, tkinterui: TkinterUI, parent):
        self._tkinterui = tkinterui
        super().__init__(parent)

        parent.config(menu=self)

        # FILE MENU
        self.file_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="File", menu=self.file_menu, underline=0)

        self.file_menu.add_command(
            label="New...",
            command=lambda: events.post(EventName.FILE_REQUEST_NEW_FILE, save_as=False),
        )
        self.file_menu.add_command(
            label="Open...",
            command=lambda: events.post(EventName.FILE_REQUEST_TO_OPEN),
            underline=0,
        )
        self.file_menu.add_command(
            label="Save",
            command=lambda: events.post(EventName.FILE_REQUEST_TO_SAVE, save_as=False),
            accelerator="Ctrl+S",
            underline=0,
        )
        self.file_menu.add_command(
            label="Save as...",
            command=lambda: events.post(EventName.FILE_REQUEST_TO_SAVE, save_as=True),
            accelerator="Ctrl+Shift+S",
            underline=5,
        )
        self.file_menu.add_command(
            label="Load media file...",
            underline=0,
            command=lambda: events.post(EventName.MENU_OPTION_FILE_LOAD_MEDIA),
        )
        self.file_menu.add_separator()
        self.goto_menu = tk.Menu(tearoff=0)
        self.file_menu.add_cascade(
            label="Go to...", menu=self.goto_menu, underline=0, state="disabled"
        )
        self.goto_menu.add_command(
            label="Measure..",
            command=lambda: GoToMeasureWindow(),
            underline=0,
            accelerator="Ctrl+G",
            state="disabled",
        )
        # self.goto_menu.add_command(label='Time..', underline=0, accelerator='Ctrl+Shift+G')

        self.file_menu.add_separator()
        self.file_menu.add_command(
            label="Media metadata...",
            command=lambda: events.post(EventName.UI_REQUEST_WINDOW_METADATA),
            underline=0
        )

        # EDIT MENU
        self.edit_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="Edit", menu=self.edit_menu, underline=0)

        self.edit_menu.add_command(
            label="Undo",
            # command=event_handlers.on_ctrlz,
            underline=0,
            accelerator="Ctrl + Z",
            state="disabled",
        )
        self.edit_menu.add_command(
            label="Redo",
            # command=event_handlers.on_ctrly,
            underline=0,
            accelerator="Ctrl + Y",
            state="disabled",
        )

        # self.edit_menu.add_command(label='Clear timeline', command=event_handlers.on_cleartimeline, underline=0)

        # TIMELINES MENU
        self.timelines_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="Timelines", menu=self.timelines_menu, underline=0)

        self.timelines_menu.add_timelines = tk.Menu(self.timelines_menu, tearoff=0)

        for kind in TimelineKind:
            self.timelines_menu.add_timelines.add_command(
                label=kind.value.capitalize(),
                command=lambda kind_=kind: events.post(
                    EventName.APP_ADD_TIMELINE, kind_
                ),
                underline=0,
            )

        self.timelines_menu.add_cascade(
            label="Add...",
            menu=self.timelines_menu.add_timelines,
            underline=0,
        )

        self.timelines_menu.add_command(
            label="Manage...",
            underline=0,
            command=lambda: events.post(EventName.UI_REQUEST_WINDOW_MANAGE_TIMELINES),
        )

        self.timelines_menu.add_command(
            label="Clear all",
            underline=0,
            command=lambda: events.post(EventName.TIMELINES_REQUEST_TO_CLEAR_ALL_TIMELINES),
            state="disabled",
        )

        # VIEW MENU
        self.view_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="View", menu=self.view_menu, underline=0)
        self.view_window_menu = tk.Menu(self.view_menu, tearoff=0)
        self.view_menu.add_cascade(
            label="Window", menu=self.view_window_menu, underline=0
        )
        self.view_window_menu.add_command(
            label="Inspect",
            command=lambda: events.post(EventName.UI_REQUEST_WINDOW_INSPECTOR),
            underline=0,
        )
        self.view_menu.add_separator()
        self.view_menu.add_command(
            label="Zoom in",
            accelerator="Ctrl + +",
            command=lambda: events.post(EventName.REQUEST_ZOOM_IN),
        )
        self.view_menu.add_command(
            label="Zoom out",
            accelerator="Ctrl + -",
            command=lambda: events.post(EventName.REQUEST_ZOOM_OUT),
        )

        # DEVELOPMENT WINDOW OPTION
        if globals_.DEVELOPMENT_MODE:
            self.view_window_menu.add_command(
                label="Development",
                command=lambda: events.post(EventName.UI_REQUEST_WINDOW_DEVELOPMENT),
                underline=0,
            )

        # HELP MENU
        self.help_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="Help", menu=self.help_menu, underline=0)
        self.help_menu.add_command(label="Help...", state="disabled", underline=0)
        self.help_menu.add_command(
            label="About...",
            underline=0,
            command=lambda: events.post(EventName.UI_REQUEST_WINDOW_ABOUT),
            state="disabled",
        )

        class AboutWindow(AppWindow):
            def __init__(self):
                super(AboutWindow, self).__init__()
                self.title(f"{globals_.APP_NAME}")
                tk.Label(self, text=globals_.APP_NAME).pack()
                tk.Label(self, text=f"Version {globals_.VERSION}").pack()
                # TODO add licensing information
                tk.Label(self, text="Felipe Defensor").pack()
                tk.Label(self, text="https://github.com/FelipeDefensor/TiLiA").pack()


def get_curr_screen_geometry():
    """
    Workaround to get the size of the current screen in a multi-screen setup.

    Returns:
        geometry (str): The standard Tk geometry string.
            [width]x[height]+[left]+[top]
    """
    root = tk.Tk()
    root.update_idletasks()
    root.attributes("-fullscreen", True)
    root.state("iconic")
    geometry = root.winfo_geometry()
    root.destroy()
    return geometry


def get_startup_geometry():
    """
    Uses get_curr_screen_geometry to return initial window size in tkinter's geometry format.
    """

    screen_geometry = get_curr_screen_geometry()
    # subtract 15 so window does not get cropped in case of miscalculation of upper right corner
    screen_width = int(screen_geometry.split("x")[0]) - 15
    window_geometry = f"{screen_width}x%d+0+0"

    return window_geometry
