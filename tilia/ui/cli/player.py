from pytube import YouTube
from tilia.media.player.qtplayer import QtPlayer
from tilia.requests import post, Post


class CLIVideoPlayer(QtPlayer):
    # inherits only from QtPlayer to prevent
    # the creation of a video widget
    pass


class CLIYoutubePlayer:
    MEDIA_TYPE = "youtube"

    def load_media(self, media_path: str, start: float = 0.0, end: float = 0.0):
        try:
            youtube = YouTube(media_path)
            post(Post.FILE_MEDIA_DURATION_CHANGED, youtube.length)
        except:
            post(
                Post.DISPLAY_ERROR,
                'Failed to get YouTube video duration. Please set the duration with "metadata set-media-length"',
            )

    def destroy(self):
        pass
