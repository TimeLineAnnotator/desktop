import itertools
from unittest.mock import MagicMock

import pytest

from tilia.timelines.slider import SliderTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.tkinter.timelines.slider import SliderTimelineTkUI


@pytest.fixture
def tl_with_ui() -> SliderTimeline:

    id_counter = itertools.count()

    tl_coll_mock = MagicMock()
    tl_coll_mock.get_id = lambda: next(id_counter)

    tlui_coll_mock = MagicMock()
    tlui_coll_mock.get_id = lambda: next(id_counter)

    timeline = SliderTimeline(tl_coll_mock, None, TimelineKind.SLIDER_TIMELINE)

    timeline.ui = SliderTimelineTkUI(
        timeline_ui_collection=tlui_coll_mock,
        element_manager=MagicMock(),
        canvas=MagicMock(),
        toolbar=None,
        name="",
    )

    yield timeline


@pytest.fixture
def tl() -> SliderTimeline:
    timeline = SliderTimeline(MagicMock(), None)

    timeline.ui = MagicMock()
    yield timeline


class TestSliderTimeline:

    def test_constructor(self):
        SliderTimeline(
            MagicMock(),
            None,
            TimelineKind.SLIDER_TIMELINE
        )

    def test_serialize_timeline(self, tl_with_ui):

        serialized_timeline = tl_with_ui.to_dict()

        assert serialized_timeline["height"] == SliderTimelineTkUI.DEFAULT_HEIGHT
        assert serialized_timeline["is_visible"] is True
        print(serialized_timeline["display_position"])
