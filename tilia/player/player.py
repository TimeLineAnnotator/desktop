"""
Handles media playback.

Defines an interface Player, which is implemented, currently, by a PygamePlayer (for audio playback)
and a VlcPlayer (for video playback).

"""

from __future__ import annotations

import os.path
import subprocess
import time
import tkinter as tk

import vlc

from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)
import threading

import pygame

import tilia.globals_ as globals_
import tilia.events as events
from tilia.events import Subscriber, EventName
from tilia.exceptions import AppException


class MediaLoadFailedError(AppException):
    pass


class NoMediaLoadedError(AppException):
    pass


class Player(Subscriber, ABC):
    """Interface for media playback engines."""

    update_interval = 100

    def __init__(self):
        super(Player, self).__init__()

        events.subscribe(EventName.PLAYER_REQUEST_TO_PLAYPAUSE, self),
        events.subscribe(EventName.PLAYER_REQUEST_TO_STOP, self),
        events.subscribe(EventName.PLAYER_REQUEST_TO_SEEK, self),
        events.subscribe(EventName.PLAYER_REQUEST_TO_UNLOAD_MEDIA, self),
        events.subscribe(EventName.PLAYER_REQUEST_TO_LOAD_MEDIA, self)

        logger.debug("Creating Player...")
        self.media_loaded = False
        self.media_length = 1.0
        self.playback_start = 0.0
        self.playback_end = 0.0
        self.current_time = 0.0
        self.media_path = ""
        self.playing = False
        self.paused = False

    @property
    def playback_length(self):
        return self.playback_end - self.playback_start

    def load_media(self, media_path: str, start: float = 0.0, end: float = 0.0):
        """Loads media into pygame mixer and resizes timelines"""
        if self.playing:
            self.stop()

        self._engine_load_media(media_path)
        self.media_path = media_path

        self.media_length = self._engine_get_media_length()
        self.playback_start = start

        if end:
            self.playback_end = end
        else:
            self.playback_end = self.media_length

        if start:
            self._engine_seek(start)

        globals_.MEDIA_LENGTH = self.playback_length

        events.post(
            EventName.PLAYER_MEDIA_LOADED,
            self.media_path,
            self.media_length,
            self.playback_length,
        )

        self.media_loaded = True

        events.post(EventName.PLAYER_AUDIO_TIME_CHANGE, 0.0)

        logger.info(
            f"Media loaded succesfully: path='{self.media_path}' length='{self.media_length}'"
        )

    def unload_media(self):
        self._engine_unload_media()
        self.media_loaded = False
        self.media_length = 1.0
        self.current_time = 0.0
        self.media_path = ""
        self.playing = False
        self.paused = False

    def play_pause(self) -> bool:
        """Plays or pauses the current song.
        Returns the paused state after the call."""

        if not self.media_path:
            raise NoMediaLoadedError(
                "No media loaded. Load file via 'File > Load Media File' before playing."
            )

        if not self.playing:
            self._engine_play()
            self.paused = False
            self.playing = True
            self._start_play_loop()
            events.post(EventName.PLAYER_UNPAUSED)

        elif self.paused:
            self._engine_unpause()
            self.paused = False
            self._start_play_loop()
            events.post(EventName.PLAYER_UNPAUSED)

        else:
            self._engine_pause()
            self.paused = True
            events.post(EventName.PLAYER_PAUSED)

        return self.paused

    def stop(self):
        """Stops music playback and resets slider position"""
        events.post(EventName.PLAYER_STOPPING)
        logger.debug("Stopping media playback.")
        if not self.playing:
            return

        self._engine_stop()
        self.paused = False
        self.playing = False

        self._engine_seek(self.playback_start)
        self.current_time = self.playback_start

        events.post(EventName.PLAYER_STOPPED)
        events.post(EventName.PLAYER_AUDIO_TIME_CHANGE, self.current_time)

    def on_request_to_seek(self, time: float):
        if self.media_loaded:
            self.seek(time)
        else:
            logger.debug(f"No media loaded. No need to seek.")

    def seek(self, time: float) -> None:
        self._engine_seek(time)
        self.current_time = time
        globals_.CURRENT_TIME = time
        events.post(EventName.PLAYER_AUDIO_TIME_CHANGE, self.current_time)

    def _start_play_loop(self):
        threading.Thread(target=self._play_loop).start()

    def _play_loop(self) -> None:
        while self.playing and not self.paused:
            self.current_time = self._engine_get_current_time() - self.playback_start
            events.post(EventName.PLAYER_AUDIO_TIME_CHANGE, self.current_time)
            if self.current_time >= self.playback_length:
                self.stop()
            time.sleep(self.update_interval / 1000)

    def clear(self):
        logger.debug(f"Clearing player...")
        self.unload_media()

    def destroy(self):
        self.unload_media()
        self.unsubscribe_from_all()
        self._engine_exit()

    def sounding(self):
        """Determines if there is media actually played (i.e. loaded and not paused or stopped) at the moment"""
        return self.playing and not self.paused

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

    def on_subscribed_event(
        self, event_name: EventName, *args: tuple, **kwargs: dict
    ) -> None:
        event_to_callback = {
            EventName.PLAYER_REQUEST_TO_PLAYPAUSE: self.play_pause,
            EventName.PLAYER_REQUEST_TO_STOP: self.stop,
            EventName.PLAYER_REQUEST_TO_SEEK: self.on_request_to_seek,
            EventName.PLAYER_REQUEST_TO_UNLOAD_MEDIA: self.unload_media,
            EventName.PLAYER_REQUEST_TO_LOAD_MEDIA: self.load_media,
        }

        event_to_callback[event_name](*args, **kwargs)

    def __repr__(self):
        return f"{type(self)}-{id(self)}"


