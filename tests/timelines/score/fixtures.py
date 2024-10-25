import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.timelines.timeline_kinds import TimelineKind


@pytest.fixture
def score_tlui(score_tl, tluis):
    ui = tluis.get_timeline_ui(score_tl.id)

    ui.create_component = score_tl.create_component

    yield ui


@pytest.fixture
def score_tl(tls):
    tl: ScoreTimeline = tls.create_timeline(TimelineKind.SCORE_TIMELINE)

    yield tl


@pytest.fixture
def note(score_tl):
    return score_tl.create_component(ComponentKind.NOTE, 0, 0, 0, 0, 3)[0]


@pytest.fixture
def staff(score_tl):
    return score_tl.create_component(ComponentKind.STAFF, 1, 5)


@pytest.fixture
def clef(score_tl):
    return score_tl.create_component(ComponentKind.CLEF, 0, shorthand=Clef.Shorthand.TREBLE)[0]


@pytest.fixture
def bar_line(score_tl):
    return score_tl.create_component(ComponentKind.BAR_LINE, 0)