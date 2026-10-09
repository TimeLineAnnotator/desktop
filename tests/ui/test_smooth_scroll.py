import pytest
from PySide6.QtCore import SIGNAL
from PySide6.QtTest import QTest

from tests.utils import wait_for_smooth_movement
from tilia.requests import Get, get
from tilia.settings import settings
from tilia.ui import commands
from tilia.ui.smooth_scroll import SmoothSetter


class TestFollowingThePlayback:
    def test_moves_smoothly_to_the_new_time(self, tluis):
        settings.set("general", "prioritise_performance", False)
        commands.execute("timelines.add.marker", name="")
        time = get(Get.MEDIA_CURRENT_TIME) + 5.0

        commands.execute("media.seek", time)

        assert tluis.selected_time < time
        wait_for_smooth_movement(tluis.smooth_time)
        assert tluis.selected_time == pytest.approx(time)

    def test_moves_smoothly_to_a_whole_number_time(self, tluis):
        settings.set("general", "prioritise_performance", False)
        commands.execute("timelines.add.marker", name="")
        commands.execute("media.seek", 2.5)
        wait_for_smooth_movement(tluis.smooth_time)

        commands.execute("media.seek", 7)

        wait_for_smooth_movement(tluis.smooth_time)
        assert tluis.selected_time == 7.0

    def test_moves_at_once_when_prioritising_performance(self, tluis):
        settings.set("general", "prioritise_performance", True)
        commands.execute("timelines.add.marker", name="")
        time = get(Get.MEDIA_CURRENT_TIME) + 5.0

        commands.execute("media.seek", time)

        assert tluis.selected_time == time

    def test_prioritising_performance_stops_a_movement(self, tluis):
        settings.set("general", "prioritise_performance", False)
        commands.execute("timelines.add.marker", name="")
        time = get(Get.MEDIA_CURRENT_TIME) + 5.0
        commands.execute("media.seek", time)

        settings.set("general", "prioritise_performance", True)
        commands.execute("media.seek", time + 2.0)
        QTest.qWait(SmoothSetter.DURATION + 50)

        assert tluis.selected_time == time + 2.0

    def test_movement_has_one_slot_however_often_it_is_retargeted(self, tluis):
        settings.set("general", "prioritise_performance", False)
        commands.execute("timelines.add.marker", name="")
        start = get(Get.MEDIA_CURRENT_TIME)

        for step in range(1, 6):
            commands.execute("media.seek", start + step)

        animation = tluis.smooth_time.animation
        assert animation.receivers(SIGNAL("valueChanged(QVariant)")) == 1
        wait_for_smooth_movement(tluis.smooth_time)
