from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QSizePolicy

from tilia.requests import Post, post
from tilia.ui.player import PlayerStatus
from tilia.ui.windows.view_window import ViewWindow

from .base import Player
from .qtplayer import PositionRelay
from .video_worker import Completion, FrameRelay, VideoEngineRequests, VideoEngineWorker


class QtVideoPlayer(Player):
    """Video playback on a dedicated worker QThread (see video_worker.py),
    same reentrancy fix as QtAudioPlayer. self.widget (QVideoWidget) stays
    on the GUI thread; the player pairs with a same-thread QVideoSink
    instead, relaying frames to the widget via FrameRelay. Pairing the
    worker-thread player directly with the GUI-thread widget via
    setVideoOutput() looks fine (no crash, correct state transitions) but
    silently drops all frame delivery -- see FrameRelay's docstring.
    """

    MEDIA_TYPE = "video"

    def __init__(self):
        super().__init__()

        self.widget = QVideoWindow()

        # Must happen before the worker thread starts and constructs its own
        # QMediaPlayer/QAudioOutput: initialising Qt Multimedia backend
        # objects concurrently from two threads deadlocks (see qtaudio.py).
        self.media_devices = QMediaDevices()
        self.media_devices.audioOutputsChanged.connect(self.on_audio_outputs_changed)

        # Constructed on the GUI thread, before the worker thread starts, so
        # queued connections from the worker resolve correctly (see
        # FrameRelay/PositionRelay docstrings).
        self._frame_relay = FrameRelay(self.widget)
        self._position_relay = PositionRelay()

        self._thread = QThread()
        self._worker = VideoEngineWorker()
        self._worker.moveToThread(self._thread)
        self._requests = VideoEngineRequests()

        self._worker.position_changed.connect(self._position_relay.on_position_changed)
        self._worker.frame_ready.connect(self._frame_relay.on_frame)

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
            self.widget.show()
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
        if self._exited:
            return
        self._exited = True
        completion = Completion()
        self._requests.exit_requested.emit(completion)
        completion.event.wait()
        self._thread.quit()
        self._thread.wait()
        self.widget.deleteLater()
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


class QVideoWindow(ViewWindow, QVideoWidget):
    def __init__(self):
        super().__init__("TiLiA Player", menu_title="Video Player")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resize(800, 600)
