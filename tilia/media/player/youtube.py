import re
from enum import Enum
from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSlot, QObject, QTimer, QByteArray
from PyQt6.QtWebChannel import QWebChannel

import tilia.constants
import tilia.errors

from tilia.media.player import Player

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineUrlRequestInterceptor

from tilia.media.player.base import MediaTimeChangeReason
from tilia.requests import Post, post
from tilia.ui.player import PlayerToolbarElement, PlayerStatus
from tilia.ui.windows.view_window import ViewWindow


class PlayerTracker(QObject):
    def __init__(
        self,
        page,
        on_duration_available,
        set_current_time,
        set_is_playing,
        set_playback_rate,
        display_error,
    ):
        super().__init__()
        self.on_duration_available = on_duration_available
        self.set_current_time = set_current_time
        self.page = page
        self.set_is_playing = set_is_playing
        self.set_playback_rate = set_playback_rate
        self.player_toolbar_enabled = False
        self.display_error = display_error

    @pyqtSlot("float")
    def on_new_time(self, time):
        self.set_current_time(time)

    @pyqtSlot("int")
    def on_player_state_change(self, state):
        if state == self.State.UNSTARTED.value:
            post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.WAITING_FOR_YOUTUBE)
            self.page.runJavaScript("getDuration()", self.on_duration_available)
            self.player_toolbar_enabled = False
        elif state == self.State.PLAYING.value:
            if not self.player_toolbar_enabled:
                post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
                self.player_toolbar_enabled = True
            self.set_is_playing(True)
        else:
            self.set_is_playing(False)

    @pyqtSlot("float")
    def on_set_playback_rate(self, playback_rate: float):
        self.set_playback_rate(playback_rate)

    @pyqtSlot(str)
    def on_error(self, message: str) -> None:
        self.display_error(message)

    class State(Enum):
        UNSTARTED = -1
        ENDED = 0
        PLAYING = 1
        PAUSED = 2
        BUFFERING = 3
        VIDEO_CUED = 5


class UrlRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        name = QByteArray("Referer".encode())
        value = QByteArray("https://tilia-ad99d.web.app/".encode())
        info.setHttpHeader(name, value)


class YouTubePlayer(Player):
    MEDIA_TYPE = "youtube"
    PATH_TO_HTML = Path(__file__).parent / "youtube.html"

    def __init__(self):
        super().__init__()
        self._setup_web_engine()
        self._setup_web_channel()

    def _setup_web_engine(self):
        self.view = QWebEngineWindow()
        self.request_interceptor = UrlRequestInterceptor()
        self.is_web_page_loaded = False
        self.view.loadFinished.connect(self._on_web_page_load_finished)
        self.view.load(QUrl.fromLocalFile(self.PATH_TO_HTML.resolve().__str__()))

    def _setup_web_channel(self):
        self.channel = QWebChannel()
        self.shared_object = PlayerTracker(
            self.view.page(),
            self.on_media_duration_available,
            self.set_current_time,
            self.set_is_playing,
            self._engine_set_playback_rate,
            self.display_error,
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

    def set_current_time(self, time):
        self.check_seek_outside_loop(time)
        if self.check_not_loop_back(time):
            self.current_time = time
            post(
                Post.PLAYER_CURRENT_TIME_CHANGED,
                time,
                MediaTimeChangeReason.PLAYBACK,
            )

    def retry_get_duration(self):
        timer = QTimer()
        timer.singleShot(500, self._engine_get_media_duration)

    def display_error(self, message: str):
        tilia.errors.display(
            tilia.errors.YOUTUBE_PLAYER_ERROR, message + f"\nVideo ID: {self.video_id}"
        )

    @staticmethod
    def get_id_from_url(url):
        return re.match(tilia.constants.YOUTUBE_URL_REGEX, url)[6]

    def set_is_playing(self, value):
        self.is_playing = value
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_PLAY_PAUSE, value)

    def _on_web_page_load_finished(self):
        self.is_web_page_loaded = True

    def _engine_load_media(self, media_path: str) -> bool:
        self.video_id = self.get_id_from_url(media_path)

        def load_video():
            self.view.page().runJavaScript(f'loadVideo("{self.video_id}")')

        if self.is_web_page_loaded:
            load_video()
        else:
            self.view.loadFinished.connect(load_video)

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
        self.shared_object.player_toolbar_enabled = False

    def _engine_get_media_duration(self):
        self.view.page().runJavaScript(
            "getDuration()", self.on_media_duration_available
        )

    def _engine_exit(self):
        self.view.deleteLater()
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.NO_MEDIA)

    def _engine_get_current_time(self) -> float:
        return self.current_time

    def _engine_set_volume(self, volume: int) -> None:
        self.view.page().runJavaScript(f"setVolume({volume})")

    def _engine_set_mute(self, is_muted: bool) -> None:
        if is_muted:
            self.view.page().runJavaScript("mute()")
        else:
            self.view.page().runJavaScript("unMute()")

    def _engine_try_playback_rate(self, playback_rate: float) -> None:
        self.view.page().runJavaScript(f"tryPlaybackRate({playback_rate})")

    def _engine_set_playback_rate(self, playback_rate: float) -> None:
        post(
            Post.PLAYER_UI_UPDATE, PlayerToolbarElement.SPINBOX_PLAYBACK, playback_rate
        )

    def _engine_loop(self, is_looping: bool) -> None:
        self.view.page().runJavaScript(f"setLoop({1 if is_looping else 0})")


class QWebEngineWindow(ViewWindow, QWebEngineView):
    def __init__(self):
        super().__init__("TiLiA Player", menu_title="YouTube Player")
        self.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.resize(800, 600)
