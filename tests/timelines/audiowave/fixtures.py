import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.audiowave.components import AudioWave
from tilia.timelines.audiowave.timeline import AudioWaveTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.audiowave import AudioWaveTimelineUI, AudioWaveUI


class TestAudioWaveTimelineUI(AudioWaveTimelineUI):
    def create_component(self, _: ComponentKind, *args, ** kwargs): ...

    def create_audiowave(
        self, start: float, end: float, amplitude: float, **kwargs
    ) -> tuple[AudioWave | None, AudioWaveUI | None]: ...


@pytest.fixture
def audiowave_tlui(tilia, tls, tluis) -> TestAudioWaveTimelineUI:
    def create_component(_: ComponentKind, *args, **kwargs):
        return create_audiowave(*args, **kwargs)

    def create_audiowave(
        start: float = 0, end: float = None, amplitude: float = 1, **kwargs
    ) -> tuple[AudioWave | None, AudioWaveUI | None]:
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

    tl.create_audiowave = create_audiowave
    ui.create_audiowave = create_audiowave
    tl.create_component = create_component
    ui.create_component = create_component
    return ui  # will be deleted by tls


@pytest.fixture
def audiowave_tl(audiowave_tlui):
    return audiowave_tlui.timeline
