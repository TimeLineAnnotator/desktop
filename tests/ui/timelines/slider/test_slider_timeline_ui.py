import pytest
from PySide6.QtCore import QVariantAnimation

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
    wait_for_smooth_movement(slider_tlui.smooth_x, tluis.smooth_playback_lines)
    assert slider_tlui.x == pytest.approx(x)


def test_zooming_during_a_smooth_movement_keeps_the_trough_at_the_time(
    slider_tlui, tluis
):
    settings.set("general", "prioritise_performance", False)
    time = get(Get.MEDIA_CURRENT_TIME) + 50.0
    commands.execute("media.seek", time)

    commands.execute("view.zoom.in")
    try:
        wait_for_smooth_movement(slider_tlui.smooth_x, tluis.smooth_playback_lines)
        x, expected_x = slider_tlui.x, time_x_converter.get_x_by_time(time)
    finally:
        # The zoom outlasts the test otherwise.
        commands.execute("view.zoom.set", 1.0)

    assert x == pytest.approx(expected_x)


def test_smooth_movement_stops_when_the_timeline_is_deleted(slider_tlui, tluis):
    settings.set("general", "prioritise_performance", False)
    commands.execute("media.seek", get(Get.MEDIA_CURRENT_TIME) + 5.0)
    animation = slider_tlui.smooth_x.animation
    assert animation.state() is QVariantAnimation.State.Running

    commands.execute("timeline.delete", slider_tlui, confirm=False)

    assert animation.state() is QVariantAnimation.State.Stopped
    wait_for_smooth_movement(tluis.smooth_playback_lines)
