"""
The YouTube player can't be driven end-to-end in the suite: it needs a real
QWebEngineView, the YouTube IFrame API and a network connection. These tests
stand in a stub view for the web engine and exercise the load-outcome logic,
which is where the player decides whether a video actually loaded.

The stub replies to getLoadState() the way QWebEnginePage does: with a *string*.
runJavaScript hands an empty string back for any JS object, so the page can only
answer in JSON text -- a stub that replied with a dict would pass while the real
player never loaded anything.
"""

import json

import pytest
from PySide6.QtCore import QObject

from tilia.media.player.youtube import YouTubePlayer

VIDEO_ID = "aaaaaaaaaaa"
OTHER_VIDEO_ID = "bbbbbbbbbbb"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
DURATION = 120.0

# The player is up and answering, but holds no video.
NOTHING_LOADED = json.dumps({"ready": True, "videoId": "", "duration": 0})
# The page is still starting: no player object, or its API not attached yet.
PLAYER_NOT_UP = json.dumps({"ready": False, "videoId": "", "duration": 0})
# What Qt actually hands back when the page returns a JS object instead of text.
UNCONVERTIBLE_OBJECT = ""


def loaded(video_id, duration=DURATION):
    return json.dumps({"ready": True, "videoId": video_id, "duration": duration})


class StubPage(QObject):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.load_state = NOTHING_LOADED

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
        self.deregistered = False

    def page(self):
        return self._page

    def isVisible(self):
        return self.visible

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def deregister(self):
        self.deregistered = True


@pytest.fixture
def youtube_player(qapplication, monkeypatch, cleanup_requests):
    def setup_stub_engine(self):
        self.view = StubView()
        self.request_interceptor = None
        self.is_web_page_loaded = True
        self._poll_video_id = None
        self._poll_attempt = 0
        self._poll_total = 0
        self._load_failure_reported = False
        from PySide6.QtCore import QTimer

        self._load_poll_timer = QTimer(self.view)
        self._load_poll_timer.setSingleShot(True)
        self._load_poll_timer.timeout.connect(self._poll_load_state)

    monkeypatch.setattr(YouTubePlayer, "_setup_web_engine", setup_stub_engine)
    # Half a second apart is right in the app and far too slow here.
    monkeypatch.setattr(YouTubePlayer, "LOAD_POLL_INTERVAL", 0)
    monkeypatch.setattr(YouTubePlayer, "MAX_LOAD_ATTEMPTS", 2)
    monkeypatch.setattr(YouTubePlayer, "MAX_TOTAL_ATTEMPTS", 6)

    player = YouTubePlayer()
    yield player
    player._load_poll_timer.stop()
    player.qtimer.stop()


def run_poll_to_completion(qapplication, player):
    """Pump the event loop until the poll stops rescheduling itself."""
    for _ in range(player.MAX_TOTAL_ATTEMPTS + 4):
        qapplication.processEvents()


class TestPageReply:
    def test_json_text_is_understood(self, youtube_player):
        assert youtube_player._parse_load_state(loaded(VIDEO_ID)) == (
            True,
            VIDEO_ID,
            DURATION,
        )

    def test_object_reply_counts_as_not_loaded(self, youtube_player):
        # Qt converts a returned JS object to "". Treating that as a loaded
        # video with no id would fail every load, including working ones.
        assert youtube_player._parse_load_state(UNCONVERTIBLE_OBJECT) == (
            False,
            "",
            0.0,
        )

    def test_missing_reply_counts_as_not_loaded(self, youtube_player):
        assert youtube_player._parse_load_state(None) == (False, "", 0.0)

    def test_garbage_reply_counts_as_not_loaded(self, youtube_player):
        assert youtube_player._parse_load_state("not json") == (False, "", 0.0)


