
import functools
import re
from enum import Enum
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSlot, QObject, QTimer, QByteArray
from PyQt6.QtWebChannel import QWebChannel

import tilia.constants

from tilia.media.player import Player

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineUrlRequestInterceptor

from tilia.media.player.base import MediaTimeChangeReason
from tilia.requests import Post, post


class PlayerTracker(QObject):
    def __init__(self, page, on_duration_available, set_current_time, set_is_playing):
        super().__init__()
        self.on_duration_available = on_duration_available
        self.set_current_time = set_current_time
        self.page = page
        self.set_is_playing = set_is_playing

    @pyqtSlot("float")
    def on_new_time(self, time):
        self.set_current_time(time)
        post(
            Post.PLAYER_CURRENT_TIME_CHANGED,
            time,
            MediaTimeChangeReason.PLAYBACK,
        )

    @pyqtSlot("int")
    def on_player_state_change(self, state):
        if state == self.State.UNSTARTED.value:
            self.page.runJavaScript("getDuration()", self.on_duration_available)
        elif state == self.State.PLAYING.value:
            post(Post.PLAYER_ENABLE_CONTROLS)
            self.set_is_playing(True)
        else:
            self.set_is_playing(False)

    class State(Enum):
        UNSTARTED = -1
        ENDED = 0
        PLAYING = 1
        PAUSED = 2
        BUFFERING = 3
        VIDEO_CUED = 5


class UrlRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        name = QByteArray('Referer'.encode())
        value = QByteArray('https://tilia-ad99d.web.app/'.encode())
        info.setHttpHeader(name, value)


class YouTubePlayer(Player):
    MEDIA_TYPE = "youtube"
    PATH_TO_HTML = Path(__file__).parent / "youtube.html"

    def __init__(self):
        super().__init__()
        self._setup_web_engine()
        self._setup_web_channel()

    def _setup_web_engine(self):
        self.view = QWebEngineView()
        self.view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.request_interceptor = UrlRequestInterceptor()
        self.is_web_page_loaded = False
        self.view.loadFinished.connect(self._on_web_page_load_finished)
        self.view.load(QUrl.fromLocalFile(self.PATH_TO_HTML.resolve().__str__()))

        self.view.setWindowTitle("TiLiA Player")
        self.view.resize(800, 600)
        self.view.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.CustomizeWindowHint
        )
        self.view.show()

    def _setup_web_channel(self):
        self.channel = QWebChannel()
        self.shared_object = PlayerTracker(
            self.view.page(),
            self.on_media_duration_available,
            functools.partial(setattr, self, "current_time"),
            self.set_is_playing,
        )
        self.channel.registerObject("backend", self.shared_object)
        self.view.page().setWebChannel(self.channel)
        self.view.page().setUrlRequestInterceptor(self.request_interceptor)

    def load_media(self, path: str | Path, start: float = 0.0, end: float = 0.0):
        if not self.view.isVisible():
            self.view.show()

        super().load_media(path, start, end)

    def on_media_load_done(self, path, start, end):
        self.media_path = str(path)
        self.playback_start = start

        post(
            Post.PLAYER_URL_CHANGED,
            self.media_path,
        )

        post(Post.PLAYER_CURRENT_TIME_CHANGED, 0.0, MediaTimeChangeReason.LOAD)

        self.is_media_loaded = True

    def on_media_duration_available(self, duration):
        if duration == self.duration:
            return
        if not duration:
            return self.retry_get_duration()

        super().on_media_duration_available(duration)

    def retry_get_duration(self):
        timer = QTimer()
        timer.singleShot(500, self._engine_get_media_duration)

    @staticmethod
    def get_id_from_url(url):
        return re.match(tilia.constants.YOUTUBE_URL_REGEX, url)[6]

    def set_is_playing(self, value):
        self.is_playing = value

    def _on_web_page_load_finished(self):
        self.is_web_page_loaded = True

    def _engine_load_media(self, media_path: str) -> bool:
        video_id = self.get_id_from_url(media_path)

        def load_video():
            self.view.page().runJavaScript(f'loadVideo("{video_id}")')

        if self.is_web_page_loaded:
            load_video()
        else:
            self.view.loadFinished.connect(load_video)

        post(Post.PLAYER_DISABLE_CONTROLS)  # first play command must be given via YT ui
        return True

    def _play_loop(self) -> None:
        def post_time_change_event(time):
            post(
                Post.PLAYER_CURRENT_TIME_CHANGED,
                time,
                MediaTimeChangeReason.PLAYBACK,
            )

        self.view.page().runJavaScript("getCurrentTime()", post_time_change_event)

    def _engine_seek(self, time: float) -> None:
        if not self.is_media_loaded:
            return

        self.view.page().runJavaScript(f"seekTo({time})")

    def _engine_play(self) -> None:
        self.view.page().runJavaScript("play()")

    def _engine_pause(self):
        self.view.page().runJavaScript("pause()")

    def _engine_unpause(self):
        self.view.page().runJavaScript("play()")

    def _engine_stop(self):
        self.view.page().runJavaScript("pause()")
        self._engine_seek(0)

    def _engine_unload_media(self):
        self.view.hide()

    def _engine_get_media_duration(self):
        self.view.page().runJavaScript(
            "getDuration()", self.on_media_duration_available
        )

    def _engine_exit(self):
        del self.view
        post(Post.PLAYER_ENABLE_CONTROLS)

    def _engine_get_current_time(self) -> float:
        return self.current_time
