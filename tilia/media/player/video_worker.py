from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDevice,
    QAudioOutput,
    QMediaPlayer,
    QVideoFrame,
    QVideoSink,
)
from PySide6.QtMultimediaWidgets import QVideoWidget

from .base import Player
from .qtplayer import wait_for_signal

#: Rate VideoEngineWorker pushes the latest decoded frame to the GUI thread
#: at, decoupled from the decoder's own (often higher) output rate.
FRAME_RELAY_INTERVAL_MS = 33


class FrameRelay(QObject):
    """Lives on the GUI thread. Receives frames from VideoEngineWorker's
    QVideoSink (worker thread) via a queued connection -- same pattern as
    _ResultRelay in background_task.py -- and pushes them into the widget's
    own sink with a same-thread call."""

    def __init__(self, widget: QVideoWidget) -> None:
        super().__init__()
        self._widget = widget

    @Slot(QVideoFrame)
    def on_frame(self, frame: QVideoFrame) -> None:
        self._widget.videoSink().setVideoFrame(frame)


class Completion:
    """One-shot handoff between the GUI thread and VideoEngineWorker: the GUI
    thread blocks on `event` (a plain thread wait, not a Qt event loop, so it
    can't reenter the GUI thread's event dispatcher) while the worker thread
    fills in `result` and sets the event as its last step."""

    __slots__ = ("event", "result")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None


class VideoEngineWorker(QObject):
    """Owns the real QMediaPlayer/QAudioOutput/QVideoSink; lives on a
    dedicated QThread (see QtVideoPlayer). Emits `frame_ready` for the
    GUI-thread FrameRelay to pick up via a queued connection (wired in
    QtVideoPlayer.__init__) -- pairing the worker-thread player directly
    with the GUI-thread QVideoWidget via setVideoOutput() silently drops
    all frame delivery cross-thread (see FrameRelay's docstring).

    All access to `self.player`/`self.audio_output` must happen through this
    worker's slots, invoked via queued signals from the GUI thread -- never
    called directly, since they have this thread's affinity, not the GUI
    thread's."""

    position_changed = Signal(float)
    frame_ready = Signal(QVideoFrame)

    def __init__(self) -> None:
        super().__init__()
        self.player: QMediaPlayer | None = None
        self.audio_output: QAudioOutput | None = None
        self.sink: QVideoSink | None = None
        self._latest_frame: QVideoFrame | None = None

    @Slot()
    def setup(self) -> None:
        self.audio_output = QAudioOutput()
        self.audio_output.setDevice(QAudioDevice())
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.sink = QVideoSink()
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._on_raw_frame)

        # Pushes position instead of the GUI thread polling-and-blocking for
        # it -- see PositionRelay's docstring in qtplayer.py.
        self._position_timer = QTimer()
        self._position_timer.setInterval(Player.UPDATE_INTERVAL)
        self._position_timer.timeout.connect(self._emit_position)
        self._position_timer.start()

        # Relaying every decoded frame directly would queue one delivery per
        # frame; if the GUI thread falls behind, it has to drain them in
        # order, so the picture lags audio more and more the longer that
        # persists. Caching just the latest frame and pushing on our own
        # timer bounds the backlog to one frame and self-heals instead.
        self._frame_relay_timer = QTimer()
        self._frame_relay_timer.setInterval(FRAME_RELAY_INTERVAL_MS)
        self._frame_relay_timer.timeout.connect(self._relay_latest_frame)
        self._frame_relay_timer.start()

    def _emit_position(self) -> None:
        if self.player is not None:
            self.position_changed.emit(self.player.position() / 1000)

    def _on_raw_frame(self, frame: QVideoFrame) -> None:
        self._latest_frame = frame

    def _relay_latest_frame(self) -> None:
        if self._latest_frame is not None:
            frame, self._latest_frame = self._latest_frame, None
            self.frame_ready.emit(frame)

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
        self._frame_relay_timer.stop()
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


class VideoEngineRequests(QObject):
    """Signals the GUI-thread QtVideoPlayer emits to reach the worker-thread
    VideoEngineWorker. Split into its own QObject (rather than defined on
    VideoEngineWorker) so the GUI thread never needs a reference to an object
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
