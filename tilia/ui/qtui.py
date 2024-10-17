from __future__ import annotations

import re
import sys
from functools import partial
from pathlib import Path

from typing import Optional, Callable

from PyQt6 import QtGui
from PyQt6.QtCore import QKeyCombination, Qt, qInstallMessageHandler, QUrl, QtMsgType
from PyQt6.QtGui import QIcon, QFontDatabase, QDesktopServices
from PyQt6.QtWidgets import QMainWindow, QApplication, QToolBar

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
from . import dialogs, actions
from .actions import TiliaAction
from .dialog_manager import DialogManager
from .dialogs.basic import display_error
from .dialogs.by_time_or_by_measure import ByTimeOrByMeasure
from .dialogs.crash import CrashDialog
from .menubar import TiliaMenuBar
from tilia.ui.timelines.collection.collection import TimelineUIs
from .menus import TimelinesMenu, HierarchyMenu, MarkerMenu, BeatMenu, HarmonyMenu, PdfMenu
from .options_toolbar import OptionsToolbar
from .player import PlayerToolbar
from .windows.manage_timelines import ManageTimelines
from .windows.metadata import MediaMetadataWindow
from .windows.about import About
from .windows.inspect import Inspect
from .windows.settings import SettingsWindow
from .windows.kinds import WindowKind
from ..media.player import QtVideoPlayer, QtAudioPlayer, YouTubePlayer
from ..parsers.csv.beat import beats_from_csv
from tilia import constants
from tilia.settings import settings
from tilia.utils import get_tilia_class_string
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.requests import Post, listen, post, serve, Get, get


class TiliaMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tilia.constants.APP_NAME)
        self.setWindowIcon(QIcon(str(tilia.constants.APP_ICON_PATH)))
        self.setStatusTip("Main window")
        qInstallMessageHandler(self.handle_qt_log_message)

    @staticmethod
    def handle_qt_log_message(type, _, msg):
        if type == QtMsgType.QtCriticalMsg or type == QtMsgType.QtFatalMsg:
            raise Exception(f'{type.name}: {msg}')
        else:
            print(f"{type.name}: {msg}")

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
            (Post.WINDOW_ABOUT_CLOSED, lambda: self.on_window_close_done(WindowKind.ABOUT)),
            (Post.WINDOW_ABOUT_OPEN, lambda: self.on_window_open(WindowKind.ABOUT)),
            (Post.WINDOW_INSPECT_CLOSE, lambda: self.on_window_close(WindowKind.INSPECT)),
            (Post.WINDOW_INSPECT_CLOSED, lambda: self.on_window_close_done(WindowKind.INSPECT)),
            (Post.WINDOW_INSPECT_OPEN, lambda: self.on_window_open(WindowKind.INSPECT)),
            (Post.WINDOW_MANAGE_TIMELINES_CLOSE_DONE, lambda: self.on_window_close_done(WindowKind.MANAGE_TIMELINES)),
            (Post.WINDOW_MANAGE_TIMELINES_OPEN, lambda: self.on_window_open(WindowKind.MANAGE_TIMELINES)),
            (Post.WINDOW_METADATA_CLOSED, lambda: self.on_window_close_done(WindowKind.MEDIA_METADATA)),
            (Post.WINDOW_METADATA_OPEN, lambda: self.on_window_open(WindowKind.MEDIA_METADATA)),
            (Post.WINDOW_SETTINGS_CLOSED, lambda: self.on_window_close_done(WindowKind.SETTINGS)),
            (Post.WINDOW_SETTINGS_OPEN, lambda: self.on_window_open(WindowKind.SETTINGS)),
            (Post.REQUEST_CLEAR_UI, self.on_clear_ui),
            (Post.TIMELINE_KIND_INSTANCED, self.on_timeline_kind_change),
            (Post.TIMELINE_KIND_NOT_INSTANCED, self.on_timeline_kind_change),
            (Post.MARKER_IMPORT_FROM_CSV, partial(self.on_import_from_csv, TlKind.MARKER_TIMELINE)),
            (Post.HIERARCHY_IMPORT_FROM_CSV, partial(self.on_import_from_csv, TlKind.HIERARCHY_TIMELINE)),
            (Post.BEAT_IMPORT_FROM_CSV, partial(self.on_import_from_csv, TlKind.BEAT_TIMELINE)),
            (Post.HARMONY_IMPORT_FROM_CSV, partial(self.on_import_from_csv, TlKind.HARMONY_TIMELINE)),
            (Post.PDF_IMPORT_FROM_CSV, partial(self.on_import_from_csv, TlKind.PDF_TIMELINE)),
            (Post.DISPLAY_ERROR, display_error),
            (Post.UI_EXIT, self.exit),
        }

        SERVES = {
            (Get.TIMELINE_WIDTH, lambda: self.timeline_width),
            (Get.PLAYBACK_AREA_WIDTH, lambda: self.playback_area_width),
            (Get.LEFT_MARGIN_X, lambda: self.playback_area_margin),
            (Get.RIGHT_MARGIN_X, lambda: self.playback_area_width + self.playback_area_margin),
            (Get.WINDOW_GEOMETRY, self.get_window_geometry),
            (Get.WINDOW_STATE, self.get_window_state),
            (Get.PLAYER_CLASS, self.get_player_class),
        }

        for post, callback in LISTENS:
            listen(self, post, callback)

        for request, callback in SERVES:
            serve(self, request, callback)

    def _setup_main_window(self, mw: TiliaMainWindow):
        def get_initial_geometry():
            x = settings.get("general", "window_x")
            y = settings.get("general", "window_y")
            w = settings.get("general", "window_width")
            h = settings.get("general", "window_height")

            return x, y, w, h

        self.main_window = mw
        # self.main_window.setGeometry(*get_initial_geometry())

    @staticmethod
    def _setup_fonts():
        fonts_dir = Path(__file__).parent / 'fonts'
        fonts = ['MusAnalysis.otf']
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
        }
        self.kind_to_dynamic_menus = {
            kind: self.menu_bar.get_menu(TimelinesMenu).get_submenu(menu_class)
            for kind, menu_class in menu_info
        }
        self.update_dynamic_menus()

    def _setup_windows(self):
        self._windows = {
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

    # noinspection PyTypeChecker,PyUnresolvedReferences
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
            window.activateWindow()

    def open_inspect_window(self):
        widget = Inspect()
        self.main_window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, widget)
        widget.setFloating(True)
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
        url, success = get(
            Get.FROM_USER_STRING, "Load from Youtube", "Enter YouTube URL"
        )
        match = re.match(tilia.constants.YOUTUBE_URL_REGEX, url)
        if not success:
            return
        if not match:
            tilia.errors.display(tilia.errors.YOUTUBE_URL_INVALID, url)
            return

        post(Post.APP_MEDIA_LOAD, url)

    def on_clear_ui(self):
        """Closes all UI windows."""
        for kind, window in self._windows.items():
            if window is not None:
                window.destroy()
                self._windows[kind] = None

    def _get_by_time_or_by_measure_from_user(self):
        dialog = ByTimeOrByMeasure(self.main_window)
        if not dialog.exec():
            return
        return dialog.get_option()

    def on_website_help_open(self):
        QDesktopServices.openUrl(QUrl(f'{constants.WEBSITE_URL}/help/introduction'))

    def on_import_from_csv(self, tlkind: TlKind) -> None:
        if not self._validate_timeline_kind_on_import_from_csv(tlkind):
            return

        timeline_ui = self.timeline_uis.ask_choose_timeline(
            "Import components from CSV",
            "Choose timeline where components will be created",
            tlkind,
        )
        if not timeline_ui:
            return

        timeline = get(Get.TIMELINE, timeline_ui.id)
        if (
            timeline.components
            and not self._confirm_timeline_overwrite_on_import_from_csv()
        ):
            return

        if tlkind == TlKind.BEAT_TIMELINE:
            time_or_measure = "time"
        else:
            time_or_measure = self._get_by_time_or_by_measure_from_user()

        if time_or_measure == "measure":
            beat_tlui = self._get_beat_timeline_ui_for_import_from_csv()
            if not beat_tlui:
                return

            beat_tl = get(Get.TIMELINE, beat_tlui.id)
        else:
            beat_tl = None

        success, path = get(
            Get.FROM_USER_FILE_PATH, "Import components", ["CSV files (*.csv)"]
        )

        if not success:
            return

        tlkind_to_funcs: dict[TlKind, dict[str, Callable]] = {
            TlKind.MARKER_TIMELINE: {
                "time": tilia.parsers.csv.marker.import_by_time,
                "measure": tilia.parsers.csv.marker.import_by_measure,
            },
            TlKind.HIERARCHY_TIMELINE: {
                "time": tilia.parsers.csv.hierarchy.import_by_time,
                "measure": tilia.parsers.csv.hierarchy.import_by_measure,
            },
            TlKind.BEAT_TIMELINE: {"time": beats_from_csv},
            TlKind.HARMONY_TIMELINE: {
                "time": tilia.parsers.csv.harmony.import_by_time,
                "measure": tilia.parsers.csv.harmony.import_by_measure,
            },
            TlKind.PDF_TIMELINE: {
                'time': tilia.parsers.csv.pdf.import_by_time,
                'measure': tilia.parsers.csv.pdf.import_by_measure
            }
        }

        timeline.clear()

        if time_or_measure == "time":
            errors = tlkind_to_funcs[tlkind]["time"](timeline, path)
        elif time_or_measure == "measure":
            errors = tlkind_to_funcs[tlkind]["measure"](timeline, beat_tl, path)
        else:
            raise ValueError("Invalid time_or_measure value '{time_or_measure}'")

        if errors:
            self._display_import_from_csv_errors(errors)

        post(Post.APP_RECORD_STATE, "Import from csv file")

    def _validate_timeline_kind_on_import_from_csv(self, tlkind: TlKind):
        if not self.timeline_uis.get_timeline_uis_by_attr("TIMELINE_KIND", tlkind):
            tilia.errors.display(
                tilia.errors.CSV_IMPORT_FAILED, 
                f"No timelines of type '{tlkind}' found."
            )
            return False
        return True

    @staticmethod
    def _confirm_timeline_overwrite_on_import_from_csv():
        return get(
            Get.FROM_USER_YES_OR_NO,
            "Import from CSV",
            "Selected timeline is not empty. Existing components will be deleted when importing. Are you sure you want to continue?",
        )

    def _get_beat_timeline_ui_for_import_from_csv(self):
        if not self.timeline_uis.get_timeline_uis_by_attr(
            "TIMELINE_KIND", TlKind.BEAT_TIMELINE
        ):
            tilia.errors.display(
                tilia.errors.CSV_IMPORT_FAILED,
                "No beat timelines found. Must have a beat timeline if importing by measure."
            )
            return

        return self.timeline_uis.ask_choose_timeline(
            "Import components from CSV",
            "Choose timeline with measures to be used when importing",
            TlKind.BEAT_TIMELINE,
        )

    @staticmethod
    def _display_import_from_csv_errors(errors):
        errors_str = "\n".join(errors)
        tilia.errors.display(
            tilia.errors.CSV_IMPORT_FAILED, 
            f"Some components were not imported. The following errors occured:\n{errors_str}"
        )

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
