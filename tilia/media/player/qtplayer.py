from __future__ import annotations

from PySide6.QtCore import QUrl, QEventLoop, SignalInstance, QTimer
from PySide6.QtMultimedia import (
    QMediaPlayer,
    QAudioOutput,
    QAudio,
    QAudioDevice,
    QMediaDevices,
)

from .base import Player

from tilia.requests import Post, post
from tilia.ui.player import PlayerStatus


def wait_for_signal(signal: SignalInstance, value):
    """
    Many Qt functions run on threads, and this wrapper makes sure that after starting a process, the right signal is emitted before continuing the TiLiA process.
    See _engine_stop of QtPlayer for an example implementation.

    :param signal: The signal to watch.
    :type signal: SignalInstance
    :param value: The "right" output value that signal should emit before continuing. (eg. on stopping player, playbackStateChanged emits StoppedState when player has been successfully stopped. Only then can we continue the rest of the update process.)
    """

    def signal_wrapper(func):
        timer = QTimer(singleShot=True, interval=200)
        loop = QEventLoop()
        success = False

        def value_checker(signal_value):
            if signal_value == value:
                nonlocal success
                success = True
                loop.quit()

        def check_signal(*args, **kwargs):
            nonlocal success
            if not func(*args, **kwargs):
                return False
            signal.connect(value_checker)
            timer.timeout.connect(loop.quit)
            timer.start()
            loop.exec()
            return timer.isActive() and success

        return check_signal

    return signal_wrapper


class QtPlayer(Player):
    MEDIA_TYPE = ""

    def __init__(self):
        super().__init__()
        self.audio_output = QAudioOutput()
        self.audio_output.setDevice(QAudioDevice())
        self.media_devices = QMediaDevices()
        self.media_devices.audioOutputsChanged.connect(self.on_audio_outputs_changed)
        self._init_player()

    def _init_player(self):
        self.player = QMediaPlayer()
        self.player.durationChanged.connect(self.on_media_duration_available)
        self.player.setAudioOutput(self.audio_output)

    def on_media_load_done(self, path, start, end):
        super().on_media_load_done(path, start, end)
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)

    def on_media_duration_available(self, duration):
        super().on_media_duration_available(duration / 1000)

    def on_audio_outputs_changed(self) -> None:
        """
        Connected to QMediaDevices.audioOutputsChanged.
        Sets the audio output to the default output device.
        """
        self.audio_output.setDevice(QAudioDevice())

    def _engine_load_media(self, media_path: str) -> bool:
        @wait_for_signal(
            self.player.mediaStatusChanged, QMediaPlayer.MediaStatus.LoadedMedia
        )
        def load_media(media_path):
            self._engine_stop()  # Must be _engine_stop() instead of player.stop() to avoid freeze.
            self.player.setSource(QUrl.fromLocalFile(media_path))
            return True

        return load_media(media_path)

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
        @wait_for_signal(
            self.player.playbackStateChanged, QMediaPlayer.PlaybackState.StoppedState
        )
        def stop():
            self.player.stop()
            return True

        return stop()

    def _engine_unload_media(self):
        self._engine_stop()  # Must be _engine_stop() instead of player.stop() to avoid freeze.
        self.player.setSource(QUrl())

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
