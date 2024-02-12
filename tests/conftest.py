import functools

import pytest

from tilia.media.player.base import MediaTimeChangeReason
from tilia.ui import actions as tilia_actions_module
from tilia.app import App
from tilia.boot import setup_logic
from tilia.exceptions import NoCallbackAttached
from tilia.requests import stop_listening_to_all, stop_serving_all, Post, stop_listening, post, Get, get
from tilia.ui.actions import TiliaAction
from tilia.ui.qtui import QtUI
from tilia.ui.cli.ui import CLI


pytest_plugins = [
    "tests.timelines.hierarchy.fixtures",
    "tests.timelines.marker.fixtures",
    "tests.timelines.beat.fixtures",
    "tests.timelines.harmony.fixtures",
]


class TiliaState:
    def __init__(self, tilia: App):
        self.app = tilia
        self.player = tilia.player
        self.undo_manager = tilia.undo_manager

    def reset(self):
        self.app.duration = 100
        self.player.current_time = 0
        self.player.media_path = ''
        self._reset_undo_manager()

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
        self.app.set_media_duration(value)

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


@pytest.fixture
def tilia_state(tilia):
    state = TiliaState(tilia)
    yield state
    state.reset()


@pytest.fixture(scope="session")
def qtui():
    qtui_ = QtUI()
    stop_listening(qtui_, Post.DISPLAY_ERROR)
    yield qtui_
    # stop_listening_to_all(qtui_.timeline_uis)
    # stop_serving_all(qtui_.timeline_uis)
    # stop_listening_to_all(qtui_)
    # stop_serving_all(qtui_)


# noinspection PyProtectedMember
@pytest.fixture(scope="session")
def tilia(qtui):
    tilia_ = setup_logic(autosaver=False)
    tilia_.player = qtui.player
    tilia_.set_media_duration(100)
    yield tilia_
    # try:
    #     tilia_.on_clear()
    # except AttributeError:
    #     # test failed and element was not created properly
    #     pass
    #
    # stop_listening_to_all(tilia_)
    # stop_listening_to_all(tilia_.timelines)
    # stop_listening_to_all(tilia_.file_manager)
    # stop_listening_to_all(tilia_.player)
    # stop_listening_to_all(tilia_.undo_manager)
    # stop_listening_to_all(tilia_.clipboard)
    #
    # stop_serving_all(tilia_)
    # stop_serving_all(tilia_.timelines)
    # try:
    #     stop_serving_all(tilia_.file_manager)
    # except NoCallbackAttached:
    #     #  file manager does its own cleanup at test_file_manager.py
    #     #  so it will already have called stop_serving_all
    #     pass
    # stop_serving_all(tilia_.player)
    # stop_serving_all(tilia_.undo_manager)
    # stop_serving_all(tilia_.clipboard)


@pytest.fixture
def tluis(qtui):
    _tluis = qtui.timeline_uis
    yield _tluis
    _tluis._setup_auto_scroll()
    _tluis._setup_drag_tracking_vars()
    _tluis._setup_selection_box()


@pytest.fixture
def tls(tilia):
    _tls = tilia.timelines
    yield _tls
    _tls.clear()  # deletes created timelines


@pytest.fixture
def cli():
    _cli = CLI()
    yield _cli
    stop_listening_to_all(_cli)


class ActionManager:
    def __init__(self):
        self.action_to_trigger_count = {}
        for action in tilia_actions_module.TiliaAction:
            qaction = tilia_actions_module.get_qaction(action)
            qaction.triggered.connect(functools.partial(self._increment_trigger_count, action))

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
def actions(qtui):
    action_manager = ActionManager()
    yield action_manager
