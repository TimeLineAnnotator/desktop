"""
Handles media playback.

Defines an interface Player, which is implemented, currently, by a PygamePlayer (for audio playback)
and a VlcPlayer (for video playback).

"""

from __future__ import annotations

import os.path
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path

import vlc

from abc import ABC, abstractmethod
import logging

from tilia import dirs

logger = logging.getLogger(__name__)
import threading

import pygame

import tilia.globals_ as globals_
import tilia.events as events
from tilia.events import Event, subscribe
from tilia.exceptions import AppException


class MediaLoadError(AppException):
    pass


class NoMediaLoadedError(AppException):
    pass

class VLCNotInstalledError(AppException):
    pass

class Player(ABC):
    """Interface for media playback engines."""

    update_interval = 100

    def __init__(self, previous_media_length: float = 1.0):
        super().__init__()

        subscribe(self, Event.PLAYER_REQUEST_TO_PLAYPAUSE, self.play_pause)
        subscribe(self, Event.PLAYER_REQUEST_TO_STOP, self.stop)
        subscribe(self, Event.PLAYER_REQUEST_TO_SEEK, self.on_request_to_seek)
        subscribe(
            self,
            Event.PLAYER_REQUEST_TO_SEEK_IF_NOT_PLAYING,
            lambda *args: self.on_request_to_seek(*args, if_paused=True),
        )
        subscribe(self, Event.PLAYER_REQUEST_TO_UNLOAD_MEDIA, self.unload_media)
        subscribe(self, Event.PLAYER_REQUEST_TO_LOAD_MEDIA, self.load_media)

        logger.debug("Creating Player...")
        self.media_loaded = False
        self.previous_media_length = previous_media_length
        self.media_length = previous_media_length
        self.playback_start = 0.0
        self.playback_end = 0.0
        self.current_time = 0.0
        self.media_path = ""
        self.playing = False

    @property
    def playback_length(self):
        return self.playback_end - self.playback_start

    def load_media(self, media_path: str, start: float = 0.0, end: float = 0.0):
        """Loads media into pygame mixer and resizes timelines"""
        if self.playing:
            self.stop()

        try:
            self._engine_load_media(media_path)
        except MediaLoadError:
            events.post(Event.REQUEST_DISPLAY_ERROR,
                        title='Media load error',
                        message=f'Could not load "{media_path}".'
                                f'Try loading another media file.'
                        )
            return

        self.media_path = media_path

        previous_media_length = self.media_length
        self.media_length = self._engine_get_media_length()
        self.playback_start = start

        if end:
            self.playback_end = end
        else:
            self.playback_end = self.media_length

        if start:
            self._engine_seek(start)

        events.post(
            Event.PLAYER_MEDIA_LOADED,
            self.media_path,
            self.media_length,
            self.playback_length,
            previous_media_length,
        )

        self.media_loaded = True

        events.post(Event.PLAYER_MEDIA_TIME_CHANGE, 0.0)

        logger.info(
            f"Media loaded succesfully: path='{self.media_path}' length='{self.media_length}'"
        )

    def unload_media(self):
        self._engine_unload_media()
        self.media_loaded = False
        self.previous_media_length = self.media_length
        self.media_length = 1.0
        self.current_time = 0.0
        self.media_path = ""
        self.playing = False
        logger.info(f"Media unloaded succesfully.")

    def play_pause(self):
        """Plays or pauses the current song.
        Returns the paused state after the call."""

        if not self.media_path:
            raise NoMediaLoadedError(
                "No media loaded. Load file via 'File > Load Media File' before playing."
            )

        if not self.playing:
            self._engine_play()
            self.playing = True
            self._start_play_loop()
            events.post(Event.PLAYER_UNPAUSED)
            logger.debug(f"Media is now playing.")

        else:
            self._engine_pause()
            self.playing = False
            events.post(Event.PLAYER_PAUSED)
            logger.debug(f"Media is now paused.")

    def stop(self):
        """Stops music playback and resets slider position"""
        events.post(Event.PLAYER_STOPPING)
        logger.debug("Stopping media playback.")
        if not self.playing and self.current_time == 0.0:
            return

        self._engine_stop()
        self.playing = False

        self._engine_seek(self.playback_start)
        self.current_time = self.playback_start

        events.post(Event.PLAYER_STOPPED)
        events.post(Event.PLAYER_MEDIA_TIME_CHANGE, self.current_time)

    def on_request_to_seek(self, time: float, if_paused: bool = False) -> None:

        logger.debug(f"Processing request to seek with {time=}, {if_paused=}")
        if if_paused and self.playing:
            logger.debug(f"Media is playing. Will not seek.")
            return

        if self.media_loaded:
            logger.debug(f"Seeking to {time}...")
            self._engine_seek(time)
            logger.debug(f"New playback time is {self.current_time}.")
        else:
            logger.debug(f"No media loaded. No need to seek.")
        self.current_time = time
        events.post(Event.PLAYER_MEDIA_TIME_CHANGE, self.current_time)

    def _start_play_loop(self):
        threading.Thread(target=self._play_loop, daemon=True).start()

    def _play_loop(self) -> None:
        while self.playing:
            self.current_time = self._engine_get_current_time() - self.playback_start
            events.post(Event.PLAYER_MEDIA_TIME_CHANGE, self.current_time, logging_level=5)
            if self.current_time >= self.playback_length:
                self.stop()
            time.sleep(self.update_interval / 1000)

    def clear(self):
        logger.debug(f"Clearing player...")
        self.unload_media()

    def destroy(self):
        self.unload_media()
        events.unsubscribe_from_all(self)
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


