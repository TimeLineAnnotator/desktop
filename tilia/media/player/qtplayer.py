from __future__ import annotations

import logging

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from .base import Player

logger = logging.getLogger(__name__)


class QtPlayer(Player):
    MEDIA_TYPE = ""

    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.player.durationChanged.connect(self.on_media_duration_available)
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

    def on_media_duration_available(self, duration):
        super().on_media_duration_available(duration / 1000)

    def _engine_load_media(self, media_path: str) -> bool:
        self.player.setSource(QUrl(media_path))
        return True

    def _engine_get_current_time(self):
        return self.player.position() / 1000

    def _engine_seek(self, time: float) -> None:
        self.player.setPosition(int(time * 1000))

    def _engine_play(self) -> None:
        self.player.play()

    def _engine_pause(self) -> None:
        self.player.pause()

    def _engine_unpause(self) -> None:
        self.player.play()

    def _engine_stop(self):
        self.player.stop()

    def _engine_unload_media(self):
        self.player.setSource(QUrl())

    def _engine_get_media_duration(self) -> float:
        return self.player.duration() / 1000

    def _engine_exit(self):
        self.player.deleteLater()
