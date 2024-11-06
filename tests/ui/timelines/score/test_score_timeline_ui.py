import pytest

from tests.mock import Serve
from tilia.requests import Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.ui.actions import TiliaAction


def test_create(tluis, user_actions):
    with Serve(Get.FROM_USER_STRING, ("", True)):
        user_actions.trigger(TiliaAction.TIMELINES_ADD_SCORE_TIMELINE)

    assert len(tluis) == 1


def test_create_note(score_tlui, note):
    assert score_tlui[0]


def test_create_staff(score_tlui, staff):
    assert score_tlui[0]


@pytest.mark.parametrize('shorthand', Clef.Shorthand)
def test_create_clef(score_tlui, shorthand):
    score_tlui.create_component(ComponentKind.CLEF, 0, 0, shorthand=shorthand)
    assert score_tlui[0]


def test_create_barline(score_tlui, bar_line):
    assert score_tlui[0]


def test_create_time_signature(score_tlui, time_signature):
    assert score_tlui[0]


@pytest.mark.parametrize('fifths', range(-7, 8))
def test_create_key_signature(score_tlui, fifths):
    score_tlui.create_component(ComponentKind.KEY_SIGNATURE, 0, 0, fifths)
    assert score_tlui[0]
