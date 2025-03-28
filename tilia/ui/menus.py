from __future__ import annotations

from typing import TypeAlias
from enum import Enum, auto

from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction

from tilia.ui.actions import TiliaAction, get_qaction
from tilia.settings import settings
from tilia.requests.post import post, Post, listen
from tilia.ui.enums import WindowState


class MenuItemKind(Enum):
    SEPARATOR = auto()
    ACTION = auto()
    SUBMENU = auto()


TiliaMenuItem: TypeAlias = None | TiliaAction | type[QMenu]


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

    def add_action(self, t_action: TiliaAction):
        self.addAction(get_qaction(t_action))

    def get_submenu(self, cls: type[TiliaMenu]):
        return self.class_to_submenu[cls]


class LoadMediaMenu(TiliaMenu):
    menu_title = "&Load media"
    items = [
        (MenuItemKind.ACTION, TiliaAction.MEDIA_LOAD_LOCAL),
        (MenuItemKind.ACTION, TiliaAction.MEDIA_LOAD_YOUTUBE),
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


class FileMenu(TiliaMenu):
    menu_title = "&File"
    items = [
        (MenuItemKind.ACTION, TiliaAction.FILE_NEW),
        (MenuItemKind.ACTION, TiliaAction.FILE_OPEN),
        (MenuItemKind.SUBMENU, RecentFilesMenu),
        (MenuItemKind.ACTION, TiliaAction.FILE_SAVE),
        (MenuItemKind.ACTION, TiliaAction.FILE_SAVE_AS),
        (MenuItemKind.ACTION, TiliaAction.FILE_EXPORT),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.SUBMENU, LoadMediaMenu),
        (MenuItemKind.ACTION, TiliaAction.METADATA_WINDOW_OPEN),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.AUTOSAVES_FOLDER_OPEN),
    ]


class EditMenu(TiliaMenu):
    menu_title = "&Edit"
    items = [
        (MenuItemKind.ACTION, TiliaAction.EDIT_UNDO),
        (MenuItemKind.ACTION, TiliaAction.EDIT_REDO),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COPY),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.SETTINGS_WINDOW_OPEN),
    ]


class AddTimelinesMenu(TiliaMenu):
    menu_title = "&Add"
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_AUDIOWAVE_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_BEAT_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_HARMONY_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_MARKER_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_PDF_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_SCORE_TIMELINE),
    ]


class HierarchyMenu(TiliaMenu):
    menu_title = "&Hierarchy"
    items = [(MenuItemKind.ACTION, TiliaAction.IMPORT_CSV_HIERARCHY_TIMELINE)]


class MarkerMenu(TiliaMenu):
    menu_title = "&Marker"
    items = [(MenuItemKind.ACTION, TiliaAction.IMPORT_CSV_MARKER_TIMELINE)]


class BeatMenu(TiliaMenu):
    menu_title = "&Beat"
    items = [
        (MenuItemKind.ACTION, TiliaAction.IMPORT_CSV_BEAT_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.BEAT_TIMELINE_FILL),
    ]


class HarmonyMenu(TiliaMenu):
    menu_title = "Ha&rmony"
    items = [(MenuItemKind.ACTION, TiliaAction.IMPORT_CSV_HARMONY_TIMELINE)]


class PdfMenu(TiliaMenu):
    menu_title = "&PDF"
    items = [(MenuItemKind.ACTION, TiliaAction.IMPORT_CSV_PDF_TIMELINE)]


class ScoreMenu(TiliaMenu):
    menu_title = "&Score"
    items = [(MenuItemKind.ACTION, TiliaAction.IMPORT_MUSICXML)]


class TimelinesMenu(TiliaMenu):
    menu_title = "&Timelines"
    items = [
        (MenuItemKind.SUBMENU, AddTimelinesMenu),
        (MenuItemKind.ACTION, TiliaAction.WINDOW_MANAGE_TIMELINES_OPEN),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_CLEAR),
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
        self.addAction(get_qaction(TiliaAction.VIEW_ZOOM_IN))
        self.addAction(get_qaction(TiliaAction.VIEW_ZOOM_OUT))

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
        (MenuItemKind.ACTION, TiliaAction.ABOUT_WINDOW_OPEN),
        (MenuItemKind.ACTION, TiliaAction.WEBSITE_HELP_OPEN),
    ]
