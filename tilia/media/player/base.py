from __future__ import annotations

import functools
import sys
from abc import ABC, abstractmethod
import logging
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QTimer

import tilia.errors
from tilia.media import exporter
from tilia.utils import get_tilia_class_string
from tilia.requests import (
    listen,
    Post,
    serve,
    Get,
    post,
    stop_listening_to_all,
    get,
    stop_serving_all,
)
from tilia.ui.strings import NO_MEDIA_LOADED_ERROR_TITLE, NO_MEDIA_LOADED_ERROR_MESSAGE

logger = logging.getLogger(__name__)


class MediaTimeChangeReason(Enum):
    PLAYBACK = auto()
    SEEK = auto()
    LOAD = auto()


class Player(ABC):
    UPDATE_INTERVAL = 100
    MEDIA_TYPE = None

    def __init__(self):
        super().__init__()

        listen(self, Post.PLAYER_TOGGLE_PLAY_PAUSE, self.toggle_play)
        listen(self, Post.PLAYER_STOP, self.stop)
        listen(self, Post.PLAYER_SEEK, self.on_seek)
        listen(
            self,
            Post.PLAYER_SEEK_IF_NOT_PLAYING,
            functools.partial(self.on_seek, if_paused=True),
        )
        listen(self, Post.PLAYER_REQUEST_TO_UNLOAD_MEDIA, self.unload_media)
        listen(self, Post.PLAYER_REQUEST_TO_LOAD_MEDIA, self.load_media)
        listen(self, Post.PLAYER_EXPORT_AUDIO, self.on_export_audio),
        serve(self, Get.MEDIA_CURRENT_TIME, lambda: self.current_time)
        serve(self, Get.MEDIA_DURATION, lambda: self.duration)
        serve(self, Get.MEDIA_PATH, lambda: self.media_path)

        self.media_loaded = False
        self.duration = 0.0
        self.playback_start = 0.0
        self.playback_end = 0.0
        self.current_time = 0.0
        self.media_path = ""
        self.playing = False

        self.qtimer = QTimer()
        self.qtimer.timeout.connect(self._play_loop)

    def __str__(self):
        return get_tilia_class_string(self)

    @property
    def playback_length(self):
        return self.playback_end - self.playback_start

    def load_media(
        self, path: str | Path, start: float = 0.0, end: float = 0.0
    ) -> bool:
        if self.playing:
            self.stop()

        success = self._engine_load_media(path)
        if not success:
            tilia.errors.display(tilia.errors.MEDIA_LOAD_FAILED, path)
            return False
        self.on_media_load_done(path, start, end)
        return True

    def on_media_load_done(self, path, start, end):
        self.media_path = str(path)
        self.playback_start = start

        post(
            Post.PLAYER_URL_CHANGED,
            self.media_path,
        )

        post(Post.PLAYER_CURRENT_TIME_CHANGED, 0.0, reason=MediaTimeChangeReason.LOAD)

        self.media_loaded = True

    def on_media_duration_available(self, duration):
        self.playback_end = self.duration = duration
        post(Post.PLAYER_DURATION_CHANGED, duration)

    def setup_playback_start_and_end(self, start, end):
        self.playback_start = start
        self.playback_end = end or self.duration

        start or self._engine_seek(start)

    def unload_media(self):
        self._engine_unload_media()
        self.media_loaded = False
        self.duration = 0.0
        self.current_time = 0.0
        self.media_path = ""
        self.playing = False
        post(Post.PLAYER_MEDIA_UNLOADED)

    def toggle_play(self):
        if not self.media_path:
            post(
                Post.DISPLAY_ERROR,
                title=NO_MEDIA_LOADED_ERROR_TITLE,
                message=NO_MEDIA_LOADED_ERROR_MESSAGE,
            )
            return

        if not self.playing:
            self._engine_play()
            self.playing = True
            self.start_play_loop()
            post(Post.PLAYER_UNPAUSED)

        else:
            self._engine_pause()
            self.stop_play_loop()
            self.playing = False
            post(Post.PLAYER_PAUSED)

    def stop(self):
        """Stops music playback and resets slider position"""
        post(Post.PLAYER_STOPPING)
        if not self.playing and self.current_time == 0.0:
            return

        self._engine_stop()
        self.stop_play_loop()
        self.playing = False

        self._engine_seek(self.playback_start)
        self.current_time = self.playback_start

        post(Post.PLAYER_STOPPED)
        post(
            Post.PLAYER_CURRENT_TIME_CHANGED,
            self.current_time,
            reason=MediaTimeChangeReason.PLAYBACK,
        )

    def on_seek(self, time: float, if_paused: bool = False) -> None:
        if if_paused and self.playing:
            return

        if self.media_loaded:
            self._engine_seek(time)

        self.current_time = time
        post(
            Post.PLAYER_CURRENT_TIME_CHANGED,
            self.current_time,
            reason=MediaTimeChangeReason.SEEK,
        )

    def on_export_audio(self, segment_name: str, start_time: float, end_time: float):
        if self.MEDIA_TYPE != "audio":
            post(
                Post.DISPLAY_ERROR,
                title="Export audio",
                message="Can only export from audio files.",
            )
            return

        if sys.platform != "darwin":
            error_message = "Exporting audio is not available or macOS."
            post(Post.DISPLAY_ERROR, title="Export audio", message=error_message)
            return

        path, _ = get(
            Get.FROM_USER_SAVE_PATH_OGG,
            "Export audio",
            f"{get(Get.MEDIA_TITLE)}_{segment_name}",
        )

        if not path:
            return

        exporter.export_audio(
            source_path=get(Get.MEDIA_PATH),
            destination_path=path,
            start_time=start_time,
            end_time=end_time,
        )

    def start_play_loop(self):
        self.qtimer.start(self.UPDATE_INTERVAL)

    def stop_play_loop(self):
        self.qtimer.stop()

    def _play_loop(self) -> None:
        self.current_time = self._engine_get_current_time() - self.playback_start
        post(
            Post.PLAYER_CURRENT_TIME_CHANGED,
            self.current_time,
            reason=MediaTimeChangeReason.PLAYBACK,
        )
        if self.current_time >= self.playback_length:
            self.stop()

    def clear(self):
        logger.debug("Clearing player...")
        self.unload_media()

    def destroy(self):
        self.unload_media()
        stop_listening_to_all(self)
        stop_serving_all(self)
        self._engine_exit()

    def restore_state(self, media_path: str):
        if self.media_path == media_path:
            return
        else:
            self.unload_media()
            self.load_media(media_path)

    @abstractmethod
    def _engine_pause(self) -> None: ...

    @abstractmethod
    def _engine_unpause(self) -> None: ...

    @abstractmethod
    def _engine_get_current_time(self) -> float: ...

    @abstractmethod
    def _engine_stop(self): ...

    @abstractmethod
    def _engine_seek(self, time: float) -> None: ...

    @abstractmethod
    def _engine_unload_media(self) -> None: ...

    @abstractmethod
    def _engine_load_media(self, media_path: str) -> None: ...

    @abstractmethod
    def _engine_play(self) -> None: ...

    @abstractmethod
    def _engine_get_media_duration(self) -> float: ...

    @abstractmethod
    def _engine_exit(self) -> float: ...

    def __repr__(self):
        return f"{type(self)}-{id(self)}"
