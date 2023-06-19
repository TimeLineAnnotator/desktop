from __future__ import annotations
import traceback
from typing import Any
import sys
import tkinter as tk
import tkinter.font as tk_font
from functools import partial
import logging

from . import event_handler, dialogs
from .common import display_error
from .dialogs.by_time_or_by_measure import ByTimeOrByMeasure
from .frames import AppToolbarsFrame, ScrollableFrame
from .menus import TkinterUIMenus, DynamicMenu
from .timelines.collection import TimelineUIs
from .windows.manage_timelines import ManageTimelines
from .windows.metadata import MediaMetadataWindow
from .windows.about import About
from .windows.inspect import Inspect
from .windows.kinds import WindowKind
from ..parsers.csv import (
    beats_from_csv,
    markers_by_time_from_csv,
    markers_by_measure_from_csv,
    hierarchies_by_time_from_csv,
    hierarchies_by_measure_from_csv,
)
from tilia import globals_, settings
from tilia.repr import default_str
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.requests import Post, listen, post, serve, Get, get

logger = logging.getLogger(__name__)


def handle_exception(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # log exception
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    # exception to stdout
    traceback.print_exc()


class TkinterUI:
    def __init__(self, root: tk.Tk):
        logger.debug("Starting TkinterUI...")

        self._setup_root(root)

        self.SUBSCRIPTIONS = [
            (
                Post.TIMELINE_WIDTH_CHANGE_REQUEST,
                self.on_timeline_width_change_request,
            ),
            (Post.MENU_OPTION_FILE_LOAD_MEDIA, self.on_menu_file_load_media),
            (
                Post.UI_REQUEST_WINDOW_INSPECTOR,
                lambda: self.on_request_window(WindowKind.INSPECT),
            ),
            (
                Post.UI_REQUEST_WINDOW_MANAGE_TIMELINES,
                lambda: self.on_request_window(WindowKind.MANAGE_TIMELINES),
            ),
            (
                Post.UI_REQUEST_WINDOW_METADATA,
                lambda: self.on_request_window(WindowKind.MEDIA_METADATA),
            ),
            (
                Post.UI_REQUEST_WINDOW_ABOUT,
                lambda: self.on_request_window(WindowKind.ABOUT),
            ),
            (
                Post.INSPECT_WINDOW_CLOSED,
                lambda: self.on_window_closed(WindowKind.INSPECT),
            ),
            (
                Post.MANAGE_TIMELINES_WINDOW_CLOSED,
                lambda: self.on_window_closed(WindowKind.MANAGE_TIMELINES),
            ),
            (
                Post.METADATA_WINDOW_CLOSED,
                lambda: self.on_window_closed(WindowKind.MEDIA_METADATA),
            ),
            (
                Post.ABOUT_WINDOW_CLOSED,
                lambda: self.on_window_closed(WindowKind.ABOUT),
            ),
            (Post.REQUEST_CLEAR_UI, self.on_request_clear_ui),
            (Post.TIMELINE_KIND_INSTANCED, self._on_timeline_kind_instanced),
            (Post.TIMELINE_KIND_UNINSTANCED, self._on_timeline_kind_uninstanced),
            (
                Post.REQUEST_IMPORT_CSV_MARKERS,
                partial(self.on_import_from_csv, TlKind.MARKER_TIMELINE),
            ),
            (
                Post.REQUEST_IMPORT_CSV_HIERARCHIES,
                partial(self.on_import_from_csv, TlKind.HIERARCHY_TIMELINE),
            ),
            (
                Post.REQUEST_IMPORT_CSV_BEATS,
                partial(self.on_import_from_csv, TlKind.BEAT_TIMELINE),
            ),
            (Post.REQUEST_DISPLAY_ERROR, dialogs.display_error),
        ]

        self.default_font = tk_font.nametofont("TkDefaultFont")

        self.timeline_width = globals_.DEFAULT_TIMELINE_WIDTH
        self.timeline_padx = globals_.DEFAULT_TIMELINE_PADX

        self._setup_subscriptions()
        self._setup_requests()
        self._setup_widgets()
        self.enabled_dynamic_menus: set[DynamicMenu] = set()
        self._setup_menus()
        self._setup_canvas_bindings()
        self._setup_timeline_ui_collection()

        self._windows = {
            WindowKind.INSPECT: None,
            WindowKind.MEDIA_METADATA: None,
            WindowKind.MANAGE_TIMELINES: None,
            WindowKind.ABOUT: None,
        }

        logger.debug("Tkinter UI started.")

    def __str__(self):
        return default_str(self)

    def _setup_subscriptions(self):
        for event, callback in self.SUBSCRIPTIONS:
            listen(self, event, callback)

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

    def _setup_canvas_bindings(self) -> None:
        for sequence, callback in event_handler.DEFAULT_CANVAS_BINDINGS:
            self.root.bind_class("Canvas", sequence, callback)

    def _setup_menus(self):
        self._menus = TkinterUIMenus()
        self.root.config(menu=self._menus)

        self._menus.update_dynamic_menus(self.enabled_dynamic_menus)

    tlkind_to_dynamic_menu = {
        TlKind.MARKER_TIMELINE: DynamicMenu.MARKER_TIMELINE,
        TlKind.HIERARCHY_TIMELINE: DynamicMenu.HIERARCHY_TIMELINE,
        TlKind.BEAT_TIMELINE: DynamicMenu.BEAT_TIMELINE,
    }

    def _setup_requests(self):
        # dialog requests
        serve(self, Get.SHOULD_SAVE_CHANGES_FROM_USER, dialogs.ask_should_save_changes)
        serve(self, Get.DIR_FROM_USER, dialogs.ask_for_directory)
        serve(self, Get.SAVE_PATH_FROM_USER, dialogs.ask_for_path_to_save_tilia_file)
        serve(self, Get.TILIA_FILE_PATH_FROM_USER, dialogs.ask_for_tilia_file_to_open)
        serve(self, Get.FILE_PATH_FROM_USER, dialogs.ask_for_file_to_open),
        serve(self, Get.STRING_FROM_USER, dialogs.ask_for_string)
        serve(self, Get.BEAT_PATTERN_FROM_USER, dialogs.ask_for_beat_pattern)
        serve(self, Get.FLOAT_FROM_USER, dialogs.ask_for_float)
        serve(self, Get.INT_FROM_USER, dialogs.ask_for_int)
        serve(self, Get.YES_OR_NO_FROM_USER, dialogs.ask_yes_no)
        serve(self, Get.COLOR_FROM_USER, dialogs.ask_for_color)
        # canvas-related requests
        serve(self, Get.TIMELINE_WIDTH, lambda: self.timeline_width)
        serve(
            self,
            Get.TIMELINE_FRAME_WIDTH,
            lambda: self.timeline_width + 2 * self.timeline_padx,
        )
        serve(self, Get.LEFT_MARGIN_X, lambda: self.timeline_padx)
        serve(
            self,
            Get.RIGHT_MARGIN_X,
            lambda: self.timeline_width + self.timeline_padx,
        )

    def _setup_root(self, root: tk.Tk):
        self.root = root

        def get_root_geometry():
            w = settings.get("general", "window_width")
            h = settings.get("general", "window_height")
            x = settings.get("general", "window_x")
            y = settings.get("general", "window_y")

            return f"{w}x{h}+{x}+{y}"

        self.root.geometry(get_root_geometry())
        self.root.focus_set()

        self.root.report_callback_exception = handle_exception

        self.root.title(globals_.APP_NAME)
        self.icon = tk.PhotoImage(master=self.root, file=globals_.APP_ICON_PATH)
        self.root.iconphoto(True, self.icon)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_timeline_ui_collection(self):
        self.timeline_ui_collection = TimelineUIs(self, self.hscrollbar)

    def _on_close(self):
        settings.edit("general", "window_width", self.root.winfo_width())
        settings.edit("general", "window_height", self.root.winfo_height())
        settings.edit("general", "window_x", self.root.winfo_x())
        settings.edit("general", "window_y", self.root.winfo_y())

        post(Post.REQUEST_CLOSE_APP)

    def _on_timeline_kind_instanced(self, kind: TlKind) -> None:
        if kind not in self.tlkind_to_dynamic_menu:
            return

        self.enabled_dynamic_menus.add(self.tlkind_to_dynamic_menu[kind])

        self._menus.update_dynamic_menus(self.enabled_dynamic_menus)

    def _on_timeline_kind_uninstanced(self, kind: TlKind) -> None:
        if kind not in self.tlkind_to_dynamic_menu:
            return

        self.enabled_dynamic_menus.remove(self.tlkind_to_dynamic_menu[kind])

        self._menus.update_dynamic_menus(self.enabled_dynamic_menus)

    def on_timeline_width_change_request(self, value: int) -> None:
        if value < 0:
            raise ValueError(f"Timeline v must be positive. Got {value=}")

        logger.debug(f"Changing to timeline width to {value}.")
        self.timeline_width = value
        post(Post.TIMELINE_WIDTH_CHANGED)

    def launch(self):
        logger.debug("Entering Tkinter UI mainloop.")
        self.root.mainloop()

    def get_timeline_total_width(self):
        return self.timeline_width + 2 * self.timeline_padx

    def get_window_size(self):
        return self.root.winfo_width()

    def get_timeline_ui_collection(self):
        return self.timeline_ui_collection

    def get_timelines_frame(self):
        return self.scrollable_frame

    def get_timelines_scrollbar(self):
        return self.hscrollbar

    def get_toolbar_frame(self):
        return self.timelines_toolbar_frame

    # noinspection PyTypeChecker,PyUnresolvedReferences
    def on_request_window(self, kind: WindowKind):
        """Open a window of 'kind', if there is no window of that kind open.
        Otherwise, focus window of that kind."""

        kind_to_constructor = {
            WindowKind.INSPECT: self.open_inspect_window,
            WindowKind.MANAGE_TIMELINES: self.open_manage_timelines_window,
            WindowKind.MEDIA_METADATA: self.open_media_metadata_window,
            WindowKind.ABOUT: self.open_about_window,
        }

        if not self._windows[kind]:
            self._windows[kind] = kind_to_constructor[kind]()
        else:
            self._windows[kind].focus()

    def open_inspect_window(self):
        return Inspect(self.root)

    def open_about_window(self):
        return About(self.root)

    def open_manage_timelines_window(self):
        return ManageTimelines(
            self, self.get_timeline_info_for_manage_timelines_window()
        )

    def open_media_metadata_window(self):
        return MediaMetadataWindow(self.root, get(Get.MEDIA_METADATA))

    def on_window_closed(self, kind: WindowKind):
        self._windows[kind] = None

    def on_request_clear_ui(self):
        """Closes all UI windows."""
        windows_to_close = [
            WindowKind.INSPECT,
            WindowKind.MANAGE_TIMELINES,
            WindowKind.MEDIA_METADATA,
        ]

        for window_kind in windows_to_close:
            if window := self._windows[window_kind]:
                window.destroy()

    def get_timeline_info_for_manage_timelines_window(self) -> list[tuple[int, str]]:
        def get_tlui_display_string(tlui):
            if tlui.TIMELINE_KIND == TlKind.SLIDER_TIMELINE:
                return "SliderTimeline"
            else:
                return f"{tlui.name} | {tlui.timeline.__class__.__name__}"

        return [
            (tlui.id, get_tlui_display_string(tlui))
            for tlui in self.timeline_ui_collection.get_timeline_uis()
        ]

    @staticmethod
    def on_menu_file_load_media():
        media_path = dialogs.ask_for_media_file()
        if media_path:
            post(Post.REQUEST_LOAD_MEDIA, media_path)
        else:
            logger.debug("User cancelled media load.")

    def on_import_from_csv(self, tlkind: TlKind) -> None:
        if not self.timeline_ui_collection.get_timeline_uis_by_kind(tlkind):
            display_error(
                "Import from CSV error",
                f"No timelines of type '{tlkind}' found.",
            )
            return

        timeline = self.timeline_ui_collection.ask_choose_timeline(
            "Import components from CSV",
            "Choose timeline where components will be created",
            tlkind,
        )
        if not timeline:
            return

        if tlkind == TlKind.BEAT_TIMELINE:
            time_or_measure = "time"
        else:
            time_or_measure = ByTimeOrByMeasure(self.root).ask()
            if not time_or_measure:
                return

            if time_or_measure == "measure":
                if not self.timeline_ui_collection.get_timeline_uis_by_kind(
                    TlKind.BEAT_TIMELINE
                ):
                    display_error(
                        "Import from CSV error",
                        (
                            "No beat timelines found. Must have a beat timeline if"
                            " importing by measure."
                        ),
                    )
                    return

                beat_tl = self.timeline_ui_collection.ask_choose_timeline(
                    "Import components from CSV",
                    "Choose timeline with measures to be used when importing",
                    TlKind.BEAT_TIMELINE,
                )

                if not beat_tl:
                    return

        path = get(
            Get.FILE_PATH_FROM_USER, "Import components", [("CSV files", "*.csv")]
        )

        if not path:
            return

        tlkind_to_funcs = {
            TlKind.MARKER_TIMELINE: {
                "time": markers_by_time_from_csv,
                "measure": markers_by_measure_from_csv,
            },
            TlKind.HIERARCHY_TIMELINE: {
                "time": hierarchies_by_time_from_csv,
                "measure": hierarchies_by_measure_from_csv,
            },
            TlKind.BEAT_TIMELINE: {"time": beats_from_csv},
        }

        if time_or_measure == "time":
            errors = tlkind_to_funcs[tlkind]["time"](timeline, path)
        else:
            errors = tlkind_to_funcs[tlkind]["measure"](timeline, beat_tl, path)

        if errors:
            errors_str = "\n".join(errors)
            post(
                Post.REQUEST_DISPLAY_ERROR,
                "Import components from csv",
                "Some components were not imported. The following errors occured:\n"
                + errors_str,
            )

    def get_timeline_ui_attribute_by_id(self, id_: int, attribute: str) -> Any:
        return self.timeline_ui_collection.get_timeline_ui_attribute_by_id(
            id_, attribute
        )