class VlcPlayer(Player):
    """Handles video playback. Depends on an existing installation of VLC."""

    def __init__(self):
        super().__init__()

        self.vlc_instance = vlc.Instance()
        self.media_player = self.vlc_instance.media_player()

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

        # must be playing to get media length
        self.media_player.play()
        time.sleep(0.5)  # must wait so pause works
        self.media_player.pause()
        self._media_length = self.media_player.get_length() / 1000
        self._engine_seek(0.0)

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
        self.media_player.destroy()


class PygamePlayer(Player):
    """Preferred audio player. Only supports .ogg natively.
    Other audio formats are automatically converted to .ogg using
    ffmpeg. Converting relies on an existing ffmpeg installation."""

    def __init__(self):
        super().__init__()

        # Initialize Pygame Mixer
        pygame.init()

        # Set a pygame event for tracking if the song has ended
        self.endevent = pygame.USEREVENT + 1
        pygame.mixer.music.set_endevent(self.endevent)

        self.playback_offset = 0.0

    def load_media(self, media_path: str, start: float = 0.0, end: float = 0.0):
        _, extension = os.path.splitext(media_path)

        if extension in globals_.SUPPORTED_AUDIO_FORMATS:
            media_path = self._convert_audio_to_ogg(media_path)

        super().load_media(media_path)

    @staticmethod
    def _convert_audio_to_ogg(audio_path: str) -> str:
        """Converts audio to .ogg. Save converted audio to same folder."""

        output_path = os.path.splitext(audio_path)[0] + ".ogg"

        # TODO display dialog so user can choose ffmpeg path
        conversion_command = (
            f"""{globals_.FFMPEG_PATH} -i "{audio_path}" "{output_path}\""""
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
            raise MediaLoadFailedError(f"pygame.error: {err}")

    def _engine_get_current_time(self):
        """Update current time to match playback slider position"""
        return pygame.mixer.music.get_pos() / 1000.0 + self.playback_offset

    def _engine_seek(self, time: float) -> None:
        self.playback_offset = time
        pygame.mixer.music.play(loops=0, start=time)
        if not self.sounding():
            pygame.mixer.music.pause()
        self.current_time = time

    def _engine_play(self) -> None:
        pygame.mixer.music.play(loops=0, start=self.current_time)

    def _engine_pause(self) -> None:
        pygame.mixer.music.pause()

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
        pygame.quit()
