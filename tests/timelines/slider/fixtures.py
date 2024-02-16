import pytest

from tilia.timelines.slider.timeline import SliderTimeline
from tilia.timelines.timeline_kinds import TimelineKind


@pytest.fixture
def slider_tlui(tls, tluis):
    tl: SliderTimeline = tls.create_timeline(TimelineKind.SLIDER_TIMELINE)
    ui = tluis.get_timeline_ui(tl.id)

    return ui


@pytest.fixture
def slider_tl(slider_tlui):
    return slider_tlui.timeline
