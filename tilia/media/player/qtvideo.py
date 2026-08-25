from __future__ import annotations

from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QSizePolicy

from tilia.ui.windows.view_window import ViewWindow

from .qtplayer import WorkerThreadPlayer
from .video_worker import FrameRelay, VideoEngineWorker


class QtVideoPlayer(WorkerThreadPlayer):
    """Video playback on a dedicated worker QThread (see video_worker.py),
    same reentrancy fix as QtAudioPlayer. self.widget (QVideoWidget) stays
    on the GUI thread; the player pairs with a same-thread QVideoSink
    instead, relaying frames to the widget via FrameRelay. Pairing the
    worker-thread player directly with the GUI-thread widget via
    setVideoOutput() looks fine (no crash, correct state transitions) but
    silently drops all frame delivery -- see FrameRelay's docstring.
    """

    MEDIA_TYPE = "video"
    _worker_cls = VideoEngineWorker

    def _extra_setup(self) -> None:
        self.widget = QVideoWindow()
        self._frame_relay = FrameRelay(self.widget)

    def _connect_extra(self) -> None:
        self._worker.frame_ready.connect(self._frame_relay.on_frame)

    def _on_load_success(self) -> None:
        self.widget.show()

    def _extra_exit_cleanup(self) -> None:
        self.widget.deleteLater()


class QVideoWindow(ViewWindow, QVideoWidget):
    def __init__(self):
        super().__init__("TiLiA Player", menu_title="Video Player")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resize(800, 600)
