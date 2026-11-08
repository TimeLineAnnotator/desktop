from __future__ import annotations

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QEventLoop,
    QIODevice,
    QTimer,
    QUrl,
    SignalInstance,
)
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDevice,
    QAudioOutput,
    QMediaDevices,
    QMediaPlayer,
)

import tilia.errors
from tilia.media import synth
from tilia.requests import Get, Post, get, long_operation, post
from tilia.ui.player import PlayerStatus

from .base import Player


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
        # The player reads the score's sound from here while it's loaded.
        self._score_sound_buffer: QBuffer | None = None
        # What that sound was rendered from.
        self._score_sound_source: tuple[list[synth.SynthNote], float] | None = None
        self._init_player()

    def _init_player(self):
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)

    def on_media_load_done(self, path, start, end):
        super().on_media_load_done(path, start, end)
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)

    def _prepare_score_sound(self) -> bool:
        """The sound is rendered when it's first played, and again only if the
        notes changed: a file with a recording never pays for it."""
        if self.media_path or not self._is_score_sound_available:
            return True
        source = (synth.get_score_notes(), get(Get.MEDIA_DURATION))
        if source == self._score_sound_source:
            return True
        if not source[1]:
            return False
        if not self._load_score_sound(*source):
            tilia.errors.display(tilia.errors.MEDIA_LOAD_FAILED, "the score's sound")
            return False
        self._score_sound_source = source
        return True

    @long_operation("Rendering score...")
    def _load_score_sound(self, notes: list[synth.SynthNote], duration: float) -> bool:
        buffer = QBuffer()
        buffer.setData(QByteArray(synth.to_wav(synth.render(notes, duration))))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)

        @wait_for_signal(
            self.player.mediaStatusChanged, QMediaPlayer.MediaStatus.LoadedMedia
        )
        def load() -> bool:
            if not self.player.source().isEmpty():
                self._engine_stop()
            # The name tells the backend what the data is.
            self.player.setSourceDevice(buffer, QUrl("score.wav"))
            self._score_sound_buffer = buffer
            return True

        if not load():
            return False
        self.is_media_loaded = True
        # As the player measures it, or playback would never reach its end. It
        # isn't announced: this isn't media the timelines should be scaled to.
        self.duration = self.playback_end = self._engine_get_media_duration()
        self._engine_seek(self.current_time)
        return True

    def _forget_score_sound(self) -> None:
        self._score_sound_buffer = None
        self._score_sound_source = None

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

        success = load_media(media_path)
        self._forget_score_sound()
        if success:
            # Divides by 1000 as durations is expected to be in miliseconds
            self.on_media_duration_available(self.player.duration() / 1000)
        return success

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
        if self.player.source().isEmpty():
            # Nothing loaded, so nothing to stop: _engine_stop() would wait out
            # its whole timeout for a StoppedState signal that never comes.
            return
        self._engine_stop()  # Must be _engine_stop() instead of player.stop() to avoid freeze.
        self.player.setSource(QUrl())
        self._forget_score_sound()

    def _engine_get_media_duration(self) -> float:
        return self.player.duration() / 1000

    def _engine_exit(self):
        if self.player is not None:
            self.player.stop()
            self.player.setSource(QUrl())
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
