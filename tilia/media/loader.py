import re
from pathlib import Path

import tilia.errors
import tilia.constants
import tilia.media.constants
from tilia.media.player import Player
from tilia.requests import get, Get


def load_media(
    player: Player, path: str, initial_duration: float = 0.0
) -> tuple[bool, Player]:
    extension, media_type = get_media_type_from_path(path)

    if media_type == "unsupported":
        tilia.errors.display(tilia.errors.UNSUPPORTED_MEDIA_FORMAT, extension)
        return False, player

    # change player to audio or video if needed
    if player.MEDIA_TYPE != media_type:
        player = _change_player_type(player, media_type)

    success = player.load_media(path, initial_duration=initial_duration)

    return success, player


def _change_player_type(player, media_type):
    player.destroy()
    return get(Get.PLAYER_CLASS, media_type)()


def get_media_type_from_path(path: str):
    if re.match(tilia.constants.YOUTUBE_URL_REGEX, path):
        return "", "youtube"

    extension = Path(path).suffix[1:].lower()
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
