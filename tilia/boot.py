import argparse
import logging
import os
import sys
import traceback

import dotenv

from tilia import dirs
from tilia.app import App
from tilia.clipboard import Clipboard
from tilia.file.file_manager import FileManager
from tilia.file.autosave import AutoSaver
from tilia.ui.cli.ui import CLI
from tilia.ui.qtui import QtUI
from tilia.undo_manager import UndoManager

logger = logging.getLogger(__name__)

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
    setup_logging(args.logging)  # relies on logging path set by dirs setup
    global app, ui
    app = setup_logic()
    ui = setup_ui(args.user_interface)

    # has to be done after ui has been created, so timelines will get displayed
    if file := get_initial_file(args.file):
        app.file_manager.open(file)
    else:
        app.setup_file()

    ui.launch()


def setup_parser():
    parser = argparse.ArgumentParser(exit_on_error=False)
    parser.add_argument(
        "--logging",
        "-l",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE"],
        default="INFO",
    )
    parser.add_argument("file", nargs="?", default="")
    parser.add_argument("--user-interface", "-i", choices=["qt", "cli"], default="qt")
    return parser.parse_args()


def setup_dirs():
    dirs.setup_dirs()


def setup_logging(level: str):
    file_mode = 'w'
    format_ = " %(name)-50s %(lineno)-5s %(levelname)-8s %(message)s"
    try:
        logging.basicConfig(
            filename=dirs.log_path,
            filemode=file_mode,
            level=level,
            format=format_,
        )
    except PermissionError:
        logging.basicConfig(
            filemode=file_mode,
            level=level,
            format=format_,
        )


def setup_logic(autosaver=True):
    file_manager = FileManager()
    clipboard = Clipboard()
    undo_manager = UndoManager()

    _app = App(
        file_manager=file_manager,
        clipboard=clipboard,
        undo_manager=undo_manager,
    )

    if autosaver:
        AutoSaver(_app.get_app_state)

    return _app


def setup_ui(interface: str):
    if interface == "qt":
        return QtUI()
    elif interface == "cli":
        return CLI()


def get_initial_file(file: str):
    """
    Checks if a file path was passed as an argument to process.
    If it was, returns its path. Else, returns the empty string.
    """
    if file and os.path.isfile(file) and file.endswith(".tla"):
        logger.info(f"Opening file provided at startup: {file}")
        return file
    else:
        return ""
