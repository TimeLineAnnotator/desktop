from __future__ import annotations

from .audio_worker import AudioEngineWorker
from .qtplayer import WorkerThreadPlayer


class QtAudioPlayer(WorkerThreadPlayer):
    """Audio playback on a dedicated worker QThread (see audio_worker.py),
    not the GUI thread. QtPlayer's wait_for_signal blocked on a nested
    QEventLoop, unsafe once a QWebEngineView has pending Chromium IPC work;
    running the player on its own thread keeps that wait off the GUI
    thread's event dispatcher entirely. QtVideoPlayer uses the same
    approach (qtvideo.py/video_worker.py).
    """

    MEDIA_TYPE = "audio"
    _worker_cls = AudioEngineWorker
