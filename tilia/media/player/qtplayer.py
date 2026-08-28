from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Callable, ParamSpec

from PySide6.QtCore import (
    QEventLoop,
    QObject,
    QThread,
    QTimer,
    QUrl,
    Signal,
    SignalInstance,
    Slot,
)
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDevice,
    QAudioOutput,
    QMediaDevices,
    QMediaPlayer,
)

from tilia.requests import Post, post
from tilia.ui.player import PlayerStatus

from .base import Player

P = ParamSpec("P")


class Completion:
    """One-shot handoff between the GUI thread and a worker: the GUI thread
    blocks on `event` (a plain thread wait, not a Qt event loop, so it can't
    reenter the GUI thread's event dispatcher) while the worker thread fills
    in `result` and sets the event as its last step."""

    __slots__ = ("event", "result")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None


class EngineRequests(QObject):
    """Signals the GUI-thread QtAudioPlayer/QtVideoPlayer emit to reach the
    worker-thread EngineWorker. Split into its own QObject (rather than
    defined on EngineWorker) so the GUI thread never needs a reference to an
    object that lives on another thread -- only to these signals, which are
    safe to emit from any thread."""

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


class EngineWorker(QObject):
    """Owns the real QMediaPlayer/QAudioOutput; lives on a dedicated QThread
    (see WorkerThreadPlayer). All access to `self.player`/`self.audio_output`
    must happen through this worker's slots, invoked via queued signals from
    the GUI thread -- never called directly, since they have this thread's
    affinity, not the GUI thread's. Subclasses (VideoEngineWorker) override
    the `_extra_worker_*` hooks for anything beyond shared audio playback."""

    position_changed = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.player: QMediaPlayer | None = None
        self.audio_output: QAudioOutput | None = None

    def _extra_worker_setup(self) -> None:
        """Hook for worker-thread setup beyond the shared player/audio
        output (e.g. VideoEngineWorker's QVideoSink/frame-relay timer)."""

    def _extra_worker_exit_cleanup(self) -> None:
        """Hook for cleanup before the player is torn down on exit (e.g.
        VideoEngineWorker stopping its frame-relay timer)."""

    @Slot()
    def setup(self) -> None:
        self.audio_output = QAudioOutput()
        self.audio_output.setDevice(QAudioDevice())
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)

        # Pushes position updates to the GUI thread instead of waiting for
        # it to poll-and-block on every UPDATE_INTERVAL tick -- see
        # PositionRelay's docstring below.
        self._position_timer = QTimer()
        self._position_timer.setInterval(Player.UPDATE_INTERVAL)
        self._position_timer.timeout.connect(self._emit_position)
        self._position_timer.start()

        self._extra_worker_setup()

    def _emit_position(self) -> None:
        if self.player is not None:
            self.position_changed.emit(self.player.position() / 1000)

    @contextmanager
    def _position_timer_paused(self) -> Generator[None, None, None]:
        self._position_timer.stop()
        try:
            yield
        finally:
            if self.player is not None:
                self._position_timer.start()

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
        def load_media(path: str):
            self._do_stop()  # Must be _do_stop() instead of player.stop() to avoid freeze.
            self.player.setSource(QUrl.fromLocalFile(path))
            return True

        with self._position_timer_paused():
            success = load_media(media_path)
        duration_ms = self.player.duration() if success else 0
        completion.result = (success, duration_ms)
        completion.event.set()

    @Slot(object)
    def stop(self, completion: Completion) -> None:
        with self._position_timer_paused():
            completion.result = self._do_stop()
        completion.event.set()

    @Slot(object)
    def unload(self, completion: Completion) -> None:
        with self._position_timer_paused():
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
        self._extra_worker_exit_cleanup()
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


class PositionRelay(QObject):
    """Lives on the GUI thread. AudioEngineWorker/VideoEngineWorker push
    position here via a queued connection (same pattern as FrameRelay), so
    _engine_get_current_time can read a plain attribute instead of blocking
    on a round-trip to the worker thread every UPDATE_INTERVAL tick -- which
    used to cause real, sustained lag under CPU contention, since a blocked
    GUI thread pumps no messages at all."""

    def __init__(self) -> None:
        super().__init__()
        self.position = 0.0

    @Slot(float)
    def on_position_changed(self, position: float) -> None:
        self.position = position


def wait_for_signal(
    signal: SignalInstance, value: Any
) -> Callable[[Callable[P, bool]], Callable[P, bool]]:
    """
    Many Qt functions run on threads, and this wrapper makes sure that after starting a process, the right signal is emitted before continuing the TiLiA process.
    See _do_stop in audio_worker.py/video_worker.py for an example implementation.

    :param signal: The signal to watch.
    :type signal: SignalInstance
    :param value: The "right" output value that signal should emit before continuing. (eg. on stopping player, playbackStateChanged emits StoppedState when player has been successfully stopped. Only then can we continue the rest of the update process.)
    """

    def signal_wrapper(func: Callable[P, bool]) -> Callable[P, bool]:
        timer = QTimer(singleShot=True, interval=200)
        loop = QEventLoop()
        success = False

        def value_checker(signal_value: Any) -> None:
            if signal_value == value:
                nonlocal success
                success = True
                loop.quit()

        def check_signal(*args: P.args, **kwargs: P.kwargs) -> bool:
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


