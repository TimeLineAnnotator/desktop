import sys

from tilia.ui.menus import MenuItemKind, _help_menu_items


class TestHelpMenuItems:
    """Windows already gets a proper Add/Remove Programs entry from Velopack,
    so help.uninstall isn't offered there - see tilia/lifecycle.py::uninstall.
    """

    def test_excludes_uninstall_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")

        items = _help_menu_items()

        assert (MenuItemKind.COMMAND, "help.uninstall") not in items

    def test_includes_uninstall_elsewhere(self, monkeypatch):
        for platform in ["darwin", "linux"]:
            monkeypatch.setattr(sys, "platform", platform)

            items = _help_menu_items()

            assert (MenuItemKind.COMMAND, "help.uninstall") in items
