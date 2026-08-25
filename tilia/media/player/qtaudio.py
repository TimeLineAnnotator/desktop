from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtMultimedia import QMediaDevices

from tilia.requests import Post, post
from tilia.ui.player import PlayerStatus

from .audio_worker import AudioEngineRequests, AudioEngineWorker, Completion
from .base import Player
from .qtplayer import PositionRelay


class QtAudioPlayer(Player):
    """Audio playback on a dedicated worker QThread (see audio_worker.py),
    not the GUI thread. QtPlayer's wait_for_signal blocks on a nested
    QEventLoop, unsafe once a QWebEngineView has pending Chromium IPC work;
    running the player on its own thread keeps that wait off the GUI
    thread's event dispatcher entirely. QtVideoPlayer uses the same
    approach (qtvideo.py/video_worker.py).
    """

    MEDIA_TYPE = "audio"

    def __init__(self):
        super().__init__()

        # Must happen before the worker thread starts and constructs its own
        # QMediaPlayer/QAudioOutput: initialising Qt Multimedia backend
        # objects concurrently from two threads deadlocks (observed
        # empirically -- constructing QMediaDevices here races with
        # AudioEngineWorker.setup() constructing QMediaPlayer on the worker
        # thread, most likely a backend-global-init lock, e.g. COM apartment
        # init on Windows).
        self.media_devices = QMediaDevices()
        self.media_devices.audioOutputsChanged.connect(self.on_audio_outputs_changed)

        # Constructed on the GUI thread, before the worker thread starts, so
        # it has real GUI-thread affinity for the queued connection from
        # AudioEngineWorker's (worker-thread) position_changed signal to
        # work (see PositionRelay's docstring in qtplayer.py).
        self._position_relay = PositionRelay()

        self._thread = QThread()
        self._worker = AudioEngineWorker()
        self._worker.moveToThread(self._thread)
        self._requests = AudioEngineRequests()

        self._worker.position_changed.connect(self._position_relay.on_position_changed)

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

    def _engine_stop(self):
        completion = Completion()
        self._requests.stop_requested.emit(completion)
        completion.event.wait()
        return completion.result

    def _engine_unload_media(self):
        completion = Completion()
        self._requests.unload_requested.emit(completion)
        completion.event.wait()

    def _engine_get_media_duration(self) -> float:
        completion = Completion()
        self._requests.get_duration_requested.emit(completion)
        completion.event.wait()
        return completion.result

    def _engine_exit(self):
        # Idempotent: once the worker thread has quit, nothing is left to
        # service a new request -- a second call to _engine_exit() would
        # otherwise hang forever on completion.event.wait(). Player.destroy()
        # can legitimately be called more than once (test fixtures, real app
        # shutdown paths).
        if self._exited:
            return
        self._exited = True
        completion = Completion()
        self._requests.exit_requested.emit(completion)
        completion.event.wait()
        self._thread.quit()
        self._thread.wait()
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
