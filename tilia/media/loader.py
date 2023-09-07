import re
from pathlib import Path
import logging

import tilia
from tilia import errors
import tilia.media.constants
from tilia.media import player
from tilia.media.player import Player
from tilia.ui.strings import YOUTUBE_URL_REGEX

logger = logging.getLogger(__name__)


class MediaLoader:
    def __init__(self, _player: Player):
        self.player = _player

    def load(self, path: str):
        extension, media_type = get_media_type_from_path(path)

        if media_type == "unsupported":
            tilia.errors.display(tilia.errors.UNSUPPORTED_MEDIA_FORMAT, extension)
            return False, None

        # change player to audio or video if needed
        if self.player.MEDIA_TYPE != media_type:
            self._change_player_type(media_type)

        self.player.load_media(path)

        return self.player

    def _change_player_type(self, media_type):
        self.player.destroy()

        self.player = {
            "video": player.QtVideoPlayer,
            "audio": player.QtAudioPlayer,
            "youtube": player.YouTubePlayer,
        }[media_type]()


def get_media_type_from_path(path: str):
    if re.match(YOUTUBE_URL_REGEX, path):
        return "", "youtube"

    path = Path(path)
    extension = path.suffix[1:].lower()
    audio_extensions = (
        tilia.media.constants.SUPPORTED_AUDIO_FORMATS
        + tilia.media.constants.CONVERTIBLE_AUDIO_FORMATS
    )
    video_extensions = tilia.media.constants.SUPPORTED_VIDEO_FORMATS

    if extension in audio_extensions:
        return extension, "audio"
    elif extension in video_extensions:
        return extension, "video"
    else:
        return extension, "unsupported"