class WorkerThreadPlayer(Player):
    """Base for players that run their QMediaPlayer/QAudioOutput on a
    dedicated worker QThread instead of the GUI thread (see QtAudioPlayer/
    QtVideoPlayer). Subclasses set `_worker_cls` and may override the
    `_extra_*`/`_on_load_success` hooks for anything beyond the shared
    wiring (e.g. QtVideoPlayer's widget/FrameRelay). `_requests_cls` has no
    reason to vary by media type -- override it only if that ever changes."""

    _worker_cls: type[EngineWorker]
    _requests_cls: type[EngineRequests] = EngineRequests

    def __init__(self):
        super().__init__()
        self._extra_setup()

        self.media_devices = QMediaDevices()
        self.media_devices.audioOutputsChanged.connect(self.on_audio_outputs_changed)

        # Constructed on the GUI thread, before the worker thread starts, so
        # queued connections from the worker resolve correctly.
        self._position_relay = PositionRelay()

        self._thread = QThread()
        self._worker = self._worker_cls()
        self._worker.moveToThread(self._thread)
        self._requests = self._requests_cls()

        self._worker.position_changed.connect(self._position_relay.on_position_changed)
        self._connect_extra()

        self._requests.load_requested.connect(self._worker.load)
        self._requests.stop_requested.connect(self._worker.stop)
        self._requests.unload_requested.connect(self._worker.unload)
        self._requests.get_duration_requested.connect(self._worker.get_duration)
        self._requests.exit_requested.connect(self._worker.exit)
        self._requests.seek_requested.connect(self._worker.seek)
        self._requests.play_requested.connect(self._worker.play)
        self._requests.pause_requested.connect(self._worker.pause)
        self._requests.set_volume_requested.connect(self._worker.set_volume)
        self._requests.set_mute_requested.connect(self._worker.set_mute)
        self._requests.set_playback_rate_requested.connect(
            self._worker.set_playback_rate
        )
        self._requests.set_loop_requested.connect(self._worker.set_loop)
        self._requests.set_default_device_requested.connect(
            self._worker.set_default_device
        )

        self._thread.started.connect(self._worker.setup)
        self._thread.start()
        self._exited = False

    def _extra_setup(self) -> None:
        """Hook for GUI-thread-affinity objects that must exist before the
        worker thread starts (e.g. QtVideoPlayer's widget/FrameRelay)."""

    def _connect_extra(self) -> None:
        """Hook for extra worker -> GUI signal wiring (e.g. frame_ready)."""

    def _on_load_success(self) -> None:
        """Hook called after a successful load (e.g. QtVideoPlayer shows
        its widget)."""

    def _extra_exit_cleanup(self) -> None:
        """Hook for cleanup after the worker thread quits (e.g.
        QtVideoPlayer deleting its widget)."""

    def on_media_load_done(self, path, start, end):
        super().on_media_load_done(path, start, end)
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)

    def on_audio_outputs_changed(self) -> None:
        self._requests.set_default_device_requested.emit()

    def _engine_load_media(self, media_path: str) -> bool:
        completion = Completion()
        self._requests.load_requested.emit(media_path, completion)
        completion.event.wait()
        success, duration_ms = completion.result
        if success:
            self.on_media_duration_available(duration_ms / 1000)
            self._on_load_success()
        return success

    def _engine_get_current_time(self):
        return self._position_relay.position

    def _engine_seek(self, time: float) -> None:
        self._requests.seek_requested.emit(time)

    def _engine_play(self) -> None:
        self._requests.play_requested.emit()

    def _engine_pause(self) -> None:
        self._requests.pause_requested.emit()

    def _engine_unpause(self) -> None:
        self._requests.play_requested.emit()

    def _engine_stop(self) -> None:
        completion = Completion()
        self._requests.stop_requested.emit(completion)
        completion.event.wait()

    def _engine_unload_media(self) -> None:
        completion = Completion()
        self._requests.unload_requested.emit(completion)
        completion.event.wait()

    def _engine_get_media_duration(self) -> float:
        completion = Completion()
        self._requests.get_duration_requested.emit(completion)
        completion.event.wait()
        return completion.result

    def _engine_exit(self) -> None:
        # Idempotent: once the worker thread has quit, nothing is left to
        # service a new request -- a second call would otherwise hang
        # forever on completion.event.wait(). Player.destroy() can
        # legitimately be called more than once (test fixtures, real app
        # shutdown paths).
        if self._exited:
            return
        self._exited = True
        completion = Completion()
        self._requests.exit_requested.emit(completion)
        completion.event.wait()
        self._thread.quit()
        self._thread.wait()
        self._extra_exit_cleanup()
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.NO_MEDIA)

    def _engine_set_volume(self, volume: int) -> None:
        self._requests.set_volume_requested.emit(volume)

    def _engine_set_mute(self, is_muted: bool) -> None:
        self._requests.set_mute_requested.emit(is_muted)

    def _engine_try_playback_rate(self, playback_rate: float) -> None:
        self._requests.set_playback_rate_requested.emit(playback_rate)

    def _engine_set_playback_rate(self, playback_rate: float) -> None:
        pass

    def _engine_loop(self, is_looping: bool) -> None:
        self._requests.set_loop_requested.emit(is_looping)
