import functools
import sys
from pathlib import Path
from typing import Literal

import pytest
from PyQt6.QtWidgets import QApplication

from tests.mock import Serve
from tilia.media.player.base import MediaTimeChangeReason
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui import actions as tilia_actions_module
from tilia.app import App
from tilia.boot import setup_logic
from tilia.requests import (
    Post,
    stop_listening,
    post,
    Get,
    get,
    listen,
)
from tilia.ui.actions import TiliaAction, setup_actions
from tilia.ui.qtui import QtUI, TiliaMainWindow
from tilia.ui.cli.ui import CLI
from tilia.ui.windows import WindowKind
from tilia.requests.get import reset as reset_get
from tilia.requests.post import reset as reset_post

pytest_plugins = [
    "tests.timelines.hierarchy.fixtures",
    "tests.timelines.marker.fixtures",
    "tests.timelines.beat.fixtures",
    "tests.timelines.harmony.fixtures",
    "tests.timelines.slider.fixtures",
    "tests.timelines.audiowave.fixtures",
    "tests.timelines.pdf.fixtures",
]


class TiliaErrors:
    def __init__(self):
        listen(self, Post.DISPLAY_ERROR, self._on_display_error)
        self.errors = []

    def _on_display_error(self, title, message):
        self.errors.append({"title": title, "message": message})

    def assert_error(self):
        assert self.errors

    def assert_in_error_message(self, string: str):
        assert string in self.errors[0]["message"]

    def assert_in_error_title(self, string: str):
        assert string in self.errors[0]["title"]

    def reset(self):
        self.errors = []
        stop_listening(self, Post.DISPLAY_ERROR)


class TiliaState:
    def __init__(self, tilia: App, player):
        self.app = tilia
        self.player = player
        self.undo_manager = tilia.undo_manager
        self.file_manager = tilia.file_manager

    def reset(self):
        self.app.on_clear()
        self.duration = 100
        self.current_time = 0
        self.media_path = ""
        self._reset_undo_manager()
        self._reset_file_manager()

    def _reset_file_manager(self):
        self.file_manager.new()

    def _reset_undo_manager(self):
        self.app.reset_undo_manager()
        self.undo_manager.record(self.app.get_app_state(), "load file")

    @property
    def current_time(self):
        return self.player.current_time

    @current_time.setter
    def current_time(self, value):
        self.player.current_time = value
        post(Post.PLAYER_CURRENT_TIME_CHANGED, value, MediaTimeChangeReason.PLAYBACK)

    @property
    def duration(self):
        return get(Get.MEDIA_DURATION)

    @duration.setter
    def duration(self, value):
        self.app.set_file_media_duration(value)

    def set_duration(self, value, scale_timelines: Literal['yes', 'no', 'prompt'] = 'prompt'):
        """Use this if you want to pass scale_timelines."""
        self.app.set_file_media_duration(value, scale_timelines)

    @property
    def media_path(self):
        return get(Get.MEDIA_PATH)

    @media_path.setter
    def media_path(self, value):
        self.player.media_path = value
        post(Post.PLAYER_URL_CHANGED, value)

    @property
    def is_undo_manager_cleared(self):
        return self.undo_manager.is_cleared

    @staticmethod
    def is_window_open(ui, kind: WindowKind):
        return ui.is_window_open(kind)

    @property
    def metadata(self):
        return get(Get.MEDIA_METADATA)


@pytest.fixture(scope="session", autouse=True)
def qapplication():
    q_application = QApplication(sys.argv)
    yield q_application


@pytest.fixture
def cli():
    _cli = CLI()
    yield _cli


@pytest.fixture(autouse=True)
def tilia_state(tilia):
    state = TiliaState(tilia, tilia.player)
    yield state
    state.reset()


@pytest.fixture
def tilia_errors():
    errors = TiliaErrors()
    yield errors
    errors.reset()


@pytest.fixture()
def resources() -> Path:
    return Path(__file__).parent / "resources"


@pytest.fixture(scope="module")
def qtui(cleanup_requests, qapplication):
    mw = TiliaMainWindow()
    qtui_ = QtUI(qapplication, mw)
    stop_listening(qtui_, Post.DISPLAY_ERROR)
    yield qtui_


# noinspection PyProtectedMember
@pytest.fixture(scope="module")
def tilia(cleanup_requests):
    mw = TiliaMainWindow()
    setup_actions(mw)
    tilia_ = setup_logic(autosaver=False)
    tilia_.set_file_media_duration(100)
    tilia_.reset_undo_manager()
    yield tilia_


@pytest.fixture
def tluis(qtui, tls):
    _tluis = qtui.timeline_uis
    yield _tluis
    post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)


@pytest.fixture(scope="module")
def cleanup_requests():
    yield

    reset_get()
    reset_post()


@pytest.fixture
def tls(tilia):
    _tls = tilia.timelines

    def add_timeline_with_post(kind: TimelineKind, name: str = ""):
        kind_to_request = {
            TimelineKind.MARKER_TIMELINE: Post.TIMELINE_ADD_MARKER_TIMELINE,
            TimelineKind.HIERARCHY_TIMELINE: Post.TIMELINE_ADD_HIERARCHY_TIMELINE,
            TimelineKind.HARMONY_TIMELINE: Post.TIMELINE_ADD_HARMONY_TIMELINE,
            TimelineKind.BEAT_TIMELINE: Post.TIMELINE_ADD_BEAT_TIMELINE,
            TimelineKind.AUDIOWAVE_TIMELINE: Post.TIMELINE_ADD_AUDIOWAVE_TIMELINE,
        }
        with Serve(Get.FROM_USER_STRING, (name, True)):
            post(kind_to_request[kind])

        return _tls[-1]

    _tls.add_timeline_with_post = add_timeline_with_post
    yield _tls
    _tls.clear()  # deletes created timelines


@pytest.fixture(params=["marker", "harmony", "beat", "hierarchy", "audiowave"])
def tlui(request, marker_tlui, harmony_tlui, beat_tlui, hierarchy_tlui, audiowave_tlui):
    return {
        "marker": marker_tlui,
        "harmony": harmony_tlui,
        "beat": beat_tlui,
        "hierarchy": hierarchy_tlui,
        "audiowave": audiowave_tlui,
    }[request.param]


class ActionManager:
    def __init__(self):
        self.action_to_trigger_count = {}
        for action in tilia_actions_module.TiliaAction:
            qaction = tilia_actions_module.get_qaction(action)
            qaction.triggered.connect(
                functools.partial(self._increment_trigger_count, action)
            )

    def trigger(self, action: TiliaAction):
        tilia_actions_module.trigger(action)
        self._increment_trigger_count(action)

    def _increment_trigger_count(self, action):
        if action not in self.action_to_trigger_count:
            self.action_to_trigger_count[action] = 1
        else:
            self.action_to_trigger_count[action] += 1

    def assert_triggered(self, action):
        assert action in self.action_to_trigger_count

    def assert_not_triggered(self, action):
        assert action not in self.action_to_trigger_count


@pytest.fixture
def actions():
    action_manager = ActionManager()
    yield action_manager
