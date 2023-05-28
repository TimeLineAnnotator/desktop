import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from tilia import dirs

from tilia import settings
import tkinter as tk
import _tkinter

from tilia.events import unsubscribe_from_all
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.timelines.beat import BeatTimelineUI
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI, HierarchyUI
from tilia.ui.timelines.marker import MarkerTimelineUI


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


@pytest.fixture(scope="module")
def tkui(tk_session):
    from tilia.ui.tkinterui import TkinterUI

    os.chdir(Path(Path(__file__).absolute().parents[1], "tilia"))
    with patch("tilia.ui.player.PlayerUI", MagicMock()):
        tkui_ = TkinterUI(pytest.root)
    yield tkui_
    unsubscribe_from_all(tkui_.timeline_ui_collection)
    unsubscribe_from_all(tkui_)


# noinspection PyProtectedMember
@pytest.fixture(scope="module")
def tilia(tkui):
    os.chdir(Path(Path(__file__).absolute().parents[1], "tilia"))
    from tilia._tilia import TiLiA

    tilia_ = TiLiA(tkui)
    tilia_.clear_app()  # undo blank file setup
    tilia_._player.media_length = 100.0
    yield tilia_
    try:
        tilia_.clear_app()
    except AttributeError:
        # test failed and element was not created properly
        pass
    unsubscribe_from_all(tilia_)
    unsubscribe_from_all(tilia_._timeline_collection)
    unsubscribe_from_all(tilia_._timeline_ui_collection)
    unsubscribe_from_all(tilia_._file_manager)
    unsubscribe_from_all(tilia_._player)
    unsubscribe_from_all(tilia_._undo_manager)
    unsubscribe_from_all(tilia_._clipboard)


@pytest.fixture(scope="module")
def tlui_clct(tkui, tilia):
    return tilia._timeline_ui_collection


@pytest.fixture(scope="module")
def tl_clct(tkui, tilia):
    return tilia._timeline_collection


## FIXTURES FOR CREATING TIMELINES


@pytest.fixture
def beat_tlui(tl_clct, tlui_clct) -> BeatTimelineUI:
    with patch(
        "tilia.ui.timelines.collection.TimelineUICollection.ask_beat_pattern"
    ) as mock:
        mock.return_value = [4]
        tl: BeatTimeline = tl_clct.create_timeline(TlKind.BEAT_TIMELINE)

    ui = tlui_clct.get_timeline_ui_by_id(tl.id)

    yield ui
    tl_clct.delete_timeline(tl)


class TestHierarchyTimelineUI(HierarchyTimelineUI):
    def create_hierarchy(
        self, start: float, end: float, level: int, **kwargs
    ) -> Hierarchy:
        ...

    def relate_hierarchies(self, parent: Hierarchy, children: list[Hierarchy]):
        ...


@pytest.fixture
def hierarchy_tlui(tilia, tl_clct, tlui_clct) -> TestHierarchyTimelineUI:
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

    tl: HierarchyTimeline = tl_clct.create_timeline(TlKind.HIERARCHY_TIMELINE)
    ui = tlui_clct.get_timeline_ui_by_id(tl.id)

    # remove initial hierarchy
    tl.clear()

    ui.create_hierarchy = create_hierarchy
    ui.relate_hierarchies = relate_hierarchies
    yield ui
    tl_clct.delete_timeline(tl)
    tilia._undo_manager.clear()


@pytest.fixture
def hierarchy_tl(hierarchy_tlui):
    return hierarchy_tlui.timeline


@pytest.fixture
def marker_tlui(tl_clct, tlui_clct) -> MarkerTimelineUI:
    tl: MarkerTimeline = tl_clct.create_timeline(TlKind.MARKER_TIMELINE)
    ui = tlui_clct.get_timeline_ui_by_id(tl.id)

    def create_marker(*args, **kwargs):
        component = tl.create_timeline_component(ComponentKind.MARKER, *args, **kwargs)
        element = ui.get_element(component.id)
        return component, element

    tl.create_marker = create_marker
    ui.create_marker = create_marker

    yield ui
    tl_clct.delete_timeline(tl)


@pytest.fixture
def marker_tl(marker_tlui):
    tl = marker_tlui.timeline

    def create_marker(*args, **kwargs):
        return tl.create_timeline_component(ComponentKind.MARKER, *args, **kwargs)

    tl.create_marker = create_marker
    return marker_tlui.timeline
