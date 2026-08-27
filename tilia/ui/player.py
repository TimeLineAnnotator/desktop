from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QRegularExpression, Qt
from PySide6.QtGui import QAction, QIcon, QRegularExpressionValidator

if TYPE_CHECKING:
    from tilia.file.tilia_file import TiliaFile
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QSlider,
    QToolBar,
)

import tilia.errors
from tilia.requests import Get, Post, get, listen, post, stop_listening_to_all
from tilia.settings import settings
from tilia.ui import commands
from tilia.ui.format import format_media_time, parse_media_time


class PlayerToolbar(QToolBar):
    def __init__(self):
        super().__init__()

        self.setObjectName("player_toolbar")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self._setup_requests()

        self.current_time_string = format_media_time(0)
        self.duration_string = format_media_time(0)
        self.duration = 0.0
        self.last_playback_rate = 1.0
        self._status = PlayerStatus.NO_MEDIA
        self._pending_time: float | None = None

        self._setup_controls()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == event.Type.PaletteChange:
            self._update_stylesheet()
        return super().changeEvent(event)

    def _setup_requests(self):
        LISTENS = {
            (Post.PLAYER_CURRENT_TIME_CHANGED, self.on_player_current_time_changed),
            (Post.FILE_MEDIA_DURATION_CHANGED, self.on_media_duration_changed),
            (Post.PLAYER_STOPPED, self.on_stop),
            (Post.PLAYER_UPDATE_CONTROLS, self.on_update_controls),
            (Post.PLAYER_UI_UPDATE, self.on_ui_update_silent),
            (Post.APP_FILE_LOADED, self._on_file_loaded),
            (Post.APP_CLEAR, self._on_clear),
        }

        for post_, callback in LISTENS:
            listen(self, post_, callback)

    def _setup_controls(self):
        self.tooltipped_widgets = {}
        self.add_play_toggle()
        self.add_stop_button()
        self.add_loop_toggle()
        self.add_time_label()

        self.addSeparator()

        self.add_volume_toggle()
        self.add_volume_slider()

        self.addSeparator()

        self.add_playback_rate_spinbox()
        self.on_update_controls(PlayerStatus.NO_MEDIA)

    def on_player_current_time_changed(self, audio_time: float, *_) -> None:
        self.current_time_string = format_media_time(audio_time)
        self._update_time_edit()

    def on_stop(self) -> None:
        self.current_time_string = format_media_time(0)
        self._update_time_edit()
        self.on_ui_update_silent(PlayerToolbarElement.TOGGLE_PLAY_PAUSE, False)

    def on_media_duration_changed(self, duration: float, is_confirmation: bool = False):
        self.duration = duration
        self.duration_string = format_media_time(duration)
        self._update_time_edit()
        self.duration_label.setText(self.duration_string)
        if self._status == PlayerStatus.NO_MEDIA:
            self.time_edit.setEnabled(duration > 0)
            self.duration_label.setEnabled(duration > 0)
        if self._pending_time is not None and duration > 0:
            commands.execute("media.seek", min(self._pending_time, duration))
            self._pending_time = None

    def _on_file_loaded(self, file: TiliaFile) -> None:
        self._pending_time = settings.get_file_time(file.file_path)

    def _on_clear(self) -> None:
        self._pending_time = None

    def _update_time_edit(self) -> None:
        if not self.time_edit.hasFocus():
            self.time_edit.setText(self.current_time_string)

    def _on_time_committed(self) -> None:
        seconds = parse_media_time(self.time_edit.text())
        if seconds is not None:
            commands.execute("media.seek", max(0.0, min(seconds, self.duration)))
        self.time_edit.setText(self.current_time_string)
        self.time_edit.clearFocus()

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if obj is self.time_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.time_edit.setText(self.current_time_string)
                self.time_edit.clearFocus()
                return True
        return super().eventFilter(obj, event)

    def _set_player_controls_enabled(self, enabled: bool) -> None:
        for widget in self.tooltipped_widgets:
            widget.setEnabled(enabled)
        self.duration_label.setEnabled(enabled)

    def on_update_controls(self, state):
        self._status = state
        match state:
            case PlayerStatus.NO_MEDIA:
                for widget in self.tooltipped_widgets:
                    widget.setToolTip(
                        "<i>Player disabled.<br>Load file via '</i>File > Load Media File<i>' to start.</i>"
                    )
                self._set_player_controls_enabled(False)
                self.time_edit.setEnabled(self.duration > 0)
            case PlayerStatus.PLAYER_ENABLED:
                for widget, tooltip in self.tooltipped_widgets.items():
                    widget.setToolTip(tooltip)
                self._set_player_controls_enabled(True)
                self.time_edit.setEnabled(True)
                self.reset()
            case PlayerStatus.WAITING_FOR_YOUTUBE:
                for widget in self.tooltipped_widgets:
                    widget.setToolTip(
                        "<i>Player disabled.<br>Click on YouTube video to enable player.</i>"
                    )
                self._set_player_controls_enabled(False)
                self.time_edit.setEnabled(False)
                self._pending_time = None

    def on_ui_update_silent(self, element_to_set, value):
        if self._status != PlayerStatus.PLAYER_ENABLED:
            return
        match element_to_set:
            case PlayerToolbarElement.TOGGLE_PLAY_PAUSE:
                element = self.play_toggle_action
            case PlayerToolbarElement.TOGGLE_LOOP:
                element = self.loop_toggle_action
            case PlayerToolbarElement.TOGGLE_VOLUME:
                element = self.volume_toggle_action
            case PlayerToolbarElement.SLIDER_VOLUME:
                element = self.volume_slider
            case PlayerToolbarElement.SPINBOX_PLAYBACK:
                self.last_playback_rate = value
                self.playback_rate_spinbox_update_silent()
                return
            case _:
                tilia.errors.display(
                    tilia.errors.PLAYER_TOOLBAR_ERROR, "Unknown element selected."
                )

        element.blockSignals(True)
        try:
            if element_to_set in [
                PlayerToolbarElement.TOGGLE_PLAY_PAUSE,
                PlayerToolbarElement.TOGGLE_LOOP,
                PlayerToolbarElement.TOGGLE_VOLUME,
            ]:
                element.setChecked(value)
            else:
                element.setValue(value)
        except Exception:
            tilia.errors.display(
                tilia.errors.PLAYER_TOOLBAR_ERROR,
                f"Unable to set {element_to_set} with value {value} of type {type(value)}.",
            )
        element.blockSignals(False)

    def destroy(self):
        stop_listening_to_all(self)
        super().destroy()

    def add_play_toggle(self):
        self.play_toggle_action = QAction(self)
        self.play_toggle_action.setText("Play / Pause")
        self.play_toggle_action.triggered.connect(
            lambda checked: commands.execute("media.toggle_play", checked)
        )
        self.play_toggle_action.setCheckable(True)
        play_icon = QIcon()
        play_icon.addPixmap(
            QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaybackStart).pixmap(256, 256),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        play_icon.addPixmap(
            QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaybackStart).pixmap(
                256, 256, QIcon.Mode.Disabled
            ),
            QIcon.Mode.Disabled,
        )
        play_icon.addPixmap(
            QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaybackPause).pixmap(256, 256),
            QIcon.Mode.Normal,
            QIcon.State.On,
        )
        self.play_toggle_action.setIcon(play_icon)
        self.play_toggle_action.setShortcut("Space")
        self.tooltipped_widgets[self.play_toggle_action] = "Play / Pause (Space)"
        self.addAction(self.play_toggle_action)

    def add_stop_button(self):
        self.stop_action = commands.get_qaction("media.stop")
        self.tooltipped_widgets[self.stop_action] = "Stop"
        self.addAction(self.stop_action)

    def add_loop_toggle(self):
        def on_loop_changed(checked: bool) -> None:
            post(Post.PLAYER_TOGGLE_LOOP, checked)

        self.loop_toggle_action = QAction(self)
        self.loop_toggle_action.setText("Toggle Loop")
        self.loop_toggle_action.triggered.connect(
            lambda checked: on_loop_changed(checked)
        )
        self.loop_toggle_action.setIcon(
            QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaylistRepeat)
        )
        self.loop_toggle_action.setCheckable(True)
        self.tooltipped_widgets[self.loop_toggle_action] = "Toggle Loop"
        self.addAction(self.loop_toggle_action)

    _TIME_RE = QRegularExpressionValidator(
        QRegularExpression(r"^\d*(?::\d*(?::\d*)?)?(?:\.\d*)?$")
    )

    def add_time_label(self):
        self.time_edit = QLineEdit(self.current_time_string)
        self.time_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.time_edit.setFrame(False)
        self.time_edit.setFixedWidth(65)
        self.time_edit.setValidator(self._TIME_RE)
        self.time_edit.returnPressed.connect(self._on_time_committed)
        self.time_edit.installEventFilter(self)
        self.addWidget(self.time_edit)

        separator = QLabel("/")
        separator.setMargin(1)
        self.addWidget(separator)

        self.duration_label = QLabel(self.duration_string)
        self.duration_label.setMargin(3)
        self.addWidget(self.duration_label)

    def add_volume_toggle(self):
        def on_volume_toggle(checked: bool) -> None:
            self.volume_toggle_action.setIcon(
                QIcon.fromTheme(
                    QIcon.ThemeIcon.AudioVolumeMuted
                    if checked
                    else QIcon.ThemeIcon.AudioVolumeHigh
                )
            )
            commands.execute("media.volume.mute", checked)
            self.volume_slider.setEnabled(not checked)

        self.volume_toggle_action = QAction(self)
        self.volume_toggle_action.setText("Toggle Volume")
        self.volume_toggle_action.triggered.connect(
            lambda checked: on_volume_toggle(checked)
        )
        self.volume_toggle_action.setIcon(
            QIcon.fromTheme(QIcon.ThemeIcon.AudioVolumeHigh)
        )
        self.volume_toggle_action.setCheckable(True)
        self.tooltipped_widgets[self.volume_toggle_action] = "Mute / Unmute"
        self.addAction(self.volume_toggle_action)

    def add_volume_slider(self):
        def on_volume_slide(value: int) -> None:
            commands.execute("media.volume.change", value)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(100)
        self.volume_slider.setMaximumWidth(70)
        self.volume_slider.valueChanged.connect(lambda value: on_volume_slide(value))
        self._update_stylesheet()
        self.tooltipped_widgets[self.volume_slider] = "Volume"
        self.addWidget(self.volume_slider)

    def _update_stylesheet(self):
        self.volume_slider.setStyleSheet(
            "QSlider {margin-right: 4px;}"
            "QSlider::groove::horizontal { height: 4px;}"
            "QSlider::groove::horizontal:enabled { background: palette(text); }"
            "QSlider::handle::horizontal { width: 8px; margin: -4px 0; border-radius: 6px;}"
            "QSlider::handle::horizontal:enabled { background: palette(text); border: 2px solid palette(text); }"
        )

    def add_playback_rate_spinbox(self):
        def on_playback_rate_changed(rate: float) -> None:
            commands.execute("media.playback_rate.try", rate)

            if get(Get.MEDIA_TYPE) == "youtube":
                self.playback_rate_spinbox_update_silent()

            else:
                self.last_playback_rate = rate

        self.playback_rate_spinbox = QDoubleSpinBox()
        self.playback_rate_spinbox.setMinimum(0)
        self.playback_rate_spinbox.setValue(1.0)
        self.playback_rate_spinbox.setSingleStep(0.25)
        self.playback_rate_spinbox.setFixedWidth(
            self.playback_rate_spinbox.height() // 8
        )
        self.playback_rate_spinbox.setSuffix(" x")
        self.playback_rate_spinbox.setKeyboardTracking(False)
        self.playback_rate_spinbox.valueChanged.connect(on_playback_rate_changed)
        self.tooltipped_widgets[self.playback_rate_spinbox] = "Playback Rate"
        self.addWidget(self.playback_rate_spinbox)

    def playback_rate_spinbox_update_silent(self) -> None:
        self.playback_rate_spinbox.blockSignals(True)
        self.playback_rate_spinbox.clearFocus()
        self.playback_rate_spinbox.setValue(self.last_playback_rate)
        self.playback_rate_spinbox.blockSignals(False)

    def reset(self):
        self.blockSignals(True)
        self.play_toggle_action.setChecked(False)
        self.volume_toggle_action.setChecked(False)
        self.volume_slider.setValue(100)
        self.loop_toggle_action.setChecked(False)
        self.last_playback_rate = 1
        self.playback_rate_spinbox.setValue(1)
        self.blockSignals(False)


class PlayerToolbarElement(Enum):
    TOGGLE_PLAY_PAUSE = auto()
    TOGGLE_LOOP = auto()
    TOGGLE_VOLUME = auto()
    SLIDER_VOLUME = auto()
    SPINBOX_PLAYBACK = auto()


class PlayerStatus(Enum):
    NO_MEDIA = auto()
    PLAYER_ENABLED = auto()
    WAITING_FOR_YOUTUBE = auto()
