import argparse
import os
import sys
import traceback

from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

import tilia.utils  # noqa: F401
from tilia.app import App
from tilia.clipboard import Clipboard
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
)


def handle_qt_log_message(type, context, msg):
    f_msg = f"[{type.name}] {context.file}:{context.line} - {msg}"
    if type == QtMsgType.QtFatalMsg:
        raise Exception(f_msg)
    if type == QtMsgType.QtWarningMsg and any(p in msg for p in QT_LOG_NOISE_PATTERNS):
        return
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
    if file := get_initial_file(args.file):
        app.on_open(file)
    else:
        app.setup_file()

    ui.launch()


def setup_parser():
    parser = argparse.ArgumentParser(exit_on_error=False)
    parser.add_argument("--file", nargs="?", default="")
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


def get_initial_file(file: str):
    """
    Checks if a file path was passed as an argument to process.
    If it was, returns its path. Else, returns the empty string.
    """
    if file and os.path.isfile(file) and file.endswith(".tla"):
        return file
    else:
        return ""
