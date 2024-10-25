from tests.mock import Serve
from tilia.requests import Get
from tilia.ui.actions import TiliaAction


def test_create(tluis, user_actions):
    with Serve(Get.FROM_USER_STRING, ("", True)):
        user_actions.trigger(TiliaAction.TIMELINES_ADD_SCORE_TIMELINE)

    assert len(tluis) == 1


def test_create_note(tluis, note):
    assert note


def test_create_staff(tluis, staff):
    assert staff


def test_create_clef(tluis, clef):
    assert clef


def test_create_barline(tluis, bar_line):
    assert bar_line