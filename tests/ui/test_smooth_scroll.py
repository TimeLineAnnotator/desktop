from unittest.mock import patch

import pytest
from PySide6.QtCore import SIGNAL, QVariantAnimation
from PySide6.QtTest import QTest

from tests.utils import wait_for_smooth_movement
from tilia.requests import Get, get
from tilia.settings import settings
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.smooth_scroll import SmoothSetter


def playback_line_time(tlui) -> float:
    return time_x_converter.get_time_by_x(tlui.scene.playback_line.line().x1())


class TestFollowingThePlayback:
    def test_lines_move_smoothly_to_the_new_time(self, marker_tlui, tluis):
        settings.set("general", "prioritise_performance", False)
        time = get(Get.MEDIA_CURRENT_TIME) + 5.0

        commands.execute("media.seek", time)

        assert playback_line_time(marker_tlui) < time
        wait_for_smooth_movement(tluis.smooth_playback_lines)
        assert playback_line_time(marker_tlui) == pytest.approx(time)

    def test_selected_time_is_the_new_time_at_once(self, marker_tlui, tluis):
        settings.set("general", "prioritise_performance", False)
        time = get(Get.MEDIA_CURRENT_TIME) + 5.0

        commands.execute("media.seek", time)

        assert get(Get.SELECTED_TIME) == time
        wait_for_smooth_movement(tluis.smooth_playback_lines)

    def test_lines_move_smoothly_to_a_whole_number_time(self, marker_tlui, tluis):
        settings.set("general", "prioritise_performance", False)
        commands.execute("media.seek", 2.5)
        wait_for_smooth_movement(tluis.smooth_playback_lines)

        commands.execute("media.seek", 7)

        wait_for_smooth_movement(tluis.smooth_playback_lines)
        assert playback_line_time(marker_tlui) == pytest.approx(7.0)

    def test_new_time_during_a_movement_starts_a_new_one_from_where_it_is(
        self, marker_tlui, tluis
    ):
        settings.set("general", "prioritise_performance", False)
        time = get(Get.MEDIA_CURRENT_TIME) + 10.0
        commands.execute("media.seek", time)
        QTest.qWait(SmoothSetter.DURATION // 2)
        reached = playback_line_time(marker_tlui)

        commands.execute("media.seek", time + 10.0)

        assert playback_line_time(marker_tlui) == pytest.approx(reached)
        wait_for_smooth_movement(tluis.smooth_playback_lines)
        assert playback_line_time(marker_tlui) == pytest.approx(time + 10.0)

    def test_lines_move_at_once_when_prioritising_performance(self, marker_tlui):
        settings.set("general", "prioritise_performance", True)
        time = get(Get.MEDIA_CURRENT_TIME) + 5.0

        commands.execute("media.seek", time)

        assert playback_line_time(marker_tlui) == pytest.approx(time)

    def test_prioritising_performance_stops_a_movement(self, marker_tlui):
        settings.set("general", "prioritise_performance", False)
        time = get(Get.MEDIA_CURRENT_TIME) + 5.0
        commands.execute("media.seek", time)

        settings.set("general", "prioritise_performance", True)
        commands.execute("media.seek", time + 2.0)
        QTest.qWait(SmoothSetter.DURATION + 50)

        assert playback_line_time(marker_tlui) == pytest.approx(time + 2.0)

    def test_movement_has_one_slot_however_often_it_is_retargeted(
        self, marker_tlui, tluis
    ):
        settings.set("general", "prioritise_performance", False)
        start = get(Get.MEDIA_CURRENT_TIME)

        for step in range(1, 6):
            commands.execute("media.seek", start + step)

        animation = tluis.smooth_playback_lines.animation
        assert animation.receivers(SIGNAL("valueChanged(QVariant)")) == 1
        wait_for_smooth_movement(tluis.smooth_playback_lines)


def test_zooming_centres_at_once_and_leaves_the_performance_setting(tluis):
    settings.set("general", "prioritise_performance", False)

    with patch.object(settings, "set", wraps=settings.set) as set_setting:
        try:
            commands.execute("view.zoom.in")
        finally:
            commands.execute("view.zoom.set", 1.0)

    assert not [
        c for c in set_setting.call_args_list if "prioritise_performance" in c.args
    ]
    assert tluis.view.smooth_x.animation.state() is QVariantAnimation.State.Stopped


def test_zooming_during_a_movement_leaves_the_lines_where_they_are(marker_tlui, tluis):
    settings.set("general", "prioritise_performance", False)
    start = get(Get.MEDIA_CURRENT_TIME)
    commands.execute("media.seek", start + 10.0)
    # Halfway through the movement, without depending on the timer.
    tluis.smooth_playback_lines.animation.setCurrentTime(SmoothSetter.DURATION // 2)
    reached = playback_line_time(marker_tlui)
    assert start < reached < start + 10.0

    try:
        commands.execute("view.zoom.in")
        after_zoom = playback_line_time(marker_tlui)
        wait_for_smooth_movement(tluis.smooth_playback_lines)
    finally:
        commands.execute("view.zoom.set", 1.0)

    assert after_zoom == pytest.approx(reached)
