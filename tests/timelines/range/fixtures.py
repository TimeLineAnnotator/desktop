import pytest

from tilia.requests import Post, post
from tilia.timelines.range.timeline import RangeTimeline
from tilia.ui import commands


@pytest.fixture
def range_tlui(range_tl, tluis):
    post(Post.APP_STATE_RECORD, "tlui fixture")
    ui = tluis.get_timeline_ui(range_tl.id)
    yield ui


@pytest.fixture
def range_tl(tls):
    tl: RangeTimeline = tls.create_timeline(RangeTimeline)
    yield tl


@pytest.fixture
def range_(range_tlui):
    commands.execute("timeline.range.add_range", start=10, end=20)
    return range_tlui.timeline[0]


@pytest.fixture
def range_ui(range_tlui, range_):
    return range_tlui.get_element(range_.id)
