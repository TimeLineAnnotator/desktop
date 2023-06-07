import argparse
import logging
import os
import tkinter as tk

from tilia import dirs, settings
from tilia.app import App
from tilia.clipboard import Clipboard
from tilia.file.file_manager import FileManager
from tilia.file.autosave import AutoSaver
from tilia.media.player import PygamePlayer
from tilia.ui.cli.ui import CLI
from tilia.ui.tkinterui import TkinterUI
from tilia.undo_manager import UndoManager

logger = logging.getLogger(__name__)


def boot() -> None:
    args = setup_parser()
    print(args.logging)
    print(args.user_interface)
    print(args.file)
    setup_dirs()
    setup_logging(args.logging)  # relies on logging path set by dirs setup
    setup_settings()
    app = setup_logic()
    ui = setup_ui(args.user_interface)

    # has to be done after ui has been created, so timelines will get displayed
    if file := get_initial_file(args.file):
        app.file_manager.open(file)
    else:
        app.setup_blank_file()

    ui.launch()


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--logging",
        "-l",
        choices=["CRITICAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE"],
        default="INFO",
    )
    parser.add_argument("file", nargs="?", default="")
    parser.add_argument("--user-interface", choices=["tk", "cli"], default="tk")
    return parser.parse_args()


def setup_dirs():
    dirs.setup_dirs()


def setup_settings():
    settings.load(dirs.settings_path)


def setup_logging(level: str):
    logging.basicConfig(
        filename=dirs.log_path,
        filemode="w",
        level=level,
        format=" %(name)-50s %(lineno)-5s %(levelname)-8s %(message)s",
    )


def setup_logic():
    player = PygamePlayer()
    file_manager = FileManager()
    clipboard = Clipboard()
    undo_manager = UndoManager()

    app = App(
        player=player,
        file_manager=file_manager,
        clipboard=clipboard,
        undo_manager=undo_manager,
    )

    AutoSaver(app.get_app_state)

    return app


def setup_ui(interface: str):
    if interface == "tk":
        root = tk.Tk()
        return TkinterUI(root)
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
