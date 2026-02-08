import base64
import urllib.parse
from os import environ

import httpx
import isodate

from tilia.media.player import Player
from tilia.media.player.qtplayer import QtPlayer
from tilia.requests import post, Post


class CLIVideoPlayer(QtPlayer):
    # inherits only from QtPlayer to prevent
    # the creation of a video widget
    pass


class CLIYoutubePlayer(Player):
    MEDIA_TYPE = "youtube"
    INVALID_YOUTUBE_URL = "Invalid YouTube URL: {}"

    def __init__(self):
        super().__init__()

    def load_media(
        self,
        media_path: str,
        start: float = 0.0,
        end: float = 0.0,
        initial_duration: float = False,
    ):
        try:
            query_params = urllib.parse.urlparse(media_path).query
            video_id = urllib.parse.parse_qs(query_params)["v"][0]
        except (KeyError, IndexError):
            post(
                Post.DISPLAY_ERROR,
                "Load media error",
                self.INVALID_YOUTUBE_URL.format(media_path),
            )
            return False

        success, result = self.get_youtube_duration(video_id)
        if not success:
            post(
                Post.DISPLAY_ERROR,
                "Load media error",
                "Could not get YouTube video duration: " + result,
            )
            return False

        self.on_media_duration_available(result)
        self.on_media_load_done(media_path, 0.0, result)
        return True

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

    CONNECTION_ERROR_MESSAGE = (
        "Could not reach YouTube. Check your internet connection."
    )
    REQUEST_FAILED_MESSAGE = "Request failed with status code: {}."
    DECODE_ERROR_MESSAGE = "Could not decode YouTube response."
    VIDEO_NOT_FOUND_MESSAGE = "No video with ID='{}'."
    DURATION_NOT_AVAILABLE_MESSAGE = "Could not get duration from YouTube response."

    @staticmethod
    def get_api_key():
        if environ.get("YOUTUBE_API_KEY"):
            return environ["YOUTUBE_API_KEY"]

        encoded_url = (
            "aHR0cHM6Ly90aWxpYS1hcGkuZmx5LmRldi9hcGkvdjEvcHJveHkveXQtYXBpLWtleS8="
        )
        try:
            key = httpx.get(base64.b64decode(encoded_url).decode(), timeout=5).json()[
                "key"
            ]
        except (httpx.RequestError, KeyError):
            return None
        return key

    def get_youtube_duration(self, id: str) -> tuple[bool, str | float]:
        """
        Gets the duration of a YouTube video using the YouTube Data API v3.
        Returns a tuple of (success: bool, duration: float | str).

        We use our server as a proxy to store the API key.
        """

        key = self.get_api_key()
        if not key:
            return False, self.REQUEST_FAILED_MESSAGE

        params = {
            "id": id,
            "key": key,
            "part": "contentDetails",
            "fields": "items(contentDetails(duration))",
        }

        try:
            response = httpx.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params=params,
                timeout=5,
            )
        except httpx.RequestError:
            return False, self.CONNECTION_ERROR_MESSAGE

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            return False, self.REQUEST_FAILED_MESSAGE.format(response.status_code)

        try:
            response_json = response.json()
        except httpx.DecodingError:
            return False, self.DECODE_ERROR_MESSAGE

        try:
            duration = response_json["items"][0]["contentDetails"]["duration"]
        except IndexError:
            return False, self.VIDEO_NOT_FOUND_MESSAGE.format(id)

        except KeyError:
            return False, self.DURATION_NOT_AVAILABLE_MESSAGE

        return True, isodate.parse_duration(duration).total_seconds()
