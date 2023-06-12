from pathlib import Path
import logging

from tilia import globals_
from tilia.media import player
from tilia.media.player import Player
from tilia.requests import Post, post

logger = logging.getLogger(__name__)


class MediaLoader:
    def __init__(self, player: Player):
        self.player = player

    def load(self, path: Path):
        extension, media_type = get_media_type_from_path(path)

        if media_type == "unsupported":
            post(
                Post.REQUEST_DISPLAY_ERROR,
                title="Media file not supported",
                message=f"Media file of type '{extension}' not supported."
                f"Try loading a supported file type.",
            )
            return

        # change player to audio or video if needed
        if self.player.MEDIA_TYPE == "video" and media_type == "audio":
            self._change_player_to_audio()
        elif self.player.MEDIA_TYPE == "audio" and media_type == "video":
            self._change_player_to_video()

        self.player.load_media(path)

        return self.player

    def _change_player_to_audio(self) -> None:
        self.player.destroy()
        self.player = player.PygamePlayer(
            previous_media_length=self.player.previous_media_length
        )
        logger.debug("Changed to audio player.")

    def _change_player_to_video(self) -> None:
        try:
            newplayer = player.VlcPlayer(
                previous_media_length=self.player.previous_media_length
            )
            logger.debug("Changed to video player.")
        except player.VLCNotInstalledError:
            post(
                Post.REQUEST_DISPLAY_ERROR,
                title="VLC not installed",
                message="To load a video file, VLC player must be installed.\n"
                "Install VLC from https://www.videolan.org, "
                "restart App and reload the file.",
            )
            return

        self.player.destroy()
        self.player = newplayer


def get_media_type_from_path(path: Path):
    extension = path.suffix[1:].lower()
    audio_exts = globals_.SUPPORTED_AUDIO_FORMATS + globals_.CONVERTIBLE_AUDIO_FORMATS
    video_exts = globals_.SUPPORTED_VIDEO_FORMATS

    if extension in audio_exts:
        return extension, "audio"
    elif extension in video_exts:
        return extension, "video"
    else:
        return extension, "unsupported"
