from PySide6.QtWidgets import QMainWindow

from tilia.ui.menus import FileMenu, EditMenu, TimelinesMenu, ViewMenu, HelpMenu


class TiliaMenuBar:
    menu_classes = [FileMenu, EditMenu, TimelinesMenu, ViewMenu, HelpMenu]

    def __init__(self, main_window: QMainWindow):
        self.menu_bar = main_window.menuBar()
        self.class_to_menu = {}
        self._setup_menus()

    def _setup_menus(self):
        for cls in self.menu_classes:
            menu = cls()
            self.menu_bar.addMenu(menu)
            self.class_to_menu[cls] = menu

    def get_menu(self, cls):
        return self.class_to_menu[cls]
