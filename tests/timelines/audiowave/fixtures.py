import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.audiowave.components import AmplitudeBar
from tilia.timelines.audiowave.timeline import AudioWaveTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.audiowave import AudioWaveTimelineUI, AmplitudeBarUI


class TestAudioWaveTimelineUI(AudioWaveTimelineUI):
    def create_component(self, _: ComponentKind, *args, ** kwargs): ...

    def create_amplitudebar(
        self, start: float, end: float, amplitude: float, **kwargs
    ) -> tuple[AmplitudeBar | None, AmplitudeBarUI | None]: ...


@pytest.fixture
def audiowave_tlui(tilia, tls, tluis) -> TestAudioWaveTimelineUI:
    def create_component(_: ComponentKind, *args, **kwargs):
        return create_amplitudebar(*args, **kwargs)

    def create_amplitudebar(
        start: float = 0, end: float = None, amplitude: float = 1, **kwargs
    ) -> tuple[AmplitudeBar | None, AmplitudeBarUI | None]:
        if end is None:
            end = start + 1
        component, _ = tl.create_timeline_component(
            ComponentKind.AUDIOWAVE, start, end, amplitude, **kwargs
        )
        element = ui.get_element(component.id) if component else None
        return component, element

    tl: AudioWaveTimeline = tls.create_timeline(TimelineKind.AUDIOWAVE_TIMELINE)
    tl.refresh = lambda self: None
    ui = tluis.get_timeline_ui(tl.id)

    tl.clear()

    tl.create_amplitudebar = create_amplitudebar
    ui.create_amplitudebar = create_amplitudebar
    tl.create_component = create_component
    ui.create_component = create_component
    return ui  # will be deleted by tls


@pytest.fixture
def audiowave_tl(audiowave_tlui):
    return audiowave_tlui.timeline
