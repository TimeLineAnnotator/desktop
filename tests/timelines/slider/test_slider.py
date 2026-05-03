import pytest

from tilia.timelines.slider.timeline import SliderTimeline


@pytest.fixture
def slider_tl(tilia, tls, tluis) -> SliderTimeline:
    tl: SliderTimeline = tls.create_timeline(SliderTimeline)

    tl.clear()
    yield tl
    tls.delete_timeline(tl)
    tilia.undo_manager.clear()


class TestSliderTimeline:
    def test_serialize_timeline(self, slider_tl):
        serialized_timeline = slider_tl.get_state()

        assert serialized_timeline["is_visible"] is True
