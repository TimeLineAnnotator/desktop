from __future__ import annotations

import re
from functools import partial
from pathlib import Path

from typing import Optional

from PyQt6 import QtGui
from PyQt6.QtCore import QKeyCombination, Qt, qInstallMessageHandler, QUrl, QtMsgType
from PyQt6.QtGui import QIcon, QFontDatabase, QDesktopServices, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow,
    QApplication,
    QToolBar,
    QDialog,
    QDockWidget,
    QGraphicsScene,
)

import tilia.constants
import tilia.errors
from tilia.file.tilia_file import TiliaFile
import tilia.ui.dialogs.file
import tilia.ui.timelines.constants
import tilia.parsers.csv.pdf
import tilia.parsers.csv.harmony
import tilia.parsers.csv.hierarchy
import tilia.parsers.csv.beat
import tilia.parsers.csv.marker
import tilia.parsers.score.musicxml
from . import actions
from .actions import TiliaAction
from .dialog_manager import DialogManager
from .dialogs.basic import display_error
from .dialogs.crash import CrashDialog
from .dialogs.resize_rect import ResizeRect
from .menubar import TiliaMenuBar
from tilia.ui.timelines.collection.collection import TimelineUIs
from .menus import (
    TimelinesMenu,
    HierarchyMenu,
    MarkerMenu,
    BeatMenu,
    HarmonyMenu,
    PdfMenu,
    ScoreMenu,
)
from .options_toolbar import OptionsToolbar
from .player import PlayerToolbar
from .ui_import import on_import_to_timeline
from .windows.manage_timelines import ManageTimelines
from .windows.metadata import MediaMetadataWindow
from .windows.about import About
from .windows.inspect import Inspect
from .windows.settings import SettingsWindow
from .windows.kinds import WindowKind
from ..dirs import IMG_DIR
from ..media.player import QtVideoPlayer, QtAudioPlayer, YouTubePlayer
from tilia import constants
from tilia.log import logger
from tilia.settings import settings
from tilia.utils import get_tilia_class_string
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.requests import Post, listen, post, serve, Get, get


class TiliaMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tilia.constants.APP_NAME)
        self.setWindowIcon(QIcon(str(IMG_DIR / "main_icon.png")))
        self.setStatusTip("Main window")
        qInstallMessageHandler(self.handle_qt_log_message)

    @staticmethod
    def handle_qt_log_message(type, _, msg):
        if type == QtMsgType.QtFatalMsg:
            raise Exception(f"{type.name}: {msg}")
        else:
            logger.error(f"{type.name}: {msg}")

    def keyPressEvent(self, event: Optional[QtGui.QKeyEvent]) -> None:
        if event is None:
            return
        # these shortcuts have to be 'captured' manually. I don't know why.
        key_comb_to_taction = [
            (
                QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_C),
                TiliaAction.TIMELINE_ELEMENT_COPY,
            ),
            (
                QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_V),
                TiliaAction.TIMELINE_ELEMENT_PASTE,
            ),
            (
                QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Delete),
                TiliaAction.TIMELINE_ELEMENT_DELETE,
            ),
            (
                QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Return),
                TiliaAction.TIMELINE_ELEMENT_INSPECT,
            ),
            (
                QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Enter),
                TiliaAction.TIMELINE_ELEMENT_INSPECT,
            ),
        ]

        for comb, taction in key_comb_to_taction:
            if event.keyCombination() == comb:
                actions.get_qaction(taction).trigger()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        actions.trigger(TiliaAction.APP_CLOSE)
        event.ignore()

    def on_close(self):
        super().closeEvent(None)

    def on_export(self, save_path: str):
        widget: QGraphicsScene = self.centralWidget().scene()
        success, result = ResizeRect.new_size(
            widget.sceneRect().width(), widget.sceneRect().height()
        )
        if not success:
            return

        if result != widget.sceneRect().width():
            margins = 2 * get(Get.LEFT_MARGIN_X)
            zoom_level = (result - margins) / (widget.sceneRect().width() - margins)
            post(Post.VIEW_ZOOM_IN, zoom_level)
        else:
            zoom_level = 1.0

        image = QPixmap(widget.sceneRect().size().toSize())
        painter = QPainter(image)
        widget.render(painter)
        image.save(save_path)
        del painter
        del image

        if zoom_level != 1.0:
            post(Post.VIEW_ZOOM_OUT, zoom_level)


