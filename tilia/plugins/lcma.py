from tilia.requests import Get, get
from tilia.ui import commands
from tilia.ui.menus import TiliaMenu, MenuItemKind


class LCMAPlugin:
    def __init__(self):
        self._register_commands()

        try:
            commands.execute("ui.add_menu", LCMAMenu)
        except ValueError:
            # We are probably in cli mode
            pass

    def _register_commands(self):
        commands.register(
            "lcma.save_and_export_to_json",
            self.save_and_export_to_json,
            "Save and export",
            shortcut="Ctrl+Shift+J",
        )

    def save_and_export_to_json(self):
        commands.execute("file.save")
        commands.execute(
            "file.export.json", get(Get.FILE_PATH).replace(".tla", ".json")
        )


class LCMAMenu(TiliaMenu):
    menu_title = "LCMA"
    items = [
        (MenuItemKind.COMMAND, "lcma.save_and_export_to_json"),
    ]
