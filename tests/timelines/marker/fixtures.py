import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.components import Marker
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.timelines.marker import MarkerTimelineUI, MarkerUI


class TestMarkerTimelineUI(MarkerTimelineUI):
    def create_component(self, _: ComponentKind, *args, **kwargs): ...

    def create_marker(self, *args, **kwargs) -> tuple[Marker, MarkerUI]: ...


@pytest.fixture
def marker_tlui(tls, tluis) -> TestMarkerTimelineUI:
    tl: MarkerTimeline = tls.create_timeline(TlKind.MARKER_TIMELINE)
    ui = tluis.get_timeline_ui(tl.id)

    def create_component(_: ComponentKind, *args, **kwargs):
        return create_marker(*args, **kwargs)

    def create_marker(*args, **kwargs):
        component, _ = tl.create_timeline_component(ComponentKind.MARKER, *args, **kwargs)
        element = ui.get_element(component.id) if component else None
        return component, element

    tl.create_marker = create_marker
    ui.create_marker = create_marker
    tl.create_component = create_component
    ui.create_component = create_component

    yield ui  # will be deleted by tls


@pytest.fixture
def marker_tl(marker_tlui):
    yield marker_tlui.timeline


@pytest.fixture
def mrkui(marker_tlui):
    _, _mrkui = marker_tlui.create_marker(0)
    return _mrkui


@pytest.fixture
def mrk(marker_tlui):
    _mrk, _ = marker_tlui.create_marker(0)
    return _mrk


@pytest.fixture
def mrk_and_ui(marker_tlui):
    return marker_tlui.create_marker(0)
