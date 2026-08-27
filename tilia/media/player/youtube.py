import re
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, Qt, QTimer, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView

import tilia.constants
import tilia.errors
from tilia.media.player import Player
from tilia.media.player.base import MediaTimeChangeReason
from tilia.requests import Post, post
from tilia.ui.player import PlayerStatus, PlayerToolbarElement
from tilia.ui.windows.view_window import ViewWindow


class PlayerTracker(QObject):
    def __init__(
        self,
        set_current_time,
        set_is_playing,
        set_playback_rate,
        display_error,
    ):
        super().__init__()
        self.set_current_time = set_current_time
        self.set_is_playing = set_is_playing
        self.set_playback_rate = set_playback_rate
        self.player_toolbar_enabled = False
        self.display_error = display_error

    @Slot("float")
    def on_new_time(self, time):
        self.set_current_time(time)

    @Slot("int")
    def on_player_state_change(self, state):
        if state == self.State.UNSTARTED.value:
            post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.WAITING_FOR_YOUTUBE)
            self.player_toolbar_enabled = False
        elif state == self.State.PLAYING.value:
            if not self.player_toolbar_enabled:
                post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
                self.player_toolbar_enabled = True
            self.set_is_playing(True)
        else:
            self.set_is_playing(False)

    @Slot("float")
    def on_set_playback_rate(self, playback_rate: float):
        self.set_playback_rate(playback_rate)

    @Slot(str)
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
        value = QByteArray("https://tilia-app.com/".encode())
        info.setHttpHeader(name, value)


class YouTubePlayer(Player):
    MEDIA_TYPE = "youtube"
    PATH_TO_HTML = Path(__file__).parent / "youtube.html"
    LOAD_POLL_INTERVAL = 500  # ms between getLoadState() polls
    MAX_LOAD_ATTEMPTS = 20  # ~10s before a load is declared failed
    LOAD_FAILED_MESSAGE = (
        "Could not load this video. It may have been removed, made private, "
        "or the video ID may be wrong."
    )

    def __init__(self):
        super().__init__()
        self.video_id = None
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
            self.set_current_time,
            self.set_is_playing,
            self._engine_set_playback_rate,
            self.display_error,
        )
        self.channel.registerObject("backend", self.shared_object)
        self.view.page().setWebChannel(self.channel)
        self.view.page().setUrlRequestInterceptor(self.request_interceptor)

    def load_media(
        self,
        path: str | Path,
        start: float = 0.0,
        end: float = 0.0,
        initial_duration: float = 0.0,
    ):
        """
        Returns True if media loading has *started* successfully, False otherwise.
        Loading is asynchronous, and self.on_media_load_done will be called
         when it is completed.
        If initial_duration is provided, it will be available when returning.
        """
        if not self.view.isVisible():
            self.view.show()

        success = super().load_media(path, start, end)

        if initial_duration:
            # This ensures duration is available
            # after opening a file, as self.on_media_duration_available
            # will not be called immediately by the engine.
            self.on_media_duration_available(initial_duration)

        return success

    def on_media_load_done(self, path, start, end):
        self.media_path = str(path)
        self.playback_start = start

        post(
            Post.PLAYER_URL_CHANGED,
            self.media_path,
        )

        post(Post.PLAYER_CURRENT_TIME_CHANGED, 0.0, MediaTimeChangeReason.LOAD)

        self.is_media_loaded = True

    def on_media_duration_available(self, duration, requested_video_id=None):
        # requested_video_id is the video this query was issued for; if a
        # different video has loaded by the time the JS round-trip resolves
        # (e.g. the user opened another YouTube-backed file), this result
        # is stale and must not be applied.
        if requested_video_id is not None and requested_video_id != self.video_id:
            return
        if duration == self.duration:
            return

        super().on_media_duration_available(duration)

    def on_load_state_available(
        self, state: dict | None, requested_video_id: str, attempt: int
    ) -> None:
        """
        Called with the result of each getLoadState() poll started by
        _engine_load_media. The poll ends when the player reports the
        requested video with a duration, or when we give up on it.
        """
        if requested_video_id != self.video_id:
            # Another video was requested while this round-trip was in
            # flight; that request runs its own poll.
            return

        loaded_video_id = (state or {}).get("videoId", "")
        duration = (state or {}).get("duration", 0)

        if loaded_video_id == requested_video_id and duration:
            self.on_media_duration_available(duration, requested_video_id)
            return

        if attempt >= self.MAX_LOAD_ATTEMPTS:
            self.on_media_load_failed()
            return

        self.retry_get_duration(requested_video_id, attempt + 1)

    def on_media_load_failed(self) -> None:
        """
        The requested video never became the loaded video. YouTube reports
        some failures through onError, but not all of them: loading an
        unplayable video over an already playing one leaves the previous
        video in place without raising anything, so the load has to be
        checked rather than assumed.
        """
        self.display_error(self.LOAD_FAILED_MESSAGE)
        # media_path is what the file declares, and it stays the file's
        # media path even though it could not be loaded. Clearing it here
        # would drop the URL from the file on the next save.
        media_path = self.media_path
        self.unload_media()
        self.media_path = media_path

    def set_current_time(self, time):
        self.check_seek_outside_loop(time)
        if self.check_not_loop_back(time):
            self.current_time = time
            post(
                Post.PLAYER_CURRENT_TIME_CHANGED,
                time,
                MediaTimeChangeReason.PLAYBACK,
            )

    def retry_get_duration(self, requested_video_id: str, attempt: int = 0):
        QTimer.singleShot(
            self.LOAD_POLL_INTERVAL,
            self.view,
            lambda: self._engine_get_media_duration(requested_video_id, attempt),
        )

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
            requested_video_id = self.video_id
            self.view.page().runJavaScript(f'loadVideo("{requested_video_id}")')
            # Loading is fire-and-forget on the JS side, so poll until the
            # player reports this video as the loaded one. Without this a
            # failed load is indistinguishable from a slow one, and the
            # previously loaded video keeps playing unnoticed.
            self.retry_get_duration(requested_video_id)

        if self.is_web_page_loaded:
            load_video()
        else:
            # SingleShot: a plain connect would leave load_video attached
            # and re-run it -- and re-start its poll -- on every later page
            # load, which can report the same failure more than once.
            self.view.loadFinished.connect(
                load_video, Qt.ConnectionType.SingleShotConnection
            )

        return True

    def _play_loop(self) -> None:
        pass

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
        if self.is_web_page_loaded:
            self.view.page().runJavaScript("stop()")
        self.view.hide()
        self.video_id = None
        self.shared_object.player_toolbar_enabled = False

    def _engine_get_media_duration(self, requested_video_id: str, attempt: int = 0):
        self.view.page().runJavaScript(
            "getLoadState()",
            lambda state: self.on_load_state_available(
                state, requested_video_id, attempt
            ),
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
