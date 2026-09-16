from __future__ import annotations

from .qtplayer import EngineWorker


class AudioEngineWorker(EngineWorker):
    """Audio has nothing beyond EngineWorker's shared player/audio-output
    machinery -- see VideoEngineWorker for the video-specific additions."""
