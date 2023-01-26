import itertools
from unittest.mock import MagicMock

import pytest

from tilia.timelines.create import create_timeline
from tilia.timelines.slider import SliderTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.slider import SliderTimelineUI


@pytest.fixture
def slider_tl(tilia, tl_clct, tlui_clct) -> SliderTimeline:
    tl: SliderTimeline = create_timeline(
        TimelineKind.SLIDER_TIMELINE, tl_clct, tlui_clct
    )

    tl.clear()
    yield tl
    tl_clct.delete_timeline(tl)
    tilia._undo_manager.clear()


class TestSliderTimeline:
    def test_serialize_timeline(self, slider_tl):

        serialized_timeline = slider_tl.get_state()

        assert serialized_timeline["height"] == SliderTimelineUI.DEFAULT_HEIGHT
        assert serialized_timeline["is_visible"] is True
        print(serialized_timeline["display_position"])
