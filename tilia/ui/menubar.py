from PyQt6.QtWidgets import QMainWindow

from tilia.ui.menus import (
    FileMenu,
    EditMenu,
    TimelinesMenu,
    ViewMenu,
    HelpMenu,
    TiliaMenu,
)


class TiliaMenuBar:
    menu_classes = [FileMenu, EditMenu, TimelinesMenu, ViewMenu, HelpMenu]

    def __init__(self, main_window: QMainWindow):
        self.menu_bar = main_window.menuBar()
        self.class_to_menu = {}
        self._setup_menus()

    def _setup_menus(self):
        for cls in self.menu_classes:
            self.add_menu(cls)

    def get_menu(self, cls):
        return self.class_to_menu[cls]

    def add_menu(self, cls: type[TiliaMenu]):
        menu = cls()
        self.menu_bar.addMenu(menu)
        self.class_to_menu[cls] = menu
