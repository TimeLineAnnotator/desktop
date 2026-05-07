from __future__ import annotations

import functools
import os
import re
from pathlib import Path

from PySide6 import QtGui
from PySide6.QtCore import (
    QEvent,
    QKeyCombination,
    QObject,
    Qt,
    QtMsgType,
    QUrl,
    qInstallMessageHandler,
)
from PySide6.QtGui import QDesktopServices, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QGraphicsScene,
    QMainWindow,
    QToolBar,
)

import tilia.constants
import tilia.errors
import tilia.media.constants
import tilia.parsers.csv.beat
import tilia.parsers.csv.harmony
import tilia.parsers.csv.hierarchy
import tilia.parsers.csv.marker
import tilia.parsers.csv.pdf
import tilia.parsers.score.musicxml
import tilia.ui.dialogs.file
import tilia.ui.timelines.constants
from tilia.file.tilia_file import TiliaFile
from tilia.log import logger
from tilia.requests import Get, Post, get, listen, post, serve
from tilia.settings import settings
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui import commands
from tilia.ui.timelines.collection.collection import TimelineUIs
from tilia.utils import get_tilia_class_string

from ..media.player import QtAudioPlayer, QtVideoPlayer, YouTubePlayer
from .dialog_manager import DialogManager
from .dialogs.basic import display_error
from .dialogs.crash import CrashDialog
from .dialogs.resize_rect import ResizeRect
from .menubar import TiliaMenuBar
from .menus import (
    BeatMenu,
    HarmonyMenu,
    HierarchyMenu,
    MarkerMenu,
    PdfMenu,
    ScoreMenu,
    TimelinesMenu,
)
from .options_toolbar import OptionsToolbar
from .player import PlayerToolbar
from .windows.about import About
from .windows.inspect import Inspect
from .windows.kinds import WindowKind
from .windows.manage_timelines import ManageTimelines
from .windows.metadata import MediaMetadataWindow
from .windows.settings import SettingsWindow


class TiliaMainWindow(QMainWindow):
    def __init__(self):
        QIcon.setThemeSearchPaths([(Path(__file__).parent / "icons").as_posix()])
        QIcon.setThemeName("tilia" + QApplication.styleHints().colorScheme().name)
        super().__init__()
        self.setWindowTitle(tilia.constants.APP_NAME)
        self.setWindowIcon(QIcon.fromTheme("tilia"))
        self.setStatusTip("Main window")
        qInstallMessageHandler(self.handle_qt_log_message)
        self.setAcceptDrops(True)
        self._drop_filter = FileDropEventFilter()

    def setup_qapplication(self, q_application: QApplication):
        q_application.installEventFilter(self._drop_filter)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == event.Type.ThemeChange:
            QIcon.setThemeName("tilia" + QApplication.styleHints().colorScheme().name)

        return super().changeEvent(event)

    # Qt warnings emitted on every paint while the SVG score viewer is open.
    # They are harmless rendering-engine noise but flood the log loudly enough
    # to make the app unresponsive (see issue #513).
    QT_LOG_NOISE_PATTERNS = (
        "QFont::setPixelSize: Pixel size <= 0",
        "QWindowsFontEngineDirectWrite::addGlyphsToPath: GetGlyphRunOutline failed",
    )

    @staticmethod
    def handle_qt_log_message(type, context, msg):
        f_msg = f"[{type.name}] {context.file}:{context.line} - {msg}"
        if type == QtMsgType.QtFatalMsg:
            raise Exception(f_msg)
        if type == QtMsgType.QtWarningMsg and any(
            p in msg for p in TiliaMainWindow.QT_LOG_NOISE_PATTERNS
        ):
            return
        logger.error(f_msg)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event is None:
            return
        # these shortcuts have to be 'captured' manually. I don't know why.
        key_comb_to_taction = [
            (
                QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_C),
                "timeline.component.copy",
            ),
            (
                QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_V),
                "timeline.component.paste",
            ),
            (
                QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Delete),
                "timeline.component.delete",
            ),
            (
                QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Return),
                "timeline.element.inspect",
            ),
            (
                QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Enter),
                "timeline.element.inspect",
            ),
        ]

        for comb, taction in key_comb_to_taction:
            if event.keyCombination() == comb:
                commands.get_qaction(taction).trigger()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        commands.execute("tilia.close")
        event.ignore()

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
            commands.execute("view.zoom.in", zoom_level)
        else:
            zoom_level = 1.0

        image = QPixmap(widget.sceneRect().size().toSize())
        painter = QPainter(image)
        widget.render(painter)
        image.save(save_path)
        del painter
        del image

        if zoom_level != 1.0:
            commands.execute("view.zoom.out", zoom_level)


