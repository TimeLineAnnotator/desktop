from PySide6.QtWidgets import QLabel

import tilia.constants
from tests.utils import get_command_action, get_main_window_menu
from tilia.ui.windows import WindowKind
from tilia.ui.windows.about import License


def test_about_opens_from_menu_and_shows_version_and_license(qtui):
    menu = get_main_window_menu(qtui, "Help")
    action = get_command_action(menu, "window.open.about")
    assert action is not None

    action.trigger()

    assert qtui.is_window_open(WindowKind.ABOUT)
    about_window = qtui._windows[WindowKind.ABOUT]

    # shows the version
    labels = [label.text() for label in about_window.findChildren(QLabel)]
    assert any(tilia.constants.VERSION in text for text in labels)

    # gives access to the license
    about_window.open_link("#license")
    license_windows = about_window.findChildren(License)
    assert len(license_windows) == 1
    assert license_windows[0].isVisible()

    license_windows[0].close()
    about_window.close()
