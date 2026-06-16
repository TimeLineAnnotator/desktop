from __future__ import annotations

from enum import Enum, auto
from typing import TypeAlias

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from tilia.requests.post import Post, listen, post
from tilia.settings import settings
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.slider.timeline import SliderTimeline
from tilia.ui import commands
from tilia.ui.commands import get_qaction
from tilia.ui.enums import WindowState


class MenuItemKind(Enum):
    COMMAND = auto()
    SEPARATOR = auto()
    SUBMENU = auto()


TiliaMenuItem: TypeAlias = None | type[QMenu] | str


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

    def add_action(self, name: TiliaMenuItem):
        self.addAction(get_qaction(name))

    def get_submenu(self, cls: type[QMenu]):
        return self.class_to_submenu[cls]


class LoadMediaMenu(TiliaMenu):
    menu_title = "&Load media"
    items = [
        (MenuItemKind.COMMAND, "media.load.local"),
        (MenuItemKind.COMMAND, "media.load.youtube"),
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
        qaction.triggered.connect(lambda _: commands.execute("file.open", file))
        return qaction

    def update_items(self):
        self.clear()
        self.add_items()


class ExportMenu(TiliaMenu):
    menu_title = "&Export..."
    items = [
        (MenuItemKind.COMMAND, "file.export.json"),
        (MenuItemKind.COMMAND, "file.export.img"),
    ]


class FileMenu(TiliaMenu):
    menu_title = "&File"
    items = [
        (MenuItemKind.COMMAND, "file.new"),
        (MenuItemKind.COMMAND, "file.open"),
        (MenuItemKind.SUBMENU, RecentFilesMenu),
        (MenuItemKind.COMMAND, "file.save"),
        (MenuItemKind.COMMAND, "file.save_as"),
        (MenuItemKind.SUBMENU, ExportMenu),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.SUBMENU, LoadMediaMenu),
        (MenuItemKind.COMMAND, "window.open.metadata"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "folder.open.autosaves"),
    ]


class EditMenu(TiliaMenu):
    menu_title = "&Edit"
    items = [
        (MenuItemKind.COMMAND, "edit.undo"),
        (MenuItemKind.COMMAND, "edit.redo"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.copy"),
        (MenuItemKind.COMMAND, "timeline.component.paste"),
        (MenuItemKind.COMMAND, "timeline.component.paste_complete"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "window.open.settings"),
    ]


class AddTimelinesMenu(TiliaMenu):
    menu_title = "&Add"

    def __init__(self):
        commands = [
            f"timelines.add.{cls.type_name().lower()}"
            for cls in Timeline.subclasses()
            if cls is not SliderTimeline
        ]
        self.items = [(MenuItemKind.COMMAND, command) for command in sorted(commands)]
        super().__init__()


class HierarchyMenu(TiliaMenu):
    menu_title = "&Hierarchy"
    items = [(MenuItemKind.COMMAND, "timelines.import.hierarchy")]


class MarkerMenu(TiliaMenu):
    menu_title = "&Marker"
    items = [(MenuItemKind.COMMAND, "timelines.import.marker")]


class BeatMenu(TiliaMenu):
    menu_title = "&Beat"
    items = [
        (MenuItemKind.COMMAND, "timelines.import.beat"),
        (MenuItemKind.COMMAND, "timeline.beat.fill"),
    ]


class HarmonyMenu(TiliaMenu):
    menu_title = "Ha&rmony"
    items = [(MenuItemKind.COMMAND, "timelines.import.harmony")]


class PdfMenu(TiliaMenu):
    menu_title = "&PDF"
    items = [(MenuItemKind.COMMAND, "timelines.import.pdf")]


class ScoreMenu(TiliaMenu):
    menu_title = "&Score"
    items = [(MenuItemKind.COMMAND, "timelines.import.score")]


class TimelinesMenu(TiliaMenu):
    menu_title = "&Timelines"
    items = [
        (MenuItemKind.SUBMENU, AddTimelinesMenu),
        (MenuItemKind.COMMAND, "window.open.manage_timelines"),
        (MenuItemKind.COMMAND, "timelines.clear_all"),
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
        self.addAction(get_qaction("view.zoom.in"))
        self.addAction(get_qaction("view.zoom.out"))

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
        (MenuItemKind.COMMAND, "window.open.about"),
        (MenuItemKind.COMMAND, "open_website_help"),
    ]
