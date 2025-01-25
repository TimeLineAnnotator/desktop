import functools

import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind


@pytest.fixture
def marker_tlui(marker_tl, tluis):
    ui = tluis.get_timeline_ui(marker_tl.id)

    ui.create_marker = marker_tl.create_marker
    ui.create_component = marker_tl.create_component

    yield ui  # will be deleted by tls


@pytest.fixture
def marker_tl(tls):
    tl: MarkerTimeline = tls.create_timeline(TlKind.MARKER_TIMELINE)
    tl.create_marker = functools.partial(tl.create_component, ComponentKind.MARKER)

    yield tl


@pytest.fixture
def mrkui(marker_tlui):
    marker_tlui.create_marker(0)
    return marker_tlui[0]


@pytest.fixture
def marker(marker_tlui):
    marker_tlui.create_marker(0)
    return marker_tlui.timeline[0]


@pytest.fixture
def marker_ui(marker_tlui, marker):
    return marker_tlui.get_element(marker.id)
