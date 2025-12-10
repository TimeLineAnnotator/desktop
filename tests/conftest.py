import functools
import sys
from pathlib import Path
from typing import Literal

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from colorama import Fore, Style

from tilia.utils import load_dotenv

load_dotenv()

import tilia.constants as constants_module
import tilia.log as logging_module
import tilia.settings as settings_module
from tilia.media.player.base import MediaTimeChangeReason
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

try:
    # icecream is a replacement for print()
    # Not required, but very useful for debugging.
    # Docs: https://github.com/gruns/icecream
    import icecream

    icecream.install()
except ImportError:
    pass

pytest_plugins = [
    "tests.timelines.hierarchy.fixtures",
    "tests.timelines.marker.fixtures",
    "tests.timelines.beat.fixtures",
    "tests.timelines.harmony.fixtures",
    "tests.timelines.slider.fixtures",
    "tests.timelines.audiowave.fixtures",
    "tests.timelines.pdf.fixtures",
    "tests.timelines.score.fixtures",
]


class TiliaErrors:
    def __init__(self):
        listen(self, Post.DISPLAY_ERROR, self._on_display_error)
        self.errors = []

    def _on_display_error(self, title, message):
        self.errors.append({"title": title, "message": message})

    def assert_error(self):
        assert self.errors

    def assert_no_error(self):
        assert not self.errors

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
        post(Post.REQUEST_CLEAR_UI)

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

    def set_duration(
        self, value, scale_timelines: Literal["yes", "no", "prompt"] = "prompt"
    ):
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


@pytest.fixture(autouse=True)
def print_errors():
    """
    Prints "errors" that would be displayed by the QtUI.
    Without this we may miss unexpected failure messages,
    since they  do not raise unhandled exceptions.
    """

    def _print_errors(title, message):
        print(Fore.YELLOW)
        print()
        print("############## TILIA ERROR MESSAGE ############## ")
        print(title)
        print(message)
        print("############################## ")
        print()
        print(Style.RESET_ALL)

    listen(print_errors, Post.DISPLAY_ERROR, _print_errors)


@pytest.fixture()
def resources() -> Path:
    return Path(__file__).parent / "resources"


@pytest.fixture(scope="module")
def use_test_settings(qapplication):
    settings_module.settings._settings = QSettings(
        constants_module.APP_NAME, "DesktopTests"
    )
    settings_module.settings._check_all_default_settings_present()
    settings_module.settings.set("general", "prioritise_performance", True)
    yield


@pytest.fixture(scope="module")
def use_test_logger(qapplication):
    logging_module.sentry_sdk.integrations.logging.ignore_logger(
        logging_module.logger.name
    )
    yield


@pytest.fixture(scope="module")
def qtui(tilia, cleanup_requests, qapplication, use_test_settings, use_test_logger):
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

    yield _tls
    _tls.clear()  # deletes created timelines


@pytest.fixture(params=["marker", "harmony", "beat", "hierarchy", "audiowave", "score"])
def tlui(
    request,
    marker_tlui,
    harmony_tlui,
    beat_tlui,
    hierarchy_tlui,
    audiowave_tlui,
    score_tlui,
):
    return {
        "marker": marker_tlui,
        "harmony": harmony_tlui,
        "beat": beat_tlui,
        "hierarchy": hierarchy_tlui,
        "audiowave": audiowave_tlui,
        "score": score_tlui,
    }[request.param]


class UserActionManager:
    """
    Class to simulate and mock user interaction with the GUI.
    """

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
def user_actions():
    """
    Fixture to simulate and mock user interaction with the GUI.
    This should be used with the <kind>_tlui fixtures
    and NOT with <kind>_tl fixtures, as the latter do not
    create corresponding TimelineUIS. Tests with <kind>_tl
    may still pass if they use this fixture, provided they do
    not require a TimelineUI.
    """
    action_manager = UserActionManager()
    yield action_manager


def parametrize_tl(func):
    """Adds a parameter 'tl' to a test that receives the name of a fixture that returns a component.
    To get the timeline from within the test, add the `request` fixture to its arguments and
    run `request.getfixturevalue('tl')`"""

    @pytest.mark.parametrize(
        "tl",
        [
            "audiowave_tl",
            "beat_tl",
            "harmony_tl",
            "hierarchy_tl",
            "marker_tl",
            "pdf_tl",
            "score_tl",
            "slider_tl",
        ],
    )
    @functools.wraps(func)  # Preserve original function metadata
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def parametrize_tlui(func):
    """Adds a parameter 'tlui' to a test that receives the name of a fixture that returns a component.
    To get the timeline ui from within the test, add the `request` fixture to its arguments and
    run `request.getfixturevalue('tlui')`"""

    @pytest.mark.parametrize(
        "tlui",
        [
            "audiowave_tlui",
            "beat_tlui",
            "harmony_tlui",
            "hierarchy_tlui",
            "marker_tlui",
            "pdf_tlui",
            "score_tlui",
            "slider_tlui",
        ],
    )
    @functools.wraps(func)  # Preserve original function metadata
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def parametrize_component(func):
    """Adds a parameter 'comp' to a test that receives the name of a fixture that returns a component.
    To get the component from within the test, add the `request` fixture to its arguments and
    run `request.getfixturevalue('comp')`"""

    @pytest.mark.parametrize(
        "comp", ["amplitudebar", "beat", "harmony", "hierarchy", "marker", "pdf_marker"]
    )
    @functools.wraps(func)  # Preserve original function metadata
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def parametrize_ui_element(func):
    """Adds a parameter 'comp' to a test that receives the name of a fixture that returns a ui element.
    To get the element from within the test, add the `request` fixture to its arguments and
    run `request.getfixturevalue('element')`.
    Tests that use this must also request the `tluis` fixture, or another fixture that requires it.
    """

    @pytest.mark.parametrize(
        "element",
        [
            "amplitudebar_ui",
            "beat_ui",
            "harmony_ui",
            "hierarchy_ui",
            "marker_ui",
            "pdf_marker_ui",
        ],
    )
    @functools.wraps(func)  # Preserve original function metadata
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper
