import functools

import pytest

from tilia.requests import Post, post
from tilia.timelines.audiowave.timeline import AudioWaveTimeline
from tilia.timelines.component_kinds import ComponentKind


@pytest.fixture
def audiowave_tlui(tilia, audiowave_tl, tluis):
    post(Post.APP_STATE_RECORD, "tlui fixture")
    ui = tluis.get_timeline_ui(audiowave_tl.id)

    ui.create_amplitudebar = audiowave_tl.create_amplitudebar
    ui.create_component = audiowave_tl.create_component
    return ui  # will be deleted by tls


@pytest.fixture
def audiowave_tl(tls):
    tl: AudioWaveTimeline = tls.create_timeline(AudioWaveTimeline)
    tl.refresh = lambda self: None

    tl.clear()

    tl.create_amplitudebar = functools.partial(
        tl.create_component, ComponentKind.AUDIOWAVE
    )
    return tl


@pytest.fixture
def amplitudebar(audiowave_tl):
    return audiowave_tl.create_amplitudebar(0, 1, 0.5)[0]


@pytest.fixture
def amplitudebar_ui(audiowave_tlui, amplitudebar):
    return audiowave_tlui.get_element(amplitudebar.id)
