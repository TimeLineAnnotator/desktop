from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Any, Iterable

from tilia import events
from tilia.events import Event
from tilia.timelines.timeline_kinds import USER_CREATABLE_TIMELINE_KINDS


SEPARATOR = "separator"


@dataclass
class CommandParams:
    label: str
    event: Event
    command_kwargs: Optional[dict[str:Any]]
    event_kwargs: Optional[dict[str:Any]]


def get_command_callback(event: Event, **kwargs):
    return lambda: events.post(event, **kwargs)


def add_menu_commands(menu: tk.Menu, commands: list[CommandParams]) -> None:
    """
    Adds commands to menu using a list of CommandParams.
    The callback to the menu option will post the event specified in CommandParams.event.
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


class TkinterUIMenus(tk.Menu):
    def __init__(self):
        super().__init__()
        self.file_menu = self.setup_file_menu()
        self.edit_menu = self.setup_edit_menu()
        self.timelines_menu = self.setup_timelines_menu()
        self.view_menu = self.setup_view_menu()
        self.help_menu = self.setup_help_menu()

        self.dynamic_menus: list[DynamicMenu] = []

        self.dynamic_menu_to_parent = {DynamicMenu.MARKER_TIMELINE: self.timelines_menu}
        self.dynamic_menu_to_index = {DynamicMenu.MARKER_TIMELINE: 3}

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
            CommandParams("New...", Event.REQUEST_NEW_FILE, {"underline": 0}, {}),
            CommandParams("Open...", Event.FILE_REQUEST_TO_OPEN, {"underline": 0}, {}),
            CommandParams(
                "Save", Event.FILE_REQUEST_TO_SAVE, {"underline": 0}, {"save_as": False}
            ),
            CommandParams(
                "Save as...",
                Event.FILE_REQUEST_TO_SAVE,
                {"underline": 5},
                {"save_as": True},
            ),
            CommandParams(
                "Load media file...",
                Event.MENU_OPTION_FILE_LOAD_MEDIA,
                {"underline": 0},
                {},
            ),
            SEPARATOR,
            CommandParams(
                "Media metadata...",
                Event.UI_REQUEST_WINDOW_METADATA,
                {"underline": 0},
                {},
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
                Event.REQUEST_TO_UNDO,
                {"underline": 0, "accelerator": "Ctrl + Z"},
                {},
            ),
            CommandParams(
                "Redo",
                Event.REQUEST_TO_REDO,
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
                Event.UI_REQUEST_WINDOW_MANAGE_TIMELINES,
                {"underline": 0},
                {},
            ),
            CommandParams(
                "Clear all",
                Event.REQUEST_CLEAR_ALL_TIMELINES,
                {"underline": 0},
                {},
            ),
        ]

        menu = tk.Menu(self, tearoff=0)

        ## ADD TIMELINE MENU
        menu.add_timelines = tk.Menu(menu, tearoff=0)

        def get_add_timeline_options():
            options = []
            for kind in USER_CREATABLE_TIMELINE_KINDS:
                label = kind.value[: -len("_TIMELINE")].capitalize()
                command = lambda kind_=kind: events.post(
                    Event.REQUEST_ADD_TIMELINE, kind_
                )
                options.append((label, command))

            return options

        for label, command in get_add_timeline_options():
            menu.add_timelines.add_command(label=label, command=command, underline=0)

        menu.add_cascade(label="Add...", menu=menu.add_timelines, underline=0)

        # ADD REMAINING COMMANDS
        add_menu_commands(menu, commands)

        ## ADD MARKER MENU
        menu.marker = tk.Menu(menu, tearoff=0)
        marker_commands = [
            CommandParams(
                "Import from csv...",
                Event.REQUEST_IMPORT_FROM_CSV,
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
                Event.REQUEST_ZOOM_IN,
                {"accelerator": "Ctrl + +"},
                {},
            ),
            CommandParams(
                "Zoom out",
                Event.REQUEST_ZOOM_OUT,
                {"accelerator": "Ctrl + -"},
                {},
            ),
        ]

        menu = tk.Menu(self, tearoff=0)

        view_window_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="Window", menu=view_window_menu, underline=0)

        view_window_menu.add_command(
            label="Inspect",
            command=lambda: events.post(Event.UI_REQUEST_WINDOW_INSPECTOR),
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
                Event.UI_REQUEST_WINDOW_ABOUT,
                {"underline": 0},
                {},
            ),
        ]

        menu = tk.Menu(self, tearoff=0)

        menu.add_command(label="Help...", state="disabled", underline=0)

        add_menu_commands(menu, commands)

        self.add_cascade(label="Help", menu=menu, underline=0)

        return menu
