import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.oscillogram.components import Oscillogram
from tilia.timelines.oscillogram.timeline import OscillogramTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.oscillogram import OscillogramTimelineUI, OscillogramUI


class TestOscillogramTimelineUI(OscillogramTimelineUI):
    def create_component(self, _: ComponentKind, *args, ** kwargs): ...

    def create_oscillogram(
        self, start: float, end: float, amplitude: float, **kwargs
    ) -> tuple[Oscillogram | None, OscillogramUI | None]: ...


@pytest.fixture
def oscillogram_tlui(tilia, tls, tluis) -> TestOscillogramTimelineUI:
    def create_component(_: ComponentKind, *args, **kwargs):
        return create_oscillogram(*args, **kwargs)

    def create_oscillogram(
        start: float = 0, end: float = None, amplitude: float = 1, **kwargs
    ) -> tuple[Oscillogram | None, OscillogramUI | None]:
        if end is None:
            end = start + 1
        component, _ = tl.create_timeline_component(
            ComponentKind.OSCILLOGRAM, start, end, amplitude, **kwargs
        )
        element = ui.get_element(component.id) if component else None
        return component, element

    tl: OscillogramTimeline = tls.create_timeline(TimelineKind.OSCILLOGRAM_TIMELINE)
    tl.refresh = lambda self: None
    ui = tluis.get_timeline_ui(tl.id)

    tl.clear()

    tl.create_hierarchy = create_oscillogram
    ui.create_hierarchy = create_oscillogram
    tl.create_component = create_component
    ui.create_component = create_component
    return ui  # will be deleted by tls


@pytest.fixture
def oscillogram_tl(oscillogram_tlui):
    return oscillogram_tlui.timeline
