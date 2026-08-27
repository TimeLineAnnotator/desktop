"""
The YouTube player can't be driven end-to-end in the suite: it needs a real
QWebEngineView, the YouTube IFrame API and a network connection. These tests
stand in a stub view for the web engine and exercise the load-outcome logic,
which is where the player decides whether a video actually loaded.
"""

import pytest
from PySide6.QtCore import QObject

from tilia.media.player.youtube import YouTubePlayer

VIDEO_ID = "aaaaaaaaaaa"
OTHER_VIDEO_ID = "bbbbbbbbbbb"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
DURATION = 120.0


class StubPage(QObject):
    """Stands in for QWebEnginePage. Replies to getLoadState() with whatever
    the test queued, so a load can be made to succeed, lag or never happen."""

    def __init__(self):
        super().__init__()
        self.scripts = []
        self.load_state = {"videoId": "", "duration": 0}

    def runJavaScript(self, script, callback=None):
        self.scripts.append(script)
        if callback is not None:
            callback(self.load_state if script == "getLoadState()" else None)

    def setWebChannel(self, channel):
        pass

    def setUrlRequestInterceptor(self, interceptor):
        pass


class StubView(QObject):
    def __init__(self):
        super().__init__()
        self._page = StubPage()
        self.visible = False

    def page(self):
        return self._page

    def isVisible(self):
        return self.visible

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


@pytest.fixture
def youtube_player(qapplication, monkeypatch, cleanup_requests):
    def setup_stub_engine(self):
        self.view = StubView()
        self.request_interceptor = None
        self.is_web_page_loaded = True

    monkeypatch.setattr(YouTubePlayer, "_setup_web_engine", setup_stub_engine)
    # 20 polls half a second apart is right in the app and far too slow here.
    monkeypatch.setattr(YouTubePlayer, "LOAD_POLL_INTERVAL", 0)
    monkeypatch.setattr(YouTubePlayer, "MAX_LOAD_ATTEMPTS", 2)

    player = YouTubePlayer()
    yield player
    player.qtimer.stop()


def run_poll_to_completion(qapplication, player):
    """Pump the event loop until the load poll stops rescheduling itself."""
    for _ in range(player.MAX_LOAD_ATTEMPTS + 3):
        qapplication.processEvents()


class TestFailedLoad:
    def test_reports_error_when_video_never_loads(
        self, qapplication, youtube_player, tilia_errors
    ):
        youtube_player.view.page().load_state = {"videoId": "", "duration": 0}

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("Could not load this video")

    def test_reports_error_when_previous_video_stays_loaded(
        self, qapplication, youtube_player, tilia_errors
    ):
        # The reported bug: loading an unplayable video over a playing one
        # leaves the previous video in place and raises nothing.
        youtube_player.view.page().load_state = {
            "videoId": OTHER_VIDEO_ID,
            "duration": DURATION,
        }

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_error()

    def test_media_is_unloaded(self, qapplication, youtube_player, tilia_errors):
        youtube_player.view.page().load_state = {
            "videoId": OTHER_VIDEO_ID,
            "duration": DURATION,
        }

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        assert not youtube_player.is_media_loaded
        assert youtube_player.duration == 0.0

    def test_keeps_media_path(self, qapplication, youtube_player, tilia_errors):
        # Clearing it would drop the URL from the file on the next save.
        youtube_player.view.page().load_state = {"videoId": "", "duration": 0}

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        assert youtube_player.media_path == URL


class TestSuccessfulLoad:
    def test_requests_the_video(self, qapplication, youtube_player):
        youtube_player.view.page().load_state = {
            "videoId": VIDEO_ID,
            "duration": DURATION,
        }

        youtube_player.load_media(URL)

        assert f'loadVideo("{VIDEO_ID}")' in youtube_player.view.page().scripts

    def test_records_duration(self, qapplication, youtube_player):
        youtube_player.view.page().load_state = {
            "videoId": VIDEO_ID,
            "duration": DURATION,
        }

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        assert youtube_player.duration == DURATION

    def test_reports_no_error(self, qapplication, youtube_player, tilia_errors):
        youtube_player.view.page().load_state = {
            "videoId": VIDEO_ID,
            "duration": DURATION,
        }

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_no_error()

    def test_slow_load_is_not_a_failure(
        self, qapplication, youtube_player, tilia_errors
    ):
        # Nothing loaded yet on the first poll, the video on the second.
        youtube_player.view.page().load_state = {"videoId": "", "duration": 0}
        youtube_player.load_media(URL)
        qapplication.processEvents()

        youtube_player.view.page().load_state = {
            "videoId": VIDEO_ID,
            "duration": DURATION,
        }
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_no_error()
        assert youtube_player.duration == DURATION


class TestStaleResults:
    def test_poll_for_a_superseded_video_is_ignored(self, youtube_player, tilia_errors):
        youtube_player.video_id = OTHER_VIDEO_ID

        youtube_player.on_load_state_available(
            {"videoId": "", "duration": 0},
            VIDEO_ID,
            youtube_player.MAX_LOAD_ATTEMPTS,
        )

        tilia_errors.assert_no_error()

    def test_duration_of_a_superseded_video_is_not_applied(self, youtube_player):
        youtube_player.video_id = OTHER_VIDEO_ID

        youtube_player.on_load_state_available(
            {"videoId": VIDEO_ID, "duration": DURATION}, VIDEO_ID, 0
        )

        assert youtube_player.duration == 0.0
