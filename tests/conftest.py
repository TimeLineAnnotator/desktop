import pytest

from tilia.app import App
from tilia.boot import setup_logic
from tilia.exceptions import NoCallbackAttached
from tilia.requests import stop_listening_to_all, stop_serving_all, Post, stop_listening
from tilia.ui.qtui import QtUI
from tilia.ui.cli.ui import CLI

pytest_plugins = [
    "tests.timelines.hierarchy.fixtures",
    "tests.timelines.marker.fixtures",
    "tests.timelines.beat.fixtures",
    "tests.timelines.harmony.fixtures",
]


@pytest.fixture(scope="module")
def qtui():
    qtui_ = QtUI()
    stop_listening(qtui_, Post.DISPLAY_ERROR)
    yield qtui_
    stop_listening_to_all(qtui_.timeline_uis)
    stop_serving_all(qtui_.timeline_uis)
    stop_listening_to_all(qtui_)
    stop_serving_all(qtui_)


class TiliaState:
    def __init__(self, tilia: App):
        self.player = tilia.player

    def reset(self):
        self.player.duration = 100
        self.player.current_time = 0

    def set_current_time(self, value):
        self.player.current_time = value

    def set_duration(self, value):
        self.player.duration = value


@pytest.fixture
def tilia_state(tilia):
    state = TiliaState(tilia)
    yield state
    state.reset()


# noinspection PyProtectedMember
@pytest.fixture(scope="module")
def tilia(qtui):
    tilia_ = setup_logic(autosaver=False)
    tilia_.player = qtui.player
    tilia_.player.duration = 100
    yield tilia_
    try:
        tilia_.on_clear()
    except AttributeError:
        # test failed and element was not created properly
        pass

    stop_listening_to_all(tilia_)
    stop_listening_to_all(tilia_.timelines)
    stop_listening_to_all(tilia_.file_manager)
    stop_listening_to_all(tilia_.player)
    stop_listening_to_all(tilia_.undo_manager)
    stop_listening_to_all(tilia_.clipboard)

    stop_serving_all(tilia_)
    stop_serving_all(tilia_.timelines)
    try:
        stop_serving_all(tilia_.file_manager)
    except NoCallbackAttached:
        #  file manager does its own cleanup at test_file_manager.py
        #  so it will already have called stop_serving_all
        pass
    stop_serving_all(tilia_.player)
    stop_serving_all(tilia_.undo_manager)
    stop_serving_all(tilia_.clipboard)


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
