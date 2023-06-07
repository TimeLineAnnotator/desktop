from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from enum import Enum, auto
from functools import partial
from typing import Optional, Any, Iterable

from tilia.requests import Post, post
from tilia.timelines.timeline_kinds import USER_CREATABLE_TIMELINE_KINDS

SEPARATOR = "separator"


@dataclass
class CommandParams:
    label: str
    event: Post
    command_kwargs: Optional[dict[str:Any]]
    event_kwargs: Optional[dict[str:Any]]


def get_command_callback(event: Post, **kwargs):
    return lambda: post(event, **kwargs)


def add_menu_commands(menu: tk.Menu, commands: list[CommandParams]) -> None:
    """
    Adds commands to menu using a list of CommandParams.
    The callback to the menu option will post the event specified in
    CommandParams.event.
    """
    for command in commands:
        if command == SEPARATOR:
            menu.add_separator()
        else:
            menu.add_command(
                label=command.label,
                command=get_command_callback(command.event, **command.event_kwargs),
                **command.command_kwargs,
            )


class DynamicMenu(Enum):
    MARKER_TIMELINE = auto()
    HIERARCHY_TIMELINE = auto()


class TkinterUIMenus(tk.Menu):
    def __init__(self):
        super().__init__()
        self.file_menu = self.setup_file_menu()
        self.edit_menu = self.setup_edit_menu()
        self.timelines_menu = self.setup_timelines_menu()
        self.view_menu = self.setup_view_menu()
        self.help_menu = self.setup_help_menu()

        self.dynamic_menus: list[DynamicMenu] = []

        self.dynamic_menu_to_parent = {
            DynamicMenu.HIERARCHY_TIMELINE: self.timelines_menu,
            DynamicMenu.MARKER_TIMELINE: self.timelines_menu,
        }

        self.dynamic_menu_to_index = {
            DynamicMenu.HIERARCHY_TIMELINE: 3,
            DynamicMenu.MARKER_TIMELINE: 4,
        }

    def update_dynamic_menus(self, menus_to_display: Iterable[DynamicMenu]) -> None:
        for menu in DynamicMenu:
            parent = self.dynamic_menu_to_parent[menu]
            index = self.dynamic_menu_to_index[menu]
            if menu in menus_to_display:
                parent.entryconfig(index, state="normal")
            else:
                parent.entryconfig(index, state="disabled")

    def setup_file_menu(self):
        commands = [
            CommandParams("New...", Post.REQUEST_FILE_NEW, {"underline": 0}, {}),
            CommandParams("Open...", Post.REQUEST_FILE_OPEN, {"underline": 0}, {}),
            CommandParams(
                "Save", Post.REQUEST_SAVE, {"underline": 0}, {"save_as": False}
            ),
            CommandParams(
                "Save as...",
                Post.REQUEST_SAVE,
                {"underline": 5},
                {"save_as": True},
            ),
            CommandParams(
                "Load media file...",
                Post.MENU_OPTION_FILE_LOAD_MEDIA,
                {"underline": 0},
                {},
            ),
            SEPARATOR,
            CommandParams(
                "Media metadata...",
                Post.UI_REQUEST_WINDOW_METADATA,
                {"underline": 0},
                {},
            ),
            SEPARATOR,
            CommandParams(
                "Settings...", Post.REQUEST_OPEN_SETTINGS, {"underline": 0}, {}
            ),
        ]

        # FILE MENU
        menu = tk.Menu(self, tearoff=0)
        add_menu_commands(menu, commands)

        self.add_cascade(label="File", menu=menu, underline=0)

        return menu

    def setup_edit_menu(self):
        commands = [
            CommandParams(
                "Undo",
                Post.REQUEST_TO_UNDO,
                {"underline": 0, "accelerator": "Ctrl + Z"},
                {},
            ),
            CommandParams(
                "Redo",
                Post.REQUEST_TO_REDO,
                {"underline": 0, "accelerator": "Ctrl + Y"},
                {},
            ),
        ]

        menu = tk.Menu(self, tearoff=0)
        add_menu_commands(menu, commands)

        self.add_cascade(label="Edit", menu=menu, underline=0)

        return menu

    def setup_timelines_menu(self):
        commands = [
            CommandParams(
                "Manage...",
                Post.UI_REQUEST_WINDOW_MANAGE_TIMELINES,
                {"underline": 0},
                {},
            ),
            CommandParams(
                "Clear all",
                Post.REQUEST_CLEAR_ALL_TIMELINES,
                {"underline": 0},
                {},
            ),
        ]

        menu = tk.Menu(self, tearoff=0)

        # ADD TIMELINE MENU
        menu.add_timelines = tk.Menu(menu, tearoff=0)

        def post_create_timeline(kind):
            post(Post.REQUEST_TIMELINE_CREATE, kind)

        def get_add_timeline_options():
            options = []
            for kind in USER_CREATABLE_TIMELINE_KINDS:
                label = kind.value[: -len("_TIMELINE")].capitalize()
                options.append((label, partial(post_create_timeline, kind)))

            return options

        for label, command in get_add_timeline_options():
            menu.add_timelines.add_command(label=label, command=command, underline=0)

        menu.add_cascade(label="Add...", menu=menu.add_timelines, underline=0)

        # ADD REMAINING COMMANDS
        add_menu_commands(menu, commands)

        # ADD HIERARCHY MENU
        menu.hierarchy = tk.Menu(menu, tearoff=0)
        hierarchy_commands = [
            CommandParams(
                "Import from csv...",
                Post.REQUEST_IMPORT_CSV_HIERARCHIES,
                {"underline": 0},
                {},
            )
        ]

        add_menu_commands(menu.hierarchy, hierarchy_commands)
        menu.add_cascade(label="Hierarchies", menu=menu.hierarchy, underline=0)

        # ADD MARKER MENU
        menu.marker = tk.Menu(menu, tearoff=0)
        marker_commands = [
            CommandParams(
                "Import from csv...",
                Post.REQUEST_IMPORT_CSV_MARKERS,
                {"underline": 0},
                {},
            )
        ]

        add_menu_commands(menu.marker, marker_commands)
        menu.add_cascade(label="Marker", menu=menu.marker, underline=0)

        self.add_cascade(label="Timelines", menu=menu, underline=0)

        return menu

    def setup_view_menu(self):
        commands = [
            CommandParams(
                "Zoom in",
                Post.REQUEST_ZOOM_IN,
                {"accelerator": "Ctrl + +"},
                {},
            ),
            CommandParams(
                "Zoom out",
                Post.REQUEST_ZOOM_OUT,
                {"accelerator": "Ctrl + -"},
                {},
            ),
        ]

        menu = tk.Menu(self, tearoff=0)

        view_window_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="Window", menu=view_window_menu, underline=0)

        view_window_menu.add_command(
            label="Inspect",
            command=lambda: post(Post.UI_REQUEST_WINDOW_INSPECTOR),
            underline=0,
        )

        menu.add_separator()

        add_menu_commands(menu, commands)

        self.add_cascade(label="View", menu=menu, underline=0)

        return menu

    def setup_help_menu(self):
        commands = [
            CommandParams(
                "About...",
                Post.UI_REQUEST_WINDOW_ABOUT,
                {"underline": 0},
                {},
            ),
        ]

        menu = tk.Menu(self, tearoff=0)

        menu.add_command(label="Help...", state="disabled", underline=0)

        add_menu_commands(menu, commands)

        self.add_cascade(label="Help", menu=menu, underline=0)

        return menu
