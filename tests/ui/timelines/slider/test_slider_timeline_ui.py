import pytest

from tests.utils import wait_for_smooth_movement
from tilia.requests import Get, get
from tilia.settings import settings
from tilia.ui import commands
from tilia.ui.coords import time_x_converter


def test_undo_redo(slider_tlui, marker_tlui):

    # using marker tl to trigger an actions that can be undone
    commands.execute("timeline.marker.add")

    commands.execute("edit.undo")
    assert len(marker_tlui) == 0

    commands.execute("edit.redo")
    assert len(marker_tlui) == 1


def test_follows_the_playback_smoothly(slider_tlui, tluis):
    settings.set("general", "prioritise_performance", False)
    x = time_x_converter.get_x_by_time(get(Get.MEDIA_CURRENT_TIME) + 5.0)

    commands.execute("media.seek", get(Get.MEDIA_CURRENT_TIME) + 5.0)

    assert slider_tlui.x < x
    wait_for_smooth_movement(slider_tlui.smooth_x, tluis.smooth_time)
    assert slider_tlui.x == pytest.approx(x)
