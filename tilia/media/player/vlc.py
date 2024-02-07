from __future__ import annotations
import time
import tkinter as tk

from tilia.exceptions import TiliaException
from .base import MediaLoadError, Player

try:
    import vlc
except OSError:
    # VLC is not installed, error will be raised when trying to load a media file
    pass


class VLCNotInstalledError(TiliaException):
    pass


class VlcPlayer(Player):
    """Handles video playback. Depends on an existing installation of VLC."""

    MEDIA_TYPE = "video"

    def __init__(self, previous_media_length: float = 1.0):
        super().__init__(previous_media_length)

        try:
            self.vlc_instance = vlc.Instance()
        except NameError:
            raise VLCNotInstalledError

        self.vlc_instance.log_unset()
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
        self.media_player.release()
        self.vlc_instance.release()
        self.player_window.destroy()
