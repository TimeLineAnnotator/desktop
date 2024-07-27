from pytube import YouTube

from tilia.media.player import Player
from tilia.media.player.qtplayer import QtPlayer
from tilia.requests import post, Post


class CLIVideoPlayer(QtPlayer):
    # inherits only from QtPlayer to prevent
    # the creation of a video widget
    pass


class CLIYoutubePlayer(Player):
    MEDIA_TYPE = "youtube"

    def load_media(self, media_path: str, start: float = 0.0, end: float = 0.0):
        try:
            youtube = YouTube(media_path)
            self.on_media_duration_available(youtube.length)
            return True
        except:
            post(
                Post.DISPLAY_ERROR,
                'Failed to get YouTube video duration. Please set the duration with "metadata set-media-length"',
            )
            return False

    def _engine_pause(self) -> None:
        ...

    def _engine_unpause(self) -> None:
        ...

    def _engine_get_current_time(self) -> float:
        ...

    def _engine_stop(self):
        ...

    def _engine_seek(self, time: float) -> None:
        ...

    def _engine_unload_media(self) -> None:
        ...

    def _engine_load_media(self, media_path: str) -> None:
        ...

    def _engine_play(self) -> None:
        ...

    def _engine_get_media_duration(self) -> float:
        ...

    def _engine_exit(self) -> float:
        ...

    def _engine_set_volume(self, volume: int) -> None:
        ...

    def _engine_set_mute(self, is_muted: bool) -> None:
        ...

    def _engine_try_playback_rate(self, playback_rate: float) -> None:
        ...

    def _engine_set_playback_rate(self, playback_rate: float) -> None:
        ...

    def _engine_loop(self, is_looping: bool) -> None:
        ...
