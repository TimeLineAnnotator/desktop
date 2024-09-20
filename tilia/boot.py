import argparse
import os
import sys
import traceback

import dotenv
from PyQt6.QtWidgets import QApplication

from tilia import dirs
from tilia.app import App
from tilia.clipboard import Clipboard
from tilia.file.file_manager import FileManager
from tilia.file.autosave import AutoSaver
from tilia.media.player import QtAudioPlayer
from tilia.ui.actions import setup_actions
from tilia.ui.cli.ui import CLI
from tilia.ui.qtui import QtUI, TiliaMainWindow
from tilia.undo_manager import UndoManager

app = None
ui = None


def handle_expection(type, value, tb):
    if app:
        # The app state should be dumped to a file
        # for debugging purposes.
        print(app.get_app_state())
    exc_message = ''.join(traceback.format_exception(type, value, tb))
    if ui:
        # Additonally. the exception info should
        # also be dumped to a file.
        ui.show_crash_dialog(exc_message)
        print(exc_message)
        ui.exit(1)
    else:
        print(exc_message)


def boot():
    sys.excepthook = handle_expection
    dotenv.load_dotenv()
    args = setup_parser()
    setup_dirs()
    q_application = QApplication(sys.argv)
    global app, ui
    app = setup_logic()
    ui = setup_ui(q_application, args.user_interface)

    # has to be done after ui has been created, so timelines will get displayed
    if file := get_initial_file(args.file):
        app.file_manager.open(file)
    else:
        app.setup_file()

    ui.launch()


def setup_parser():
    parser = argparse.ArgumentParser(exit_on_error=False)
    parser.add_argument("file", nargs="?", default="")
    parser.add_argument("--user-interface", "-i", choices=["qt", "cli"], default="qt")
    return parser.parse_args()


def setup_dirs():
    dirs.setup_dirs()


def setup_logic(autosaver=True):
    file_manager = FileManager()
    clipboard = Clipboard()
    undo_manager = UndoManager()
    player = QtAudioPlayer()

    _app = App(
        file_manager=file_manager,
        clipboard=clipboard,
        undo_manager=undo_manager,
        player=player,
    )

    if autosaver:
        AutoSaver(_app.get_app_state)

    return _app


def setup_ui(q_application: QApplication, interface: str):
    if interface == "qt":
        mw = TiliaMainWindow()
        setup_actions(mw)
        return QtUI(q_application, mw)
    elif interface == "cli":
        return CLI()


def get_initial_file(file: str):
    """
    Checks if a file path was passed as an argument to process.
    If it was, returns its path. Else, returns the empty string.
    """
    if file and os.path.isfile(file) and file.endswith(".tla"):
        return file
    else:
        return ""