class VlcPlayer(Player):
    """Handles video playback. Depends on an existing installation of VLC."""

    def __init__(self, previous_media_length: float = 1.0):
        super().__init__(previous_media_length)

        self.vlc_instance = vlc.Instance()
        if not self.vlc_instance:
            raise VLCNotInstalledError
        self.media_player = self.vlc_instance.media_player_new()
        self._media_length = 0.0

        self.player_window = tk.Toplevel()
        self.player_window.geometry("800x600")
        self.player_window.protocol(
            "WM_DELETE_WINDOW", lambda: None
        )  # disable close button

        self.media_player.set_hwnd(self.player_window.winfo_id())

    def _engine_stop(self):
        self.media_player.pause()
        self.media_player.set_position(0)

    def _engine_load_media(self, media_path: str):
        media = self.vlc_instance.media_new(media_path)
        self.media_player.set_media(media)

        self._setup_media_length()

        if not self._media_length:
            raise MediaLoadError

        self._engine_seek(0.0)

    def _setup_media_length(self):
        MAX_RETRIES = 10
        retries = 0

        self.media_player.play()
        while not self._media_length and retries < MAX_RETRIES:
            # must play and pause first to get media length
            time.sleep(0.3)
            self._media_length = self.media_player.get_length() / 1000
            retries += 1

        self.media_player.pause()

    def _engine_get_media_length(self) -> float:
        return self._media_length

    def _engine_seek(self, time: float) -> None:
        self.media_player.set_position(time / self._media_length)

    def _engine_unload_media(self) -> None:
        pass

    def _engine_play(self) -> None:
        self.media_player.play()

    def _engine_pause(self) -> None:
        self.media_player.pause()

    def _engine_unpause(self) -> None:
        self.media_player.play()

    def _engine_get_current_time(self) -> float:
        return self.media_player.get_position() * self._media_length

    def _engine_exit(self):
        self.vlc_instance.vlm_del_media(self.media_path)
        self.player_window.destroy()


class PygamePlayer(Player):
    """Preferred audio player. Only supports .ogg natively.
    Other audio formats are automatically converted to .ogg using
    ffmpeg. Converting relies on an existing ffmpeg installation."""

    def __init__(self, previous_media_length: float = 1.0):
        super().__init__(previous_media_length)

        # Initialize Pygame Mixer
        pygame.mixer.init()
        pygame.display.init()

        # Set a pygame event for tracking if the song has ended
        self.endevent = pygame.USEREVENT + 1
        pygame.mixer.music.set_endevent(self.endevent)

        self.playback_offset = 0.0

    def load_media(self, media_path: str, start: float = 0.0, end: float = 0.0):
        extension = Path(media_path).suffix[1:]

        if extension not in globals_.SUPPORTED_AUDIO_FORMATS:
            ERROR_MESSAGE = (
                "Conversion when loading is currently only available on "
                "Windows. Convert audio file to OGG before loading."
            )

            if sys.platform != "win32":
                events.post(
                    Event.REQUEST_DISPLAY_ERROR,
                    title="Convert audio",
                    message=ERROR_MESSAGE,
                )
                return

            media_path = self._convert_audio_to_ogg(media_path)

        super().load_media(media_path)

    @staticmethod
    def _convert_audio_to_ogg(audio_path: str) -> str:
        """Converts audio to .ogg. Save converted audio to same folder."""

        output_path = os.path.splitext(audio_path)[0] + ".ogg"

        conversion_command = (
            f"""{dirs.ffmpeg_path} -i "{audio_path}" "{output_path}\""""
        )

        logger.info(f"Converting audio file {audio_path}")

        process = subprocess.Popen(conversion_command)
        process_out, process_err = process.communicate()
        process.wait()

        logger.info(f"Audio convert finished with code {process_out}, {process_err}")

        return output_path

    def _engine_load_media(self, media_path: str) -> None:
        try:
            pygame.mixer.music.load(media_path)
        except pygame.error as err:
            raise MediaLoadError(f"pygame.error: {err}")

    def _engine_get_current_time(self):
        """Update current time to match playback slider position"""
        return pygame.mixer.music.get_pos() / 1000.0 + self.playback_offset

    def _engine_seek(self, time: float) -> None:
        self.playback_offset = time
        pygame.mixer.music.play(loops=0, start=time)
        self.current_time = time
        if not self.playing:
            self._engine_pause()

    def _engine_play(self) -> None:
        try:
            pygame.mixer.music.play(loops=0, start=self.current_time)
        except pygame.error:
            pygame.mixer.music.play(loops=0)

    def _engine_pause(self) -> None:
        pygame.mixer.music.pause()
        self.playback_offset = self.current_time

    def _engine_unpause(self) -> None:
        pygame.mixer.music.unpause()

    def _engine_stop(self):
        pygame.mixer.music.stop()

        # Handle pygame event so it won't get caught in next playtime()
        for event in pygame.event.get():
            if event.type == self.endevent:
                pass

        self.playback_offset = 0.0

    def _engine_unload_media(self):
        pygame.mixer.music.unload()


    def _engine_get_media_length(self) -> float:
        return pygame.mixer.Sound(self.media_path).get_length()

    def _engine_exit(self):
        pygame.mixer.quit()
        pygame.display.quit()
