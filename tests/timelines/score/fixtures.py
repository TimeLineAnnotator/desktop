import functools

import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.timelines.timeline_kinds import TimelineKind


@pytest.fixture
def score_tlui(score_tl, tluis):
    ui = tluis.get_timeline_ui(score_tl.id)

    ui.create_note = score_tl.create_note
    ui.create_component = score_tl.create_component

    yield ui


@pytest.fixture
def score_tl(tls):
    tl: ScoreTimeline = tls.create_timeline(TimelineKind.SCORE_TIMELINE)
    tl.create_note = functools.partial(tl.create_component, ComponentKind.NOTE)

    yield tl


@pytest.fixture
def note(score_tl):
    return score_tl.create_note(0, 0, 0, 0, 3)[0]
