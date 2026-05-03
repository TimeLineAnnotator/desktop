import pytest

from tilia.timelines.slider.timeline import SliderTimeline


@pytest.fixture
def slider_tlui(tls, tluis):
    tl: SliderTimeline = tls.create_timeline(SliderTimeline)
    ui = tluis.get_timeline_ui(tl.id)

    return ui


@pytest.fixture
def slider_tl(slider_tlui):
    return slider_tlui.timeline
