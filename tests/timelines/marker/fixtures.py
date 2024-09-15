import functools

import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind


@pytest.fixture
def marker_tlui(tls, tluis):
    tl: MarkerTimeline = tls.create_timeline(TlKind.MARKER_TIMELINE)
    ui = tluis.get_timeline_ui(tl.id)

    tl.create_marker = functools.partial(tl.create_component, ComponentKind.MARKER)
    ui.create_marker = tl.create_marker
    ui.create_component = tl.create_component

    yield ui  # will be deleted by tls


@pytest.fixture
def marker_tl(marker_tlui):
    yield marker_tlui.timeline


@pytest.fixture
def mrkui(marker_tlui):
    marker_tlui.create_marker(0)
    return marker_tlui[0]


@pytest.fixture
def mrk(marker_tlui):
    marker_tlui.create_marker(0)
    return marker_tlui.timeline[0]


@pytest.fixture
def mrk_and_ui(marker_tlui):
    return marker_tlui.create_marker(0)