class QtUI:
    def __init__(self, q_application: QApplication, mw: TiliaMainWindow):
        self.app = None
        self.q_application = q_application
        self._setup_main_window(mw)
        self._setup_fonts()
        self._setup_sizes()
        self._setup_requests()
        self._setup_actions()
        self._setup_widgets()
        self._setup_dialog_manager()
        self._setup_menus()
        self._setup_windows()

        self.is_error = False

    def __str__(self):
        return get_tilia_class_string(self)

    @property
    def timeline_width(self):
        return self.playback_area_width + 2 * self.playback_area_margin

    def _setup_sizes(self):
        self.playback_area_width = tilia.ui.timelines.constants.PLAYBACK_AREA_WIDTH
        self.playback_area_margin = tilia.ui.timelines.constants.PLAYBACK_AREA_MARGIN

    def _setup_requests(self):
        LISTENS = {
            (Post.APP_FILE_LOAD, self.on_file_load),
            (Post.PLAYBACK_AREA_SET_WIDTH, self.on_timeline_set_width),
            (Post.UI_MEDIA_LOAD_LOCAL, self.on_media_load_local),
            (Post.UI_MEDIA_LOAD_YOUTUBE, self.on_media_load_youtube),
            (Post.TIMELINE_ELEMENT_INSPECT, self.on_timeline_element_inspect),
            (Post.WEBSITE_HELP_OPEN, self.on_website_help_open),
            (Post.WINDOW_OPEN, self.on_window_open),
            (Post.WINDOW_CLOSE, self.on_window_close),
            (Post.WINDOW_CLOSE_DONE, self.on_window_close_done),
            (Post.REQUEST_CLEAR_UI, self.on_clear_ui),
            (Post.TIMELINE_KIND_INSTANCED, self.on_timeline_kind_change),
            (Post.TIMELINE_KIND_NOT_INSTANCED, self.on_timeline_kind_change),
            (Post.IMPORT_CSV, self.on_import_to_timeline),
            (
                Post.IMPORT_MUSICXML,
                partial(self.on_import_to_timeline, TlKind.SCORE_TIMELINE),
            ),
            (Post.DISPLAY_ERROR, display_error),
            (Post.UI_EXIT, self.exit),
        }

        SERVES = {
            (Get.TIMELINE_WIDTH, lambda: self.timeline_width),
            (Get.PLAYBACK_AREA_WIDTH, lambda: self.playback_area_width),
            (Get.LEFT_MARGIN_X, lambda: self.playback_area_margin),
            (
                Get.RIGHT_MARGIN_X,
                lambda: self.playback_area_width + self.playback_area_margin,
            ),
            (Get.WINDOW_GEOMETRY, self.get_window_geometry),
            (Get.WINDOW_STATE, self.get_window_state),
            (Get.PLAYER_CLASS, self.get_player_class),
            (Get.MAIN_WINDOW, lambda: self.main_window),
        }

        for post_, callback in LISTENS:
            listen(self, post_, callback)

        for request, callback in SERVES:
            serve(self, request, callback)

    def _setup_main_window(self, mw: TiliaMainWindow):
        self.main_window = mw

    @staticmethod
    def _setup_fonts():
        fonts_dir = Path(__file__).parent / "fonts"
        fonts = ["MusAnalysis.otf"]
        for font in fonts:
            font_path = str(Path(fonts_dir, font).resolve())
            QFontDatabase.addApplicationFont(font_path)

    def _setup_dialog_manager(self):
        self.dialog_manager = DialogManager()

    def _setup_menus(self):
        self.menu_bar = TiliaMenuBar(self.main_window)
        self._setup_dynamic_menus()

    def _setup_dynamic_menus(self):
        menu_info = {
            (TlKind.MARKER_TIMELINE, MarkerMenu),
            (TlKind.HIERARCHY_TIMELINE, HierarchyMenu),
            (TlKind.BEAT_TIMELINE, BeatMenu),
            (TlKind.HARMONY_TIMELINE, HarmonyMenu),
            (TlKind.PDF_TIMELINE, PdfMenu),
            (TlKind.SCORE_TIMELINE, ScoreMenu),
        }
        self.kind_to_dynamic_menus = {
            kind: self.menu_bar.get_menu(TimelinesMenu).get_submenu(menu_class)
            for kind, menu_class in menu_info
        }
        self.update_dynamic_menus()

    def _setup_windows(self):
        self._windows: dict[WindowKind, QDialog | QDockWidget | None] = {
            WindowKind.INSPECT: None,
            WindowKind.MEDIA_METADATA: None,
            WindowKind.MANAGE_TIMELINES: None,
            WindowKind.ABOUT: None,
            WindowKind.SETTINGS: None,
        }

    def update_dynamic_menus(self):
        instanced_kinds = [tlui.TIMELINE_KIND for tlui in get(Get.TIMELINE_UIS)]
        for kind in [
            TlKind.HIERARCHY_TIMELINE,
            TlKind.BEAT_TIMELINE,
            TlKind.MARKER_TIMELINE,
            TlKind.HARMONY_TIMELINE,
            TlKind.PDF_TIMELINE,
            TlKind.SCORE_TIMELINE,
        ]:
            if kind in instanced_kinds:
                self.show_dynamic_menus(kind)
            else:
                self.hide_dynamic_menus(kind)

    def show_dynamic_menus(self, kind: TlKind):
        self.kind_to_dynamic_menus[kind].menuAction().setVisible(True)

    def hide_dynamic_menus(self, kind: TlKind):
        self.kind_to_dynamic_menus[kind].menuAction().setVisible(False)

    def on_timeline_kind_change(self, _: TlKind):
        self.update_dynamic_menus()

    def on_timeline_set_width(self, value: int) -> None:
        if value < 0:
            raise ValueError(f"Timeline width must be positive. Got {value=}")

        self.playback_area_width = value
        post(Post.TIMELINE_WIDTH_SET_DONE, self.timeline_width)

    def launch(self):
        self.main_window.show()
        return self.q_application.exec()

    def exit(self, code: int):
        # Code = 0 means a succesful run, code = 1 means an unhandled exception.
        self.q_application.exit(code)

    def get_window_geometry(self):
        return self.main_window.saveGeometry()

    def get_window_state(self):
        return self.main_window.saveState()

    def on_file_load(self, file: TiliaFile) -> None:
        geometry, state = settings.get_geometry_and_state_from_path(file.file_path)
        if geometry and state:
            self.main_window.restoreGeometry(geometry)
            self.main_window.restoreState(state)

    def _setup_widgets(self):
        self.timeline_toolbars = QToolBar()
        self.timeline_uis = TimelineUIs(self.main_window)
        self.player_toolbar = PlayerToolbar()
        self.options_toolbar = OptionsToolbar()

        self.main_window.addToolBar(self.player_toolbar)
        self.main_window.addToolBar(self.options_toolbar)

    def _setup_actions(self):
        actions.setup_actions(self.main_window)

    def on_window_open(self, kind: WindowKind):
        """Open a window of 'kind', if there is no window of that kind open.
        Otherwise, focus window of that kind."""

        kind_to_constructor = {
            WindowKind.INSPECT: self.open_inspect_window,
            WindowKind.MANAGE_TIMELINES: ManageTimelines,
            WindowKind.MEDIA_METADATA: self.open_media_metadata_window,
            WindowKind.ABOUT: self.open_about_window,
            WindowKind.SETTINGS: self.open_settings_window,
        }

        if not self._windows[kind]:
            window = kind_to_constructor[kind]()
        else:
            window = self._windows[kind]

        if window:
            self._windows[kind] = window
            if isinstance(window, QDialog):
                window.activateWindow()
            elif isinstance(window, QDockWidget):
                window.setFocus()
            window.raise_()

    def open_inspect_window(self):
        widget = Inspect(self.main_window)
        self.main_window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, widget)
        return widget

    def open_about_window(self):
        return About(self.main_window)

    @staticmethod
    def open_media_metadata_window():
        return MediaMetadataWindow()

    @staticmethod
    def open_settings_window():
        return SettingsWindow()

    def on_window_close(self, kind: WindowKind):
        if window := self._windows[kind]:
            window.close()
            self.on_window_close_done(kind)  # should post appropriate event instead

    def on_window_close_done(self, kind: WindowKind):
        self._windows[kind] = None

    def is_window_open(self, kind: WindowKind):
        return self._windows[kind] is not None

    def on_timeline_element_inspect(self):
        if not get(Get.TIMELINE_ELEMENTS_SELECTED):
            return
        self.on_window_open(WindowKind.INSPECT)

    @staticmethod
    def on_media_load_local():
        success, path = get(Get.FROM_USER_MEDIA_PATH)
        if success:
            post(Post.APP_MEDIA_LOAD, path)

    @staticmethod
    def on_media_load_youtube():
        accepted, url = get(
            Get.FROM_USER_STRING, "Load from Youtube", "Enter YouTube URL"
        )
        match = re.match(tilia.constants.YOUTUBE_URL_REGEX, url)
        if not accepted:
            return
        if not match:
            tilia.errors.display(tilia.errors.YOUTUBE_URL_INVALID, url)
            return

        post(Post.APP_MEDIA_LOAD, url)

    def on_clear_ui(self):
        """Closes all UI windows."""
        for kind, window in self._windows.items():
            if window is not None:
                window.close()
        self.main_window.setFocus()

    def on_website_help_open(self):
        QDesktopServices.openUrl(QUrl(f"{constants.WEBSITE_URL}/help"))

    def on_import_to_timeline(self, tl_kind: TlKind):
        prev_state = get(Get.APP_STATE)
        status, errors = on_import_to_timeline(self.timeline_uis, tl_kind)

        if status == "failure":
            post(Post.APP_STATE_RESTORE, prev_state)
            if errors:
                tilia.errors.display(tilia.errors.CSV_IMPORT_FAILED, "\n".join(errors))
        elif status == "success" and errors:
            tilia.errors.display(
                tilia.errors.CSV_IMPORT_SUCCESS_ERRORS, "\n".join(errors)
            )
            post(Post.APP_RECORD_STATE, "Import from csv file")

    @staticmethod
    def show_crash_dialog(exception_info):
        dialog = CrashDialog(exception_info)
        dialog.exec()

    @staticmethod
    def get_player_class(media_type: str):
        return {
            "video": QtVideoPlayer,
            "audio": QtAudioPlayer,
            "youtube": YouTubePlayer,
        }[media_type]