class TestFailedLoad:
    def test_reports_error_when_video_never_loads(
        self, qapplication, youtube_player, tilia_errors
    ):
        youtube_player.view.page().load_state = NOTHING_LOADED

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("Could not load this video")

    def test_reports_error_when_previous_video_stays_loaded(
        self, qapplication, youtube_player, tilia_errors
    ):
        # The reported bug: loading an unplayable video over a playing one
        # leaves the previous video in place and raises nothing.
        youtube_player.view.page().load_state = loaded(OTHER_VIDEO_ID)

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_error()

    def test_media_is_unloaded(self, qapplication, youtube_player, tilia_errors):
        youtube_player.view.page().load_state = loaded(OTHER_VIDEO_ID)

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        assert not youtube_player.is_media_loaded
        assert youtube_player.duration == 0.0

    def test_keeps_media_path(self, qapplication, youtube_player, tilia_errors):
        # Clearing it would drop the URL from the file on the next save.
        youtube_player.view.page().load_state = NOTHING_LOADED

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        assert youtube_player.media_path == URL

    def test_page_that_never_answers_fails_eventually(
        self, qapplication, youtube_player, tilia_errors
    ):
        youtube_player.view.page().load_state = PLAYER_NOT_UP

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_error()


class TestStartupIsNotAFailedLoad:
    def test_waiting_for_the_player_does_not_spend_the_budget(
        self, qapplication, youtube_player, tilia_errors
    ):
        # The page and the IFrame API take seconds to come up. Counting that
        # wait made a load fail before the player had answered once.
        youtube_player.view.page().load_state = PLAYER_NOT_UP

        youtube_player.load_media(URL)
        for _ in range(youtube_player.MAX_LOAD_ATTEMPTS + 1):
            qapplication.processEvents()

        tilia_errors.assert_no_error()
        assert youtube_player._load_poll_timer.isActive()

    def test_video_still_loads_after_a_slow_start(
        self, qapplication, youtube_player, tilia_errors
    ):
        youtube_player.view.page().load_state = PLAYER_NOT_UP
        youtube_player.load_media(URL)
        for _ in range(youtube_player.MAX_LOAD_ATTEMPTS + 1):
            qapplication.processEvents()

        youtube_player.view.page().load_state = loaded(VIDEO_ID)
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_no_error()
        assert youtube_player.duration == DURATION


class TestSuccessfulLoad:
    def test_requests_the_video(self, qapplication, youtube_player):
        youtube_player.view.page().load_state = loaded(VIDEO_ID)

        youtube_player.load_media(URL)

        assert f'loadVideo("{VIDEO_ID}")' in youtube_player.view.page().scripts

    def test_records_duration(self, qapplication, youtube_player):
        youtube_player.view.page().load_state = loaded(VIDEO_ID)

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        assert youtube_player.duration == DURATION

    def test_reports_no_error(self, qapplication, youtube_player, tilia_errors):
        youtube_player.view.page().load_state = loaded(VIDEO_ID)

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_no_error()

    def test_slow_load_is_not_a_failure(
        self, qapplication, youtube_player, tilia_errors
    ):
        # Nothing loaded yet on the first poll, the video on the second.
        youtube_player.view.page().load_state = NOTHING_LOADED
        youtube_player.load_media(URL)
        qapplication.processEvents()

        youtube_player.view.page().load_state = loaded(VIDEO_ID)
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_no_error()
        assert youtube_player.duration == DURATION

    def test_poll_stops_once_the_video_is_loaded(self, qapplication, youtube_player):
        youtube_player.view.page().load_state = loaded(VIDEO_ID)

        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        assert not youtube_player._load_poll_timer.isActive()


