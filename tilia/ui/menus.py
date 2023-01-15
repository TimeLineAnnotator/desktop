from __future__ import annotations

import tkinter as tk

from tilia import events
from tilia.events import Event
from tilia.timelines.timeline_kinds import USER_CREATABLE_TIMELINE_KINDS


class TkinterUIMenus(tk.Menu):
    def __init__(self):
        super().__init__()

        # FILE MENU
        file_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="File", menu=file_menu, underline=0)

        file_menu.add_command(
            label="New...",
            command=lambda: events.post(Event.REQUEST_NEW_FILE),
        )
        file_menu.add_command(
            label="Open...",
            command=lambda: events.post(Event.FILE_REQUEST_TO_OPEN),
            underline=0,
        )
        file_menu.add_command(
            label="Save",
            command=lambda: events.post(Event.FILE_REQUEST_TO_SAVE, save_as=False),
            accelerator="Ctrl+S",
            underline=0,
        )
        file_menu.add_command(
            label="Save as...",
            command=lambda: events.post(Event.FILE_REQUEST_TO_SAVE, save_as=True),
            accelerator="Ctrl+Shift+S",
            underline=5,
        )
        file_menu.add_command(
            label="Load media file...",
            underline=0,
            command=lambda: events.post(Event.MENU_OPTION_FILE_LOAD_MEDIA),
        )
        file_menu.add_separator()

        file_menu.add_command(
            label="Media metadata...",
            command=lambda: events.post(Event.UI_REQUEST_WINDOW_METADATA),
            underline=0,
        )

        # EDIT MENU
        edit_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="Edit", menu=edit_menu, underline=0)

        edit_menu.add_command(
            label="Undo",
            command=lambda: events.post(Event.REQUEST_TO_UNDO),
            underline=0,
            accelerator="Ctrl + Z",
        )
        edit_menu.add_command(
            label="Redo",
            command=lambda: events.post(Event.REQUEST_TO_REDO),
            underline=0,
            accelerator="Ctrl + Y",
        )

        # edit_menu.add_command(label='Clear timeline', command=event_handlers.on_cleartimeline, underline=0)

        # TIMELINES MENU
        timelines_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="Timelines", menu=timelines_menu, underline=0)

        timelines_menu.add_timelines = tk.Menu(timelines_menu, tearoff=0)

        def get_add_timeline_options():
            options = []
            for kind in USER_CREATABLE_TIMELINE_KINDS:
                label = kind.value[:-len('_TIMELINE')].capitalize()
                command = lambda kind_=kind: events.post(Event.REQUEST_ADD_TIMELINE, kind_)
                options.append((label, command))

            return options

        for label, command in get_add_timeline_options():
            timelines_menu.add_timelines.add_command(
                label=label,
                command=command,
                underline=0
            )

        timelines_menu.add_cascade(
            label="Add...",
            menu=timelines_menu.add_timelines,
            underline=0,
        )

        timelines_menu.add_command(
            label="Manage...",
            underline=0,
            command=lambda: events.post(Event.UI_REQUEST_WINDOW_MANAGE_TIMELINES),
        )

        timelines_menu.add_command(
            label="Clear all",
            underline=0,
            command=lambda: events.post(Event.REQUEST_CLEAR_ALL_TIMELINES),
        )

        # VIEW MENU
        view_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="View", menu=view_menu, underline=0)
        view_window_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(
            label="Window", menu=view_window_menu, underline=0
        )
        view_window_menu.add_command(
            label="Inspect",
            command=lambda: events.post(Event.UI_REQUEST_WINDOW_INSPECTOR),
            underline=0,
        )
        view_menu.add_separator()
        view_menu.add_command(
            label="Zoom in",
            accelerator="Ctrl + +",
            command=lambda: events.post(Event.REQUEST_ZOOM_IN),
        )
        view_menu.add_command(
            label="Zoom out",
            accelerator="Ctrl + -",
            command=lambda: events.post(Event.REQUEST_ZOOM_OUT),
        )

        # # DEVELOPMENT WINDOW OPTION
        # if settings.get('dev', 'dev_mode'):
        #     view_window_menu.add_command(
        #         label="Development",
        #         command=lambda: events.post(Event.UI_REQUEST_WINDOW_DEVELOPMENT),
        #         underline=0,
        #     )

        # HELP MENU
        help_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="Help", menu=help_menu, underline=0)
        help_menu.add_command(label="Help...", state="disabled", underline=0)
        help_menu.add_command(
            label="About...",
            underline=0,
            command=lambda: events.post(Event.UI_REQUEST_WINDOW_ABOUT),
        )
