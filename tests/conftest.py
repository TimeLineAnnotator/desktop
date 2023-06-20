import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import tkinter as tk
import _tkinter
import traceback

import pytest

from tests.mock import PatchGet
from tilia import dirs
from tilia import settings
from tilia.boot import setup_logic
from tilia.exceptions import NoCallbackAttached
from tilia.requests import stop_listening_to_all, Get, stop_serving_all
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.collection import Timelines
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.tkinterui import TkinterUI
from tilia.ui.cli.ui import CLI
from tilia.ui.timelines.beat import BeatTimelineUI
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI, HierarchyUI
from tilia.ui.timelines.marker import MarkerTimelineUI


class EmptyObject:
    pass


@pytest.fixture(scope="session", autouse=True)
def tilia_session():
    def settings_get_patch(table, value, default_value=None):
        match table, value:
            case "dev", "dev_mode":
                return False
            case "auto-save", "interval":
                return 0
            case _:
                return original_settings_get(table, value)

    original_settings_get = settings.get
    settings.get = settings_get_patch

    dirs.setup_dirs()
    settings.load(dirs.settings_path)
    return


@pytest.fixture(scope="session")
def tk_session():
    pytest.root = tk.Tk()
    pump_events()
    yield
    if pytest.root:
        pytest.root.destroy()
        pump_events()


def pump_events():
    while pytest.root.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT):
        pass


def handle_exc(exc_type, exc_value, exc_traceback) -> None:
    """
    Tilia overrides the callback handler in tk.Tk, as reccomended, in such a way
    that unhandled errors won't immediately cause a crash. The problem is that such
    handling also prevents the error from reaching pytest, and so some tests that
    should fail, don't. This happens only when using a few tkinter functions,
    as tk.Menu.invoke
    """
    traceback.print_exc()
    raise (exc_type, exc_value)


@pytest.fixture(scope="module")
def tkui(tk_session):
    os.chdir(Path(Path(__file__).absolute().parents[1], "tilia"))
    with patch("tilia.ui.player.PlayerUI", MagicMock()):
        tkui_ = TkinterUI(pytest.root)
    tkui_.root.report_callback_exception = (
        handle_exc  # ensures exceptions will bubble up
    )
    yield tkui_
    stop_listening_to_all(tkui_.timeline_ui_collection)
    stop_serving_all(tkui_.timeline_ui_collection)
    stop_listening_to_all(tkui_)
    stop_serving_all(tkui_)


# noinspection PyProtectedMember
@pytest.fixture
def tilia(tkui):
    tilia_ = setup_logic()
    tilia_.clear_app()  # undo blank file setup
    tilia_.player.media_length = 100.0
    yield tilia_
    try:
        tilia_.clear_app()
    except AttributeError:
        # test failed and element was not created properly
        pass

    stop_listening_to_all(tilia_)
    stop_listening_to_all(tilia_.timeline_collection)
    stop_listening_to_all(tilia_.file_manager)
    stop_listening_to_all(tilia_.player)
    stop_listening_to_all(tilia_.undo_manager)
    stop_listening_to_all(tilia_.clipboard)

    stop_serving_all(tilia_)
    stop_serving_all(tilia_.timeline_collection)
    try:
        stop_serving_all(tilia_.file_manager)
    except NoCallbackAttached:
        #  file manager does its own cleanup at test_file_manager.py
        #  so it will already have called stop_serving_all
        pass
    stop_serving_all(tilia_.player)
    stop_serving_all(tilia_.undo_manager)
    stop_serving_all(tilia_.clipboard)


@pytest.fixture(scope="module")
def tluis(tkui):
    return tkui.timeline_ui_collection


@pytest.fixture()
def tls(tilia):
    _tls = tilia.timeline_collection

    def create_timeline(*args, **kwargs):
        return Timelines.create_timeline(_tls, *args, ask_user_for_name=False, **kwargs)

    _tls.create_timeline = create_timeline
    yield _tls
    _tls.clear()  # deletes created timelines


@pytest.fixture
def beat_tlui(tls, tluis) -> BeatTimelineUI:
    with PatchGet("tilia.timelines.collection", Get.BEAT_PATTERN_FROM_USER, [4]):
        tl: BeatTimeline = tls.create_timeline(TlKind.BEAT_TIMELINE)

    ui = tluis.get_timeline_ui_by_id(tl.id)

    yield ui  # will be deleted by tls


class TestHierarchyTimelineUI(HierarchyTimelineUI):
    def create_hierarchy(
        self, start: float, end: float, level: int, **kwargs
    ) -> Hierarchy:
        ...

    def relate_hierarchies(self, parent: Hierarchy, children: list[Hierarchy]):
        ...


@pytest.fixture
def hierarchy_tlui(tilia, tls, tluis) -> TestHierarchyTimelineUI:
    def create_hierarchy(
        start: float, end: float, level: int, **kwargs
    ) -> tuple[Hierarchy, HierarchyUI]:
        component = tl.create_timeline_component(
            ComponentKind.HIERARCHY, start, end, level, **kwargs
        )
        element = ui.get_element(component.id)
        return component, element

    def relate_hierarchies(parent: Hierarchy, children: list[Hierarchy]):
        return tl.component_manager._update_genealogy(parent, children)

    tl: HierarchyTimeline = tls.create_timeline(TlKind.HIERARCHY_TIMELINE)
    ui = tluis.get_timeline_ui_by_id(tl.id)

    # remove initial hierarchy
    tl.clear()

    ui.create_hierarchy = create_hierarchy
    ui.relate_hierarchies = relate_hierarchies
    return ui  # will be deleted by tls


@pytest.fixture
def hierarchy_tl(hierarchy_tlui):
    return hierarchy_tlui.timeline


@pytest.fixture
def marker_tlui(tls, tluis) -> MarkerTimelineUI:
    tl: MarkerTimeline = tls.create_timeline(TlKind.MARKER_TIMELINE)
    ui = tluis.get_timeline_ui_by_id(tl.id)

    def create_marker(*args, **kwargs):
        component = tl.create_timeline_component(ComponentKind.MARKER, *args, **kwargs)
        element = ui.get_element(component.id)
        return component, element

    tl.create_marker = create_marker
    ui.create_marker = create_marker

    yield ui  # will be deleted by tls


@pytest.fixture
def marker_tl(marker_tlui):
    tl = marker_tlui.timeline

    def create_marker(*args, **kwargs):
        return tl.create_timeline_component(ComponentKind.MARKER, *args, **kwargs)

    tl.create_marker = create_marker
    yield tl


@pytest.fixture
def cli():
    _cli = CLI()
    yield _cli
    stop_listening_to_all(_cli)
