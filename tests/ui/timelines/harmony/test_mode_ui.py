from unittest.mock import patch

import pytest

from tests.ui.timelines.harmony.interact import click_mode_ui
from tests.ui.timelines.interact import click_timeline_ui
from tilia.ui import actions
from tilia.ui.actions import TiliaAction


@pytest.fixture
def tlui(harmony_tlui):
    return harmony_tlui


class TestRightClick:
    def test_right_click(self, tlui):
        tlui.create_mode()
        with patch(
                "tilia.ui.timelines.harmony.context_menu.ModeContextMenu.exec"
        ) as exec_mock:
            tlui[0].on_right_click(0, 0, None)

        exec_mock.assert_called_once()


class TestCopyPaste:
    def test_paste_single_into_timeline(self, tlui, tilia_state):
        tlui.create_mode(0)
        click_mode_ui(tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        click_timeline_ui(tlui, 10)
        tilia_state.current_time = 50
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)
        assert len(tlui) == 2
        assert tlui[1].get_data("time") == 50

    def test_paste_multiple_into_timeline(self, tlui, tilia_state):
        tlui.create_mode(0)
        tlui.create_mode(10)
        tlui.create_mode(20)
        click_mode_ui(tlui[0])
        click_mode_ui(tlui[1], modifier="shift")
        click_mode_ui(tlui[2], modifier="shift")
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        click_timeline_ui(tlui, 90)
        tilia_state.current_time = 50
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)
        assert len(tlui) == 6
        assert tlui[3].get_data("time") == 50
        assert tlui[4].get_data("time") == 60
        assert tlui[5].get_data("time") == 70

    def test_paste_single_into_element(self, tlui):
        attributes_to_copy = {
            "step": 2,
            "accidental": 1,
            "type": "minor",
            "comments": "some comments",
        }
        _, copied_mui = tlui.create_mode(0, **attributes_to_copy)
        _, target_mui = tlui.create_mode(
            10,
            step=1,
            accidental=-1,
            type="major",
            comments="other comments",
        )

        click_mode_ui(tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        click_mode_ui(tlui[1])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)
        assert len(tlui) == 2
        for attr, value in attributes_to_copy.items():
            assert tlui[1].get_data(attr) == attributes_to_copy[attr]

    def test_paste_multiple_into_element(self, tlui):
        attributes_to_copy = {
            "step": 2,
            "accidental": 1,
            "type": "minor",
            "comments": "some comments",
        }
        for i in range(3):
            tlui.create_mode(i * 10, **attributes_to_copy)

        copied_muis = [tlui[0], tlui[1], tlui[2]]
        tlui.create_mode(
            50,
            step=1,
            accidental=-1,
            type="major",
            comments="other comments",
        )
        target_mui = tlui[3]

        for mui in copied_muis:
            click_mode_ui(mui, modifier="shift")
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        click_timeline_ui(tlui, 90)
        click_mode_ui(target_mui)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)
        assert len(tlui) == 6
        for attr, value in attributes_to_copy.items():
            assert target_mui.get_data(attr) == attributes_to_copy[attr]
