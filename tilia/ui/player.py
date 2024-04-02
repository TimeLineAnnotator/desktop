from PyQt6.QtWidgets import (
    QToolBar,
    QLabel,
)

from tilia.media.player.base import MediaTimeChangeReason
from tilia.ui import actions
from tilia.ui.actions import TiliaAction
from tilia.ui.format import format_media_time
from tilia.requests import Post, listen, stop_listening_to_all


class PlayerToolbar(QToolBar):
    def __init__(self):
        super().__init__()

        listen(
            self, Post.PLAYER_CURRENT_TIME_CHANGED, self.on_player_current_time_changed
        )
        listen(self, Post.FILE_MEDIA_DURATION_CHANGED, self.on_media_duration_changed)
        listen(self, Post.PLAYER_MEDIA_UNLOADED, self.on_media_unload)
        listen(self, Post.PLAYER_STOPPED, self.on_stop)
        listen(self, Post.PLAYER_DISABLE_CONTROLS, self.on_disable_controls)
        listen(self, Post.PLAYER_ENABLE_CONTROLS, self.on_enable_controls)

        self.current_time_string = "0:00:00"
        self.duration_string = "0:00:00"

        self.play_action = actions.get_qaction(TiliaAction.MEDIA_TOGGLE_PLAY_PAUSE)
        self.stop_action = actions.get_qaction(TiliaAction.MEDIA_STOP)
        self.addAction(self.play_action)
        self.addAction(self.stop_action)
        self.time_label = QLabel(f"{self.current_time_string}/{self.duration_string}")
        self.addWidget(self.time_label)

    def on_player_current_time_changed(
        self, audio_time: float, _: MediaTimeChangeReason
    ) -> None:
        self.current_time_string = format_media_time(audio_time)
        self.update_time_string()

    def on_stop(self) -> None:
        self.current_time_string = format_media_time(0)
        self.update_time_string()

    def on_media_duration_changed(self, duration: float):
        self.duration_string = format_media_time(duration)
        self.update_time_string()

    def on_media_unload(self) -> None:
        self.duration_string = format_media_time(0)
        self.current_time_string = format_media_time(0)
        self.update_time_string()

    def update_time_string(self):
        self.time_label.setText(f"{self.current_time_string}/{self.duration_string}")

    def on_disable_controls(self):
        self.play_action.setEnabled(False)
        self.stop_action.setEnabled(False)

    def on_enable_controls(self):
        self.play_action.setEnabled(True)
        self.stop_action.setEnabled(True)

    def destroy(self):
        stop_listening_to_all(self)
        super().destroy()