class FileDropEventFilter(QObject):
    """Routes file drag/drop events from any widget to the main window.

    Qt only delivers drag/drop events to widgets with setAcceptDrops(True),
    and child widgets cover most of TiliaMainWindow, so an app-level filter
    is needed to catch drops anywhere in the window.
    """

    _DRAG_EVENT_TYPES = (
        QEvent.Type.DragEnter,
        QEvent.Type.DragMove,
        QEvent.Type.Drop,
    )

    @staticmethod
    def _is_file_droppable(urls: list[QUrl]):
        if len(urls) != 1 or not urls[0].isLocalFile():
            return False
        ext = Path(urls[0].toLocalFile()).suffix[1:].lower()
        return ext in {tilia.constants.FILE_EXTENSION}.union(
            tilia.media.constants.ALL_SUPPORTED_MEDIA_FORMATS
        )

    @staticmethod
    def _dispatch_dropped_path(path: str) -> None:
        if Path(path).suffix[1:].lower() == tilia.constants.FILE_EXTENSION:
            commands.execute("file.open", path)
        else:
            post(Post.APP_MEDIA_LOAD, path)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() not in self._DRAG_EVENT_TYPES:
            return False
        if not self._is_file_droppable(event.mimeData().urls()):
            return False
        if event.type() == QEvent.Type.Drop:
            path = event.mimeData().urls()[0].toLocalFile()
            self._dispatch_dropped_path(path)
        event.acceptProposedAction()
        return True


class QtUI:
    def __init__(self, q_application: QApplication, mw: TiliaMainWindow):
        self.app = None
        self.q_application = q_application
        self._setup_main_window(mw)
        self._setup_fonts()
        self._setup_sizes()
        self._setup_requests()
        self._setup_commands()
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
            (Post.APP_FILE_LOADED, self.on_file_loaded),
            (Post.PLAYBACK_AREA_SET_WIDTH, self.on_timeline_set_width),
            (Post.WINDOW_OPEN, self.on_window_open),
            (Post.WINDOW_CLOSE, self.on_window_close),
            (Post.WINDOW_CLOSE_DONE, self.on_window_close_done),
            (Post.REQUEST_CLEAR_UI, self.on_clear_ui),
            (Post.TIMELINE_KIND_INSTANCED, self.on_timeline_kind_change),
            (Post.TIMELINE_KIND_NOT_INSTANCED, self.on_timeline_kind_change),
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

    def _setup_commands(self):
        window_commands = [
            ("window.open.metadata", WindowKind.MEDIA_METADATA, "Metadata"),
            ("window.open.settings", WindowKind.SETTINGS, "Settings"),
            ("window.open.manage_timelines", WindowKind.MANAGE_TIMELINES, "Manage"),
            ("window.open.about", WindowKind.ABOUT, "About"),
        ]

        for command, kind, text in window_commands:
            commands.register(
                command, functools.partial(self.on_window_open, kind), text
            )

        commands.register(
            "media.load.local",
            self.on_media_load_local,
            text="&Local...",
            shortcut="Ctrl+Shift+L",
        )

        commands.register(
            "media.load.youtube",
            self.on_media_load_youtube,
            text="&YouTube...",
        )

        commands.register(
            "timeline.element.inspect",
            self.on_timeline_element_inspect,
            text="Inspect",
        )

        commands.register("open_website_help", self.on_open_website_help, "&Help...")

    def _setup_main_window(self, mw: TiliaMainWindow):
        self.main_window = mw
        if os.environ.get("ENVIRONMENT") != "test":
            self.main_window.setup_qapplication(self.q_application)

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

    def exit(self, code: int, cause: str | None = None):
        # Code = 0 means a successful run, code = 1 means an unhandled exception.
        self.q_application.exit(code)

    def get_window_geometry(self):
        return self.main_window.saveGeometry()

    def get_window_state(self):
        return self.main_window.saveState()

    def on_file_loaded(self, file: TiliaFile) -> None:
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
        for window in self._windows.values():
            if window is not None:
                window.close()
        self.main_window.setFocus()

    @staticmethod
    def on_open_website_help():
        QDesktopServices.openUrl(QUrl(f"{tilia.constants.WEBSITE_URL}/help"))

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
