from __future__ import annotations

from typing import TypeAlias

from PyQt6.QtWidgets import QMenu

from tilia.ui.actions import TiliaAction, get_qaction


class MenuItemKind:
    SEPARATOR = "separator"
    ACTION = "action"
    SUBMENU = "menu"


TiliaMenuItem: TypeAlias = None | TiliaAction | type["TiliaMenu"]


class TiliaMenu(QMenu):
    title = ""
    items: list[tuple[MenuItemKind, TiliaMenuItem]] = []

    def __init__(self):
        super().__init__()
        self.setTitle(self.title)
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
    title = "Load media"
    items = [
        (MenuItemKind.ACTION, TiliaAction.MEDIA_LOAD_LOCAL),
        (MenuItemKind.ACTION, TiliaAction.MEDIA_LOAD_YOUTUBE),
    ]


class FileMenu(TiliaMenu):
    title = "File"
    items = [
        (MenuItemKind.ACTION, TiliaAction.FILE_NEW),
        (MenuItemKind.ACTION, TiliaAction.FILE_OPEN),
        (MenuItemKind.ACTION, TiliaAction.FILE_SAVE),
        (MenuItemKind.ACTION, TiliaAction.FILE_SAVE_AS),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.SUBMENU, LoadMediaMenu),
        (MenuItemKind.ACTION, TiliaAction.METADATA_WINDOW_OPEN),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.SETTINGS_WINDOW_OPEN),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.AUTOSAVES_FOLDER_OPEN),
    ]


class EditMenu(TiliaMenu):
    title = "Edit"
    items = [
        (MenuItemKind.ACTION, TiliaAction.EDIT_UNDO),
        (MenuItemKind.ACTION, TiliaAction.EDIT_REDO),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COPY),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE),
    ]


class AddTimelinesMenu(TiliaMenu):
    title = "Add..."
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_BEAT_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_HARMONY_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_MARKER_TIMELINE),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_ADD_AUDIOWAVE_TIMELINE)
    ]


class HierarchyMenu(TiliaMenu):
    title = "Hierarchy"
    items = [(MenuItemKind.ACTION, TiliaAction.HIERARCHY_IMPORT_FROM_CSV)]


class MarkerMenu(TiliaMenu):
    title = "Marker"
    items = [(MenuItemKind.ACTION, TiliaAction.MARKER_IMPORT_FROM_CSV)]


class BeatMenu(TiliaMenu):
    title = "Beat"
    items = [(MenuItemKind.ACTION, TiliaAction.BEAT_IMPORT_FROM_CSV)]


class HarmonyMenu(TiliaMenu):
    title = "Harmony"
    items = [(MenuItemKind.ACTION, TiliaAction.HARMONY_IMPORT_FROM_CSV)]


class TimelinesMenu(TiliaMenu):
    title = "Timelines"
    items = [
        (MenuItemKind.SUBMENU, AddTimelinesMenu),
        (MenuItemKind.ACTION, TiliaAction.WINDOW_MANAGE_TIMELINES_OPEN),
        (MenuItemKind.ACTION, TiliaAction.TIMELINES_CLEAR),
        (MenuItemKind.SUBMENU, HierarchyMenu),
        (MenuItemKind.SUBMENU, MarkerMenu),
        (MenuItemKind.SUBMENU, BeatMenu),
        (MenuItemKind.SUBMENU, HarmonyMenu),
    ]


class ViewMenu(TiliaMenu):
    title = "View"
    items = [
        (MenuItemKind.ACTION, TiliaAction.VIEW_ZOOM_IN),
        (MenuItemKind.ACTION, TiliaAction.VIEW_ZOOM_OUT),
    ]


class HelpMenu(TiliaMenu):
    title = "Help"
    items = [
        (MenuItemKind.ACTION, TiliaAction.ABOUT_WINDOW_OPEN),
        (MenuItemKind.ACTION, TiliaAction.WEBSITE_HELP_OPEN)
    ]
