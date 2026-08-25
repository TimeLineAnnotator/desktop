from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudio, QAudioDevice, QAudioOutput, QMediaPlayer

from .base import Player
from .qtplayer import wait_for_signal


class Completion:
    """One-shot handoff between the GUI thread and AudioEngineWorker: the GUI
    thread blocks on `event` (a plain thread wait, not a Qt event loop, so it
    can't reenter the GUI thread's event dispatcher) while the worker thread
    fills in `result` and sets the event as its last step."""

    __slots__ = ("event", "result")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None


class AudioEngineWorker(QObject):
    """Owns the real QMediaPlayer/QAudioOutput; lives on a dedicated QThread
    (see QtAudioPlayer). All access to `self.player`/`self.audio_output` must
    happen through this worker's slots, invoked via queued signals from the
    GUI thread -- never called directly, since they have this thread's
    affinity, not the GUI thread's."""

    position_changed = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.player: QMediaPlayer | None = None
        self.audio_output: QAudioOutput | None = None

    @Slot()
    def setup(self) -> None:
        self.audio_output = QAudioOutput()
        self.audio_output.setDevice(QAudioDevice())
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)

        # Pushes position updates to the GUI thread instead of waiting for
        # it to poll-and-block on every UPDATE_INTERVAL tick -- see
        # PositionRelay's docstring in qtplayer.py.
        self._position_timer = QTimer()
        self._position_timer.setInterval(Player.UPDATE_INTERVAL)
        self._position_timer.timeout.connect(self._emit_position)
        self._position_timer.start()

    def _emit_position(self) -> None:
        if self.player is not None:
            self.position_changed.emit(self.player.position() / 1000)

    def _do_stop(self) -> bool:
        @wait_for_signal(
            self.player.playbackStateChanged, QMediaPlayer.PlaybackState.StoppedState
        )
        def stop():
            self.player.stop()
            return True

        return stop()

    @Slot(str, object)
    def load(self, media_path: str, completion: Completion) -> None:
        @wait_for_signal(
            self.player.mediaStatusChanged, QMediaPlayer.MediaStatus.LoadedMedia
        )
        def load_media(path):
            self._do_stop()  # Must be _do_stop() instead of player.stop() to avoid freeze.
            self.player.setSource(QUrl.fromLocalFile(path))
            return True

        success = load_media(media_path)
        duration_ms = self.player.duration() if success else 0
        completion.result = (success, duration_ms)
        completion.event.set()

    @Slot(object)
    def stop(self, completion: Completion) -> None:
        completion.result = self._do_stop()
        completion.event.set()

    @Slot(object)
    def unload(self, completion: Completion) -> None:
        self._do_stop()  # Must be _do_stop() instead of player.stop() to avoid freeze.
        self.player.setSource(QUrl())
        completion.result = None
        completion.event.set()

    @Slot(object)
    def get_duration(self, completion: Completion) -> None:
        completion.result = self.player.duration() / 1000
        completion.event.set()

    @Slot(object)
    def exit(self, completion: Completion) -> None:
        self._position_timer.stop()
        if self.player is not None:
            self.player.stop()
            self.player.setSource(QUrl())
            self.player = None
        completion.result = None
        completion.event.set()

    @Slot(float)
    def seek(self, time_seconds: float) -> None:
        self.player.setPosition(int(time_seconds * 1000))

    @Slot()
    def play(self) -> None:
        self.player.play()

    @Slot()
    def pause(self) -> None:
        self.player.pause()

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        log_volume = QAudio.convertVolume(
            volume / 100.0,
            QAudio.VolumeScale.LinearVolumeScale,
            QAudio.VolumeScale.LogarithmicVolumeScale,
        )
        self.audio_output.setVolume(log_volume)

    @Slot(bool)
    def set_mute(self, is_muted: bool) -> None:
        self.audio_output.setMuted(is_muted)

    @Slot(float)
    def set_playback_rate(self, playback_rate: float) -> None:
        self.player.setPlaybackRate(playback_rate)

    @Slot(bool)
    def set_loop(self, is_looping: bool) -> None:
        self.player.setLoops(
            QMediaPlayer.Loops.Infinite if is_looping else QMediaPlayer.Loops.Once
        )

    @Slot()
    def set_default_device(self) -> None:
        self.audio_output.setDevice(QAudioDevice())


class AudioEngineRequests(QObject):
    """Signals the GUI-thread QtAudioPlayer emits to reach the worker-thread
    AudioEngineWorker. Split into its own QObject (rather than defined on
    AudioEngineWorker) so the GUI thread never needs a reference to an object
    that lives on another thread -- only to these signals, which are safe to
    emit from any thread."""

    load_requested = Signal(str, object)
    stop_requested = Signal(object)
    unload_requested = Signal(object)
    get_duration_requested = Signal(object)
    exit_requested = Signal(object)
    seek_requested = Signal(float)
    play_requested = Signal()
    pause_requested = Signal()
    set_volume_requested = Signal(int)
    set_mute_requested = Signal(bool)
    set_playback_rate_requested = Signal(float)
    set_loop_requested = Signal(bool)
    set_default_device_requested = Signal()
