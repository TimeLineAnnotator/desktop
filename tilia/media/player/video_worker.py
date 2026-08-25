from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtMultimedia import QVideoFrame, QVideoSink
from PySide6.QtMultimediaWidgets import QVideoWidget

from .qtplayer import EngineWorker

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


class VideoEngineWorker(EngineWorker):
    """Adds a QVideoSink, paired with the player on this same worker
    thread, on top of EngineWorker's shared audio playback. Emits
    `frame_ready` for the GUI-thread FrameRelay to pick up via a queued
    connection (wired in QtVideoPlayer.__init__) -- pairing the
    worker-thread player directly with the GUI-thread QVideoWidget via
    setVideoOutput() silently drops all frame delivery cross-thread (see
    FrameRelay's docstring)."""

    frame_ready = Signal(QVideoFrame)

    def __init__(self) -> None:
        super().__init__()
        self.sink: QVideoSink | None = None
        self._latest_frame: QVideoFrame | None = None

    def _extra_worker_setup(self) -> None:
        self.sink = QVideoSink()
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._on_raw_frame)

        # Relaying every decoded frame directly would queue one delivery per
        # frame; if the GUI thread falls behind, it has to drain them in
        # order, so the picture lags audio more and more the longer that
        # persists. Caching just the latest frame and pushing on our own
        # timer bounds the backlog to one frame and self-heals instead.
        self._frame_relay_timer = QTimer()
        self._frame_relay_timer.setInterval(FRAME_RELAY_INTERVAL_MS)
        self._frame_relay_timer.timeout.connect(self._relay_latest_frame)
        self._frame_relay_timer.start()

    def _extra_worker_exit_cleanup(self) -> None:
        self._frame_relay_timer.stop()

    def _on_raw_frame(self, frame: QVideoFrame) -> None:
        self._latest_frame = frame

    def _relay_latest_frame(self) -> None:
        if self._latest_frame is not None:
            frame, self._latest_frame = self._latest_frame, None
            self.frame_ready.emit(frame)
