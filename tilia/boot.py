import argparse
import os
import sys
import traceback
from collections.abc import Callable
from typing import NoReturn

from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

import tilia.errors
import tilia.utils  # noqa: F401
from tilia.app import App
from tilia.clipboard import Clipboard
from tilia.constants import FILE_EXTENSION
from tilia.dirs import setup_dirs
from tilia.file.autosave import AutoSaver
from tilia.file.file_manager import FileManager
from tilia.log import logger
from tilia.media.player import QtAudioPlayer
from tilia.undo_manager import UndoManager

app = None
ui = None


def handle_exception(type, value, tb):
    if type in (EOFError, KeyboardInterrupt) and ui:
        ui.exit(1, type.__name__)

    exc_message = "".join(traceback.format_exception(type, value, tb))
    if ui:
        ui.show_crash_dialog(exc_message)
    if app:
        logger.file_dump(app.get_app_state())

    logger.critical(exc_message)
    if ui:
        ui.exit(1)


# Qt warnings emitted on every paint while the SVG score viewer is open.
# They are harmless rendering-engine noise but flood the log loudly enough
# to make the app unresponsive (see issue #513).
QT_LOG_NOISE_PATTERNS = (
    "QFont::setPixelSize: Pixel size <= 0",
    "QWindowsFontEngineDirectWrite::addGlyphsToPath: GetGlyphRunOutline failed",
    # Emitted by QtGui's ICC parser when it can't read the description tag of a
    # colour profile - on macOS the display profile is re-parsed for every
    # native window, flooding the log on startup. Purely cosmetic.
    "fromIccProfile: Failed to parse description",
)


def handle_qt_log_message(type, context, msg):
    f_msg = f"[{type.name}] {context.file}:{context.line} - {msg}"
    if type == QtMsgType.QtFatalMsg:
        raise Exception(f_msg)
    if type == QtMsgType.QtWarningMsg and any(p in msg for p in QT_LOG_NOISE_PATTERNS):
        return
    # Qt's "Ambiguous shortcut overload" is logged at warning level and
    # otherwise disappears silently — surface it to the user so we don't
    # miss new collisions in production. Anything registered via
    # commands.register goes through setup_shortcuts which preempts this
    # warning; if we still see it, something is bypassing that system.
    if "Ambiguous shortcut overload" in msg:
        tilia.errors.display(tilia.errors.AMBIGUOUS_SHORTCUT, msg)
    logger.error(f_msg)


def boot():
    sys.excepthook = handle_exception

    args = setup_parser()
    setup_dirs()
    logger.setup()
    q_application = QApplication(sys.argv)
    qInstallMessageHandler(handle_qt_log_message)
    global app, ui
    app = setup_logic()
    ui = setup_ui(q_application, args.user_interface)
    logger.debug("INITIALISED")
    if os.environ.get("ENVIRONMENT") == "dev":
        try:
            # icecream is a replacement for print()
            # Not required, but very useful for debugging.
            # Docs: https://github.com/gruns/icecream
            import icecream

            icecream.install()
        except ImportError:
            pass
    # has to be done after ui has been created, so timelines will get displayed
    if args.file:
        app.on_open(args.file)
    app.setup_file()

    ui.launch()


def setup_parser():
    parser = argparse.ArgumentParser(
        exit_on_error=False, usage="%(prog)s [--user-interface {qt,cli}] [tilia_file]"
    )
    parser.register("type", "tilia file", lambda f: get_initial_file(f, parser.error))
    parser.add_argument("file", type="tilia file", nargs="?", default="")
    parser.add_argument("--user-interface", "-i", choices=["qt", "cli"], default="qt")
    return parser.parse_args()


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
        from tilia.ui.qtui import QtUI, TiliaMainWindow

        mw = TiliaMainWindow()
        return QtUI(q_application, mw)

    elif interface == "cli":
        from tilia.ui.cli.ui import CLI

        return CLI()


def get_initial_file(file: str, error: Callable[[str], NoReturn]) -> str:
    """
    Checks if a file path was passed as an argument to process.
    If it was, returns its path. Else, returns the empty string.
    """
    f_ext = "." + FILE_EXTENSION
    if not file:
        return file
    if not os.path.isfile(file):
        error(f"{file} is not a valid file.")
    if not file.lower().endswith(f_ext.lower()):
        error(f"{file} is not a {f_ext} file.")
    return file
