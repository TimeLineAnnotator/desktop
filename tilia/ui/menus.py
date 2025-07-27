from __future__ import annotations

from typing import TypeAlias
from enum import Enum, auto

from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction

from tilia.timelines import timeline_kinds
from tilia.timelines.timeline_kinds import get_timeline_name
from tilia.ui.commands import get_qaction
from tilia.settings import settings
from tilia.requests.post import post, Post, listen
from tilia.ui.enums import WindowState


class MenuItemKind(Enum):
    SEPARATOR = auto()
    ACTION = auto()
    SUBMENU = auto()


TiliaMenuItem: TypeAlias = None | type[QMenu]


class TiliaMenu(QMenu):
    menu_title: str = ""
    items: list[tuple[MenuItemKind, TiliaMenuItem]] = []

    def __init__(self):
        super().__init__()
        self.setTitle(self.menu_title)
        self.class_to_submenu = {}
        for kind, item in self.items:
            self.add_item(kind, item)

    def add_item(self, kind: MenuItemKind, item: TiliaMenuItem):
        if kind == MenuItemKind.SEPARATOR:
            self.add_separator()
        elif kind == MenuItemKind.SUBMENU:
            self.add_submenu(item)
        else:
            self.add_action(item)

    def add_separator(self):
        self.addSeparator()

    def add_submenu(self, cls: type[TiliaMenu]):
        #  submenus can't be instanced as a class property,
        #  since QApplication is not yet instanced at
        #  declaration-time, so instancing is delayed until now
        submenu = cls()
        self.class_to_submenu[cls] = submenu
        self.addMenu(submenu)

    def add_action(self, name: str):
        self.addAction(get_qaction(name))

    def get_submenu(self, cls: type[TiliaMenu]):
        return self.class_to_submenu[cls]


class LoadMediaMenu(TiliaMenu):
    menu_title = "&Load media"
    items = [
        (MenuItemKind.ACTION, "media_load_local"),
        (MenuItemKind.ACTION, "media_load_youtube"),
    ]


class RecentFilesMenu(QMenu):
    def __init__(self):
        super().__init__()
        self.setTitle("Open &Recent file")
        self.add_items()
        settings.link_file_update(self.update_items)

    def add_items(self):
        recent_files = settings.get_recent_files()
        qactions = [self._get_action(file) for file in recent_files]
        self.addActions(qactions)

    def _get_action(self, file):
        qaction = QAction(str(file), self)
        qaction.triggered.connect(lambda _: post(Post.FILE_OPEN, file))
        return qaction

    def update_items(self):
        self.clear()
        self.add_items()


class ExportMenu(TiliaMenu):
    menu_title = "&Export..."
    items = [
        (MenuItemKind.ACTION, "file_export_json"),
        (MenuItemKind.ACTION, "file_export_img"),
    ]


class FileMenu(TiliaMenu):
    menu_title = "&File"
    items = [
        (MenuItemKind.ACTION, "file_new"),
        (MenuItemKind.ACTION, "file_open"),
        (MenuItemKind.SUBMENU, RecentFilesMenu),
        (MenuItemKind.ACTION, "file_save"),
        (MenuItemKind.ACTION, "file_save_as"),
        (MenuItemKind.SUBMENU, ExportMenu),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.SUBMENU, LoadMediaMenu),
        (MenuItemKind.ACTION, "metadata_window_open"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "autosaves_folder_open"),
    ]


class EditMenu(TiliaMenu):
    menu_title = "&Edit"
    items = [
        (MenuItemKind.ACTION, "edit_undo"),
        (MenuItemKind.ACTION, "edit_redo"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_copy"),
        (MenuItemKind.ACTION, "timeline_element_paste"),
        (MenuItemKind.ACTION, "timeline_element_paste_complete"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "settings_window_open"),
    ]


class AddTimelinesMenu(TiliaMenu):
    menu_title = "&Add"

    def __init__(self):
        commands = [
            f"timelines.add.{get_timeline_name(kind)}"
            for kind in timeline_kinds.NOT_SLIDER
        ]
        self.items = [(MenuItemKind.ACTION, command) for command in commands]
        super().__init__()


class HierarchyMenu(TiliaMenu):
    menu_title = "&Hierarchy"
    items = [(MenuItemKind.ACTION, "timelines.import.hierarchy")]


class MarkerMenu(TiliaMenu):
    menu_title = "&Marker"
    items = [(MenuItemKind.ACTION, "timelines.import.marker")]


class BeatMenu(TiliaMenu):
    menu_title = "&Beat"
    items = [
        (MenuItemKind.ACTION, "timelines.import.beat"),
        (MenuItemKind.ACTION, "beat_timeline_fill"),
    ]


class HarmonyMenu(TiliaMenu):
    menu_title = "Ha&rmony"
    items = [(MenuItemKind.ACTION, "timelines.import.harmony")]


class PdfMenu(TiliaMenu):
    menu_title = "&PDF"
    items = [(MenuItemKind.ACTION, "timelines.import.pdf")]


class ScoreMenu(TiliaMenu):
    menu_title = "&Score"
    items = [(MenuItemKind.ACTION, "timelines.import.score")]


class TimelinesMenu(TiliaMenu):
    menu_title = "&Timelines"
    items = [
        (MenuItemKind.SUBMENU, AddTimelinesMenu),
        (MenuItemKind.ACTION, "window_manage_timelines_open"),
        (MenuItemKind.ACTION, "timelines_clear"),
        (MenuItemKind.SUBMENU, HierarchyMenu),
        (MenuItemKind.SUBMENU, MarkerMenu),
        (MenuItemKind.SUBMENU, BeatMenu),
        (MenuItemKind.SUBMENU, HarmonyMenu),
        (MenuItemKind.SUBMENU, PdfMenu),
        (MenuItemKind.SUBMENU, ScoreMenu),
    ]


class ViewMenu(QMenu):
    def __init__(self):
        super().__init__()
        self.setTitle("&View")
        self.add_default_items()

        self.windows = {}
        listen(self, Post.WINDOW_UPDATE_STATE, self.update_items)

    def add_default_items(self):
        self.addAction(get_qaction("view_zoom_in"))
        self.addAction(get_qaction("view_zoom_out"))

    def update_items(self, window_id: int, window_state: WindowState, window_title=""):
        if not self.windows:
            self.addSeparator()

        if window_id not in self.windows:
            self._get_action(window_id)

        match window_state:
            case WindowState.OPENED:
                self.windows[window_id].blockSignals(True)
                self.windows[window_id].setChecked(True)
                self.windows[window_id].blockSignals(False)
            case WindowState.CLOSED:
                self.windows[window_id].blockSignals(True)
                self.windows[window_id].setChecked(False)
                self.windows[window_id].blockSignals(False)
            case WindowState.DELETED:
                self.removeAction(self.windows[window_id])
                self.windows.pop(window_id)

        if window_title != "":
            self.windows[window_id].setText(window_title)

    def _get_action(self, window_id):
        qaction = QAction(self)
        qaction.setCheckable(True)
        qaction.triggered.connect(
            lambda checked: post(Post.WINDOW_UPDATE_REQUEST, window_id, checked)
        )
        self.addAction(qaction)
        self.windows[window_id] = qaction


class HelpMenu(TiliaMenu):
    menu_title = "&Help"
    items = [
        (MenuItemKind.ACTION, "about_window_open"),
        (MenuItemKind.ACTION, "website_help_open"),
    ]
