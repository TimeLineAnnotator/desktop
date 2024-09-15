import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.components import Harmony, Mode
from tilia.timelines.harmony.timeline import HarmonyTimeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.timelines.harmony import HarmonyTimelineUI, HarmonyUI, ModeUI


class TestHarmonyTimelineUI(HarmonyTimelineUI):
    def create_harmony(
        self, time=0, step=0, accidental=0, quality="major", **kwargs
    ) -> tuple[Harmony, HarmonyUI]: ...

    def create_mode(
        self, time=0, step=0, accidental=0, type="major", **kwargs
    ) -> tuple[Mode, ModeUI]: ...


@pytest.fixture
def harmony_tlui(tls, tluis) -> TestHarmonyTimelineUI:
    tl: HarmonyTimeline = tls.create_timeline(TlKind.HARMONY_TIMELINE)
    ui = tluis.get_timeline_ui(tl.id)
    original_create_component = tl.create_component

    def create_harmony(time=0, step=0, accidental=0, quality="major", **kwargs):
        component, _ = original_create_component(
            ComponentKind.HARMONY, time, step, accidental, quality, **kwargs
        )
        return component, None

    def create_mode(time=0, step=0, accidental=0, type="major", **kwargs):
        component, _ = original_create_component(
            ComponentKind.MODE, time, step, accidental, type, **kwargs
        )
        return component, None

    tl.create_harmony = create_harmony
    ui.create_harmony = create_harmony
    tl.create_mode = create_mode
    ui.create_mode = create_mode
    ui.create_component = tl.create_component

    yield ui  # will be deleted by tls


@pytest.fixture
def harmony_tl(harmony_tlui):
    tl = harmony_tlui.timeline

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
