from tests.mock import Serve
from tilia.requests import Get
from tilia.ui.actions import TiliaAction


def test_create(tluis, user_actions):
    with Serve(Get.FROM_USER_STRING, ("", True)):
        user_actions.trigger(TiliaAction.TIMELINES_ADD_SCORE_TIMELINE)

    assert len(tluis) == 1


def test_create_note(tluis, note):
    import os
    import time
    os.environ['QT_QTA_PLATFORM'] = 'windows'

    time.sleep(3)
    assert note