from __future__ import annotations

import sys
import threading
import time
from abc import ABC, abstractmethod
import logging
from pathlib import Path

from tilia.exceptions import TiliaException
from tilia.media import exporter
from tilia.repr import default_str
from tilia.requests import listen, Post, serve, Get, post, stop_listening_to_all, get

logger = logging.getLogger(__name__)


class MediaLoadError(TiliaException):
    pass


class NoMediaLoadedError(TiliaException):
    pass


class Player(ABC):
    """Interface for media playback engines."""

    update_interval = 25
    MEDIA_TYPE = None

    def __init__(self, previous_media_length: float = 0.0):
        super().__init__()

        listen(self, Post.PLAYER_REQUEST_TO_PLAYPAUSE, self.toggle_play)
        listen(self, Post.PLAYER_REQUEST_TO_STOP, self.stop)
        listen(self, Post.PLAYER_REQUEST_TO_SEEK, self.on_request_to_seek)
        listen(
            self,
            Post.PLAYER_REQUEST_TO_SEEK_IF_NOT_PLAYING,
            lambda *args: self.on_request_to_seek(*args, if_paused=True),
        )
        listen(self, Post.PLAYER_REQUEST_TO_UNLOAD_MEDIA, self.unload_media)
        listen(self, Post.PLAYER_REQUEST_TO_LOAD_MEDIA, self.load_media)
        listen(self, Post.REQUEST_EXPORT_AUDIO, self.on_request_to_export_audio),
        serve(self, Get.CURRENT_PLAYBACK_TIME, self.reply_playback_time)
        serve(self, Get.MEDIA_DURATION, lambda: self.media_length)
        serve(self, Get.MEDIA_PATH, lambda: self.media_path)

        logger.debug("Creating Player...")
        self.media_loaded = False
        self.previous_media_length = previous_media_length
        self.media_length = previous_media_length
        self.playback_start = 0.0
        self.playback_end = 0.0
        self.current_time = 0.0
        self.media_path = ""
        self.playing = False

    def __str__(self):
        return default_str(self)

    @property
    def playback_length(self):
        return self.playback_end - self.playback_start

    def load_media(self, media_path: str | Path, start: float = 0.0, end: float = 0.0):
        """Loads media into pygame mixer and resizes timelines"""
        if self.playing:
            self.stop()

        try:
            self._engine_load_media(media_path)
        except MediaLoadError:
            post(
                Post.REQUEST_DISPLAY_ERROR,
                title="Media load error",
                message=f'Could not load "{media_path}".'
                f"Try loading another media file.",
            )
            return

        self.media_path = str(media_path)

        previous_media_length = self.media_length
        self.media_length = self._engine_get_media_length()
        self.playback_start = start

        if end:
            self.playback_end = end
        else:
            self.playback_end = self.media_length

        if start:
            self._engine_seek(start)

        post(
            Post.PLAYER_MEDIA_LOADED,
            self.media_path,
            self.media_length,
            self.playback_length,
            previous_media_length,
        )

        self.media_loaded = True

        post(Post.PLAYER_MEDIA_TIME_CHANGE, 0.0)

        logger.info(
            f"Media loaded succesfully: path='{self.media_path}'"
            f" length='{self.media_length}'"
        )

    def unload_media(self):
        self._engine_unload_media()
        self.media_loaded = False
        self.previous_media_length = self.media_length
        self.media_length = 1.0
        self.current_time = 0.0
        self.media_path = ""
        self.playing = False
        logger.info("Media unloaded succesfully.")
        post(Post.PLAYER_MEDIA_UNLOADED)

    def toggle_play(self):
        """Plays or pauses the current song.
        Returns the paused state after the call."""

        if not self.media_path:
            raise NoMediaLoadedError(
                "No media loaded. "
                "Load file via 'File > Load Media File' before playing."
            )

        if not self.playing:
            self._engine_play()
            self.playing = True
            self._start_play_loop()
            post(Post.PLAYER_UNPAUSED)
            logger.debug("Media is now playing.")

        else:
            self._engine_pause()
            self.playing = False
            post(Post.PLAYER_PAUSED)
            logger.debug("Media is now paused.")

    def stop(self):
        """Stops music playback and resets slider position"""
        post(Post.PLAYER_STOPPING)
        logger.debug("Stopping media playback.")
        if not self.playing and self.current_time == 0.0:
            return

        self._engine_stop()
        self.playing = False

        self._engine_seek(self.playback_start)
        self.current_time = self.playback_start

        post(Post.PLAYER_STOPPED)
        post(Post.PLAYER_MEDIA_TIME_CHANGE, self.current_time)

    def on_request_to_seek(self, time: float, if_paused: bool = False) -> None:
        logger.debug(f"Processing request to seek with {time=}, {if_paused=}")
        if if_paused and self.playing:
            logger.debug("Media is playing. Will not seek.")
            return

        if self.media_loaded:
            logger.debug(f"Seeking to {time}...")
            self._engine_seek(time)
            logger.debug(f"New playback time is {self.current_time}.")
        else:
            logger.debug("No media loaded. No need to seek.")
        self.current_time = time
        post(Post.PLAYER_MEDIA_TIME_CHANGE, self.current_time)

    def on_request_to_export_audio(
        self, segment_name: str, start_time: float, end_time: float
    ):
        logger.debug("User requested audio segment export.")

        if self.MEDIA_TYPE != "audio":
            post(
                Post.REQUEST_DISPLAY_ERROR,
                title="Export audio",
                message="Can only export from audio files.",
            )
            return

        if sys.platform != "win32":
            ERROR_MESSAGE = "Exporting audio is currently only available on Windows."
            post(
                Post.REQUEST_DISPLAY_ERROR, title="Export audio", message=ERROR_MESSAGE
            )
            return

        export_dir = get(Get.DIR_FROM_USER, "Export audio")

        exporter.export_audio(
            audio_path=Path(self.media_path),
            dir=export_dir,
            file_title=get(Get.MEDIA_TITLE),
            start_time=start_time,
            end_time=end_time,
            segment_name=segment_name,
        )

    def _start_play_loop(self):
        threading.Thread(target=self._play_loop, daemon=True).start()

    def _play_loop(self) -> None:
        while self.playing:
            self.current_time = self._engine_get_current_time() - self.playback_start
            post(Post.PLAYER_MEDIA_TIME_CHANGE, self.current_time, logging_level=5)
            if self.current_time >= self.playback_length:
                self.stop()
            time.sleep(self.update_interval / 1000)

    def clear(self):
        logger.debug("Clearing player...")
        self.unload_media()

    def destroy(self):
        self.unload_media()
        stop_listening_to_all(self)
        self._engine_exit()

    def restore_state(self, media_path: str):
        if self.media_path == media_path:
            return
        else:
            self.unload_media()
            self.load_media(media_path)

    @abstractmethod
    def _engine_pause(self) -> None:
        ...

    @abstractmethod
    def _engine_unpause(self) -> None:
        ...

    @abstractmethod
    def _engine_get_current_time(self) -> float:
        ...

    @abstractmethod
    def _engine_stop(self):
        ...

    @abstractmethod
    def _engine_seek(self, time: float) -> None:
        ...

    @abstractmethod
    def _engine_unload_media(self) -> None:
        ...

    @abstractmethod
    def _engine_load_media(self, media_path: str) -> None:
        ...

    @abstractmethod
    def _engine_play(self) -> None:
        ...

    @abstractmethod
    def _engine_get_media_length(self) -> float:
        ...

    @abstractmethod
    def _engine_exit(self) -> float:
        ...

    def __repr__(self):
        return f"{type(self)}-{id(self)}"

    def reply_playback_time(self):
        return self.current_time
