import pytest

from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind as TlKind


@pytest.fixture
def beat_tlui(beat_tl, tluis):
    ui = tluis.get_timeline_ui(beat_tl.id)
    ui.create_beat = beat_tl.create_beat
    ui.create_component = beat_tl.create_component

    yield ui  # will be deleted by tls


@pytest.fixture
def beat_tl(tls):
    tl: BeatTimeline = tls.create_timeline(TlKind.BEAT_TIMELINE, [], beat_pattern=[4])

    def create_beat(*args, **kwargs):
        beat, error = tl.create_component(ComponentKind.BEAT, *args, **kwargs)
        if error:
            raise ValueError(f"Unable to create beat: {error}")
        return beat, None

    tl.create_beat = create_beat

    yield tl


@pytest.fixture
def beat(beat_tl):
    return beat_tl.create_beat(0)[0]


@pytest.fixture()
def beat_ui(beat_tlui, beat):
    return beat_tlui.get_element(beat.id)
