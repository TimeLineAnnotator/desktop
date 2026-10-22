import pytest

from tests.ui.timelines.interact import get_focused_widget, press_key
from tests.ui.timelines.marker.interact import click_marker_ui
from tilia.requests import Post, post
from tilia.settings import settings
from tilia.ui import commands
from tilia.ui.coords import time_x_converter


class TestCenterOnSelectionCheckbox:
    @staticmethod
    def _checkbox(qtui):
        return qtui.options_toolbar.center_on_selection_checkbox

    def test_reflects_setting_on_creation(self, qtui):
        assert self._checkbox(qtui).isChecked() == settings.get(
            "general", "center_on_selection"
        )

    def test_click_updates_setting(self, qtui):
        settings.set("general", "center_on_selection", True)
        self._checkbox(qtui).setChecked(True)

        self._checkbox(qtui).click()

        assert settings.get("general", "center_on_selection") is False

        self._checkbox(qtui).click()

        assert settings.get("general", "center_on_selection") is True

    def test_settings_updated_syncs_checkbox(self, qtui):
        self._checkbox(qtui).setChecked(True)

        settings.set("general", "center_on_selection", False)
        post(Post.SETTINGS_UPDATED, ["general"])

        assert not self._checkbox(qtui).isChecked()

    def test_unchecking_disables_centering(self, qtui, marker_tlui, tluis, tilia_state):
        settings.set("general", "center_on_selection", True)
        self._checkbox(qtui).setChecked(True)
        get_focused_widget()
        left, right = tluis.view.current_viewport_x.values()
        offscreen = time_x_converter.get_time_by_x(right + (right - left))
        assert offscreen < tilia_state.duration
        commands.execute("media.seek", offscreen)
        commands.execute("timeline.marker.add")
        commands.execute(
            "media.seek", time_x_converter.get_time_by_x((left + right) / 2)
        )
        commands.execute("timeline.marker.add")
        click_marker_ui(marker_tlui[0])
        viewport_before = tluis.view.current_viewport_x

        self._checkbox(qtui).click()
        press_key("Right", widget=marker_tlui.view)

        assert marker_tlui[1].is_selected()
        assert tluis.view.current_viewport_x == viewport_before

    def test_checking_enables_centering(self, qtui, marker_tlui, tluis, tilia_state):
        settings.set("general", "center_on_selection", False)
        self._checkbox(qtui).setChecked(False)
        get_focused_widget()
        left, right = tluis.view.current_viewport_x.values()
        offscreen = time_x_converter.get_time_by_x(right + (right - left))
        assert offscreen < tilia_state.duration
        commands.execute("media.seek", offscreen)
        commands.execute("timeline.marker.add")
        commands.execute(
            "media.seek", time_x_converter.get_time_by_x((left + right) / 2)
        )
        commands.execute("timeline.marker.add")
        click_marker_ui(marker_tlui[0])

        self._checkbox(qtui).click()
        press_key("Right", widget=marker_tlui.view)

        assert marker_tlui[1].is_selected()
        left, right = tluis.view.current_viewport_x.values()
        assert (left + right) / 2 == pytest.approx(
            time_x_converter.get_x_by_time(offscreen), abs=2
        )
