from __future__ import annotations

import time

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudio

from .base import Player

from tilia.requests import Post, post
from tilia.ui.player import PlayerStatus


class QtPlayer(Player):
    MEDIA_TYPE = ""

    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.player.durationChanged.connect(self.on_media_duration_available)
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

    def on_media_load_done(self, path):
        super().on_media_load_done(path)
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)

    def on_media_duration_available(self, duration):
        super().on_media_duration_available(duration / 1000)

    def _engine_load_media(self, media_path: str) -> bool:
        self.player.stop()
        time.sleep(0.1)
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
        time.sleep(
            0.1
        )  # Avoids freeze if about to change to YT player. Reason unknown.

    def _engine_unload_media(self):
        self.player.setSource(QUrl(None))

    def _engine_get_media_duration(self) -> float:
        return self.player.duration() / 1000

    def _engine_exit(self):
        self.player = None
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.NO_MEDIA)

    def _engine_set_volume(self, volume: int) -> None:
        log_volume = QAudio.convertVolume(
            volume / 100.0,
            QAudio.VolumeScale.LinearVolumeScale,
            QAudio.VolumeScale.LogarithmicVolumeScale,
        )
        self.audio_output.setVolume(log_volume)

    def _engine_set_mute(self, is_muted: bool) -> None:
        self.audio_output.setMuted(is_muted)

    def _engine_try_playback_rate(self, playback_rate: float) -> None:
        self.player.setPlaybackRate(playback_rate)

    def _engine_set_playback_rate(self, playback_rate: float) -> None:
        pass

    def _engine_loop(self, is_looping: bool) -> None:
        self.player.setLoops(
            QMediaPlayer.Loops.Infinite if is_looping else QMediaPlayer.Loops.Once
        )
