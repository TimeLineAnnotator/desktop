import json
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
    MAX_LOAD_ATTEMPTS = 6  # ~3s of an answering player before a load fails
    MAX_TOTAL_ATTEMPTS = 40  # ~20s before giving up on a page that never answers
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
        # One owned timer rather than a chain of singleShots: the poll has to
        # be cancellable, or it keeps querying a page that is being torn down.
        self._poll_video_id = None
        self._poll_attempt = 0
        self._poll_total = 0
        self._load_failure_reported = False
        self._load_poll_timer = QTimer(self.view)
        self._load_poll_timer.setSingleShot(True)
        self._load_poll_timer.timeout.connect(self._poll_load_state)
        self.view.loadFinished.connect(self._on_web_page_load_finished)
        self.view.load(QUrl.fromLocalFile(self.PATH_TO_HTML.resolve().__str__()))

    def _setup_web_channel(self):
        self.channel = QWebChannel()
        self.shared_object = PlayerTracker(
            self.set_current_time,
            self.set_is_playing,
            self._engine_set_playback_rate,
            self.on_player_error,
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
        self, state: str | None, requested_video_id: str
    ) -> None:
        """
        Called with the result of one getLoadState() poll. The poll ends when
        the player reports the requested video with a duration, or when we
        give up on it.
        """
        if (
            requested_video_id != self.video_id
            or requested_video_id != self._poll_video_id
        ):
            # Superseded by another load, or cancelled by an unload while this
            # round-trip was in flight. Reaching into the page or the window
            # from here would touch a player that is being torn down.
            return

        is_answering, loaded_video_id, duration = self._parse_load_state(state)

        if loaded_video_id == requested_video_id and duration:
            self._stop_load_poll()
            self.on_media_duration_available(duration, requested_video_id)
            return

        self._poll_total += 1
        if is_answering:
            # Attempts only count once the player answers at all. Waiting for
            # the page and the IFrame API to come up is startup, and counting
            # it made every load spend the whole budget before failing.
            self._poll_attempt += 1

        if (
            self._poll_attempt >= self.MAX_LOAD_ATTEMPTS
            or self._poll_total >= self.MAX_TOTAL_ATTEMPTS
        ):
            self._stop_load_poll()
            # Leave this callback before reporting: display_error opens a modal
            # dialog and unload_media calls back into the page, neither of which
            # is safe from inside a runJavaScript result callback.
            QTimer.singleShot(0, self.view, self.on_media_load_failed)
            return

        self._load_poll_timer.start(self.LOAD_POLL_INTERVAL)

    @staticmethod
    def _parse_load_state(state: str | None) -> tuple[bool, str, float]:
        """
        getLoadState() replies with JSON text -- runJavaScript hands back an
        empty string for a JS object, so only scalars cross the bridge. An
        empty or malformed reply means the page could not answer, which counts
        as "not loaded yet".

        The first element says whether the player answered the query at all,
        as opposed to not being up yet.
        """
        try:
            parsed = json.loads(state)
        except (TypeError, ValueError):
            return False, "", 0.0
        if not isinstance(parsed, dict):
            return False, "", 0.0
        return (
            bool(parsed.get("ready")),
            parsed.get("videoId") or "",
            parsed.get("duration") or 0.0,
        )

    def on_media_load_failed(self, message: str | None = None) -> None:
        """
        The requested video never became the loaded video. YouTube reports
        some failures through onError, but not all of them: loading an
        unplayable video over an already playing one leaves the previous
        video in place without raising anything, so the load has to be
        checked rather than assumed.
        """
        self._load_failure_reported = True
        self.display_error(message or self.LOAD_FAILED_MESSAGE)
        # media_path is what the file declares, and it stays the file's
        # media path even though it could not be loaded. Clearing it here
        # would drop the URL from the file on the next save.
        media_path = self.media_path
        self.unload_media()
        self.media_path = media_path

    def on_player_error(self, message: str) -> None:
        """
        An error reported by YouTube itself. For a video that cannot be
        played, YouTube stays quiet until playback is attempted, which can
        fall on either side of the load poll giving up. Either way it is one
        failure, so whichever notices first reports it and the other is
        dropped.
        """
        if self._load_failure_reported:
            return

        if self._poll_video_id is not None:
            # The video still being polled for is the one YouTube is
            # complaining about: this is that load failing, reported early
            # and with YouTube's own reason instead of the generic one.
            self._stop_load_poll()
            self.on_media_load_failed(message)
            return

        self.display_error(message)

    def set_current_time(self, time):
        self.check_seek_outside_loop(time)
        if self.check_not_loop_back(time):
            self.current_time = time
            post(
                Post.PLAYER_CURRENT_TIME_CHANGED,
                time,
                MediaTimeChangeReason.PLAYBACK,
            )

    def _start_load_poll(self, video_id: str) -> None:
        self._poll_video_id = video_id
        self._poll_attempt = 0
        self._poll_total = 0
        self._load_poll_timer.start(self.LOAD_POLL_INTERVAL)

    def _stop_load_poll(self) -> None:
        self._poll_video_id = None
        self._load_poll_timer.stop()

    def _poll_load_state(self) -> None:
        requested_video_id = self._poll_video_id
        if requested_video_id is None or requested_video_id != self.video_id:
            self._stop_load_poll()
            return
        self.view.page().runJavaScript(
            "getLoadState()",
            lambda state: self.on_load_state_available(state, requested_video_id),
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
            self._load_failure_reported = False
            self._start_load_poll(requested_video_id)

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
        self._stop_load_poll()
        if self.is_web_page_loaded:
            self.view.page().runJavaScript("clearPlayer()")
        self.view.hide()
        # The View menu is the way back into the window. With no video loaded
        # there is nothing to go back to, so drop the entry until the next
        # load shows the window again.
        self.view.deregister()
        self.video_id = None
        self.shared_object.player_toolbar_enabled = False

    def _engine_get_media_duration(self):
        self._poll_load_state()

    def _engine_exit(self):
        self._stop_load_poll()
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