class TestOnlyOneDialogPerFailure:
    def test_youtube_error_on_a_loaded_video_is_shown(
        self, qapplication, youtube_player, tilia_errors
    ):
        youtube_player.view.page().load_state = loaded(VIDEO_ID)
        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        youtube_player.on_player_error("YouTube says no")

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("YouTube says no")

    def test_youtube_error_during_a_load_ends_it(
        self, qapplication, youtube_player, tilia_errors
    ):
        # Pressing play on a video that cannot be played makes YouTube speak
        # up before the poll has given up. That is the same failure, so it
        # takes over the poll's job instead of adding a second dialog.
        youtube_player.view.page().load_state = NOTHING_LOADED
        youtube_player.load_media(URL)
        qapplication.processEvents()

        youtube_player.on_player_error("YouTube says no")
        run_poll_to_completion(qapplication, youtube_player)

        assert len(tilia_errors.errors) == 1
        tilia_errors.assert_in_error_message("YouTube says no")
        assert not youtube_player.is_media_loaded
        assert youtube_player.media_path == URL

    def test_youtube_error_after_a_reported_failure_is_suppressed(
        self, qapplication, youtube_player, tilia_errors
    ):
        # YouTube only raises its own error for an unplayable video once
        # playback is attempted, which can be long after the poll gave up.
        youtube_player.view.page().load_state = NOTHING_LOADED
        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)
        assert len(tilia_errors.errors) == 1

        youtube_player.on_player_error("YouTube says no")

        assert len(tilia_errors.errors) == 1

    def test_a_new_load_reports_errors_again(
        self, qapplication, youtube_player, tilia_errors
    ):
        youtube_player.view.page().load_state = NOTHING_LOADED
        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        youtube_player.view.page().load_state = loaded(OTHER_VIDEO_ID)
        youtube_player.load_media(f"https://www.youtube.com/watch?v={OTHER_VIDEO_ID}")
        youtube_player.on_player_error("YouTube says no")

        tilia_errors.assert_in_error_message("Could not load this video")
        assert any("YouTube says no" in e["message"] for e in tilia_errors.errors)


class TestPollCancellation:
    def test_unloading_stops_the_poll(self, qapplication, youtube_player):
        # A poll left running against a page that is being torn down is what
        # segfaulted when a file was reopened mid-load.
        youtube_player.view.page().load_state = NOTHING_LOADED
        youtube_player.load_media(URL)
        qapplication.processEvents()

        youtube_player.unload_media()

        assert not youtube_player._load_poll_timer.isActive()
        assert youtube_player._poll_video_id is None

    def test_no_error_after_unloading(self, qapplication, youtube_player, tilia_errors):
        youtube_player.view.page().load_state = NOTHING_LOADED
        youtube_player.load_media(URL)
        qapplication.processEvents()

        youtube_player.unload_media()
        run_poll_to_completion(qapplication, youtube_player)

        tilia_errors.assert_no_error()

    def test_reply_for_a_cancelled_poll_is_ignored(self, youtube_player, tilia_errors):
        youtube_player.video_id = OTHER_VIDEO_ID

        youtube_player.on_load_state_available(NOTHING_LOADED, VIDEO_ID)

        tilia_errors.assert_no_error()

    def test_duration_of_a_superseded_video_is_not_applied(self, youtube_player):
        youtube_player.video_id = OTHER_VIDEO_ID

        youtube_player.on_load_state_available(loaded(VIDEO_ID), VIDEO_ID)

        assert youtube_player.duration == 0.0


class TestUnloadClearsTheWindow:
    def test_player_is_cleared_not_only_stopped(self, qapplication, youtube_player):
        # The window stays in the View menu after an unload, and the player
        # cannot drop a video by itself: left alone, the previous one would
        # still play from there.
        youtube_player.view.page().load_state = loaded(VIDEO_ID)
        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        youtube_player.unload_media()

        assert "clearPlayer()" in youtube_player.view.page().scripts

    def test_window_is_hidden(self, qapplication, youtube_player):
        youtube_player.view.page().load_state = loaded(VIDEO_ID)
        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        youtube_player.unload_media()

        assert not youtube_player.view.isVisible()

    def test_window_leaves_the_view_menu(self, qapplication, youtube_player):
        # The menu entry is a way back into the window; with no video loaded
        # it would only lead to a dead one.
        youtube_player.view.page().load_state = loaded(VIDEO_ID)
        youtube_player.load_media(URL)
        run_poll_to_completion(qapplication, youtube_player)

        youtube_player.unload_media()

        assert youtube_player.view.deregistered
