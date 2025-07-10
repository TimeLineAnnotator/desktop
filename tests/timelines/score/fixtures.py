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
    score_tl.create_component(ComponentKind.STAFF, 0, 5)
    score_tl.create_component(ComponentKind.CLEF, 0, 0, shorthand=Clef.Shorthand.TREBLE)
    return score_tl.create_component(ComponentKind.NOTE, 0, 1, 0, 0, 3, 0)[0]


@pytest.fixture
def note_ui(score_tlui, note):
    return score_tlui.get_component_ui(note)


@pytest.fixture
def staff(score_tl):
    return score_tl.create_component(ComponentKind.STAFF, 1, 5)


@pytest.fixture
def staff_ui(score_tlui, staff):
    return score_tlui.get_element(staff)


@pytest.fixture
def clef(score_tl):
    return score_tl.create_component(
        ComponentKind.CLEF, 0, 0, shorthand=Clef.Shorthand.TREBLE
    )[0]


@pytest.fixture
def clef_ui(score_tlui, clef):
    return score_tlui.get_component_ui(clef)


@pytest.fixture
def bar_line(score_tl):
    return score_tl.create_component(ComponentKind.BAR_LINE, 0)


@pytest.fixture
def bar_line_ui(score_tlui, bar_line):
    return score_tlui.get_element(bar_line)


@pytest.fixture
def time_signature(score_tl):
    return score_tl.create_component(ComponentKind.TIME_SIGNATURE, 0, 0, 4, 4)[0]


@pytest.fixture
def time_signature_ui(score_tlui, time_signature):
    return score_tlui.get_component_ui(time_signature)


@pytest.fixture
def key_signature(score_tl):
    return score_tl.create_component(ComponentKind.KEY_SIGNATURE, 0, 0, 0)[0]
