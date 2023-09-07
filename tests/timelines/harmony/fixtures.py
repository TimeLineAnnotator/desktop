import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.components import Harmony
from tilia.timelines.harmony.timeline import HarmonyTimeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.timelines.harmony import HarmonyTimelineUI, HarmonyUI


class TestHarmonyTimelineUI(HarmonyTimelineUI):
    def create_harmony(self, time=0, step=0, accidental=0, quality='major', **kwargs) -> tuple[Harmony, HarmonyUI]: ...


@pytest.fixture
def harmony_tlui(tls, tluis) -> TestHarmonyTimelineUI:
    tl: HarmonyTimeline = tls.create_timeline(TlKind.HARMONY_TIMELINE)
    ui = tluis.get_timeline_ui(tl.id)

    def create_harmony(time=0, step=0, accidental=0, quality='major', **kwargs):
        component = tl.create_timeline_component(ComponentKind.HARMONY, time, step, accidental, quality, **kwargs)
        element = ui.get_element(component.id)
        return component, element

    tl.create_harmony = create_harmony
    ui.create_harmony = create_harmony

    yield ui  # will be deleted by tls


@pytest.fixture
def harmony_tl(harmony_tlui):
    tl = harmony_tlui.timeline

    def create_harmony(*args, **kwargs):
        return tl.create_timeline_component(ComponentKind.HARMONY, *args, **kwargs)

    tl.create_harmony = create_harmony
    yield tl


@pytest.fixture
def harui(harmony_tlui):
    _, _mrkui = harmony_tlui.create_harmony(0)
    return _mrkui


@pytest.fixture
def har(harmony_tlui):
    _mrk, _ = harmony_tlui.create_harmony(0)
    return _mrk


@pytest.fixture
def har_and_ui(harmony_tlui):
    return harmony_tlui.create_harmony(0)
