from tilia.ui import commands
from tilia.ui.menus import TiliaMenu, MenuItemKind


class LCMAPlugin:
    def __init__(self):
        self._register_commands()

        commands.execute("ui.add_menu", LCMAMenu)

    def _register_commands(self):
        commands.register("lcma.test", lambda: print("An experimental plugin"))


class LCMAMenu(TiliaMenu):
    menu_title = "LCMA"
    items = [
        (MenuItemKind.COMMAND, "lcma.test"),
    ]
