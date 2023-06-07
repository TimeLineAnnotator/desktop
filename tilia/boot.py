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
from tilia.ui.tkinterui import TkinterUI
from tilia.undo_manager import UndoManager

logger = logging.getLogger(__name__)


def boot() -> None:
    _setup_dirs()
    _setup_logging()  # relies on logging path set by dirs setup
    _setup_settings()
    app = _setup_logic()
    ui = _setup_ui()

    # has to be done after ui has been created, so timelines will get displayed
    if file := _get_initial_file():
        app.file_manager.open(file)
    else:
        app.setup_blank_file()

    ui.launch()


def _setup_dirs():
    dirs.setup_dirs()


def _setup_settings():
    settings.load(dirs.settings_path)


def _setup_logging():
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "--logging",
        "-l",
        choices=["CRITICAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE"],
        default="INFO",
    )
    argparser.add_argument("file", nargs=argparse.REMAINDER)
    args = argparser.parse_args()

    logging.basicConfig(
        filename=dirs.log_path,
        filemode="w",
        level=args.logging,
        format=" %(name)-50s %(lineno)-5s %(levelname)-8s %(message)s",
    )


def _setup_logic():
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


def _setup_ui():
    root = tk.Tk()
    return TkinterUI(root)


def _get_initial_file():
    """
    Checks if a file path was passed as an argument to process.
    If it was, returns its path. Else, returns the empty string.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?")
    args = parser.parse_args()

    if args.file and os.path.isfile(args.file) and args.file.endswith(".tla"):
        logger.info(f"Opening file provided at startup: {args.file}")
        return args.file
    else:
        return ""
