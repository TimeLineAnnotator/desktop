from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import logging

import pygame

from tilia import globals_ as globals_, dirs
from .base import MediaLoadError, Player
from tilia.requests import post, Post

logger = logging.getLogger(__name__)


class PygamePlayer(Player):
    """Preferred audio player. Only supports .ogg natively.
    Other audio formats are automatically converted to .ogg using
    ffmpeg. Converting relies on an existing ffmpeg installation."""

    MEDIA_TYPE = "audio"

    def __init__(self, previous_media_length: float = 1.0):
        super().__init__(previous_media_length)

        # Initialize Pygame Mixer
        pygame.mixer.init()
        pygame.display.init()

        # Set a pygame event for tracking if the song has ended
        self.endevent = pygame.USEREVENT + 1
        pygame.mixer.music.set_endevent(self.endevent)

        self.playback_offset = 0.0

    def load_media(self, path: str, start: float = 0.0, end: float = 0.0):
        extension = Path(path).suffix[1:]

        if extension not in globals_.SUPPORTED_AUDIO_FORMATS:
            if sys.platform == "darwin":
                ERROR_MESSAGE = "Convert file to .ogg before loading."
                post(
                    Post.REQUEST_DISPLAY_ERROR,
                    title="Convert audio",
                    message=ERROR_MESSAGE,
                )
                return
            elif sys.platform == "linux":
                if self._ffmpeg_check_linux():
                    self._convert_to_ogg_linux(path)
                else:
                    MESSAGE = (
                        "To convert to .ogg, "
                        "ffmpeg needs to be installed. "
                        "Install it or convert the file before loading."
                    )
                    post(
                        Post.REQUEST_DISPLAY_ERROR,
                        title="Convert audio",
                        message=MESSAGE,
                    )
            elif sys.platform == "win32":
                path = self._convert_to_ogg_win32(path)

        super().load_media(path)

    @staticmethod
    def _ffmpeg_check_linux():
        import os

        print(os.getcwd())
        p = subprocess.Popen(["ffmpeg -version"], shell=True)
        p.wait()
        print("------")
        print(p.returncode)
        print("------")

        return p.returncode != 127

    @staticmethod
    def _convert_to_ogg_linux(path: str):
        output_path = os.path.splitext(path)[0] + ".ogg"

        logger.info(f"Converting audio file {path}")
        print()
        p = subprocess.Popen(["ffmpeg", "-i", f"{path}", f"{output_path}", "-y"])
        process_out, process_err = p.communicate()
        p.wait()

        logger.info(f"Audio convert finished with code {process_out}, {process_err}")

        return output_path

    @staticmethod
    def _convert_to_ogg_win32(audio_path: str) -> str:
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
