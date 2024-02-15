from unittest.mock import patch

from tests.ui.timelines.harmony.interact import click_harmony_ui
from tests.ui.timelines.interact import click_timeline_ui
from tilia.ui import actions
from tilia.ui.actions import TiliaAction
from tilia.ui.coords import get_x_by_time


class TestRightClick:
    def test_right_click(self, harmony_tlui):
        _, hui = harmony_tlui.create_harmony(0)
        with patch(
            "tilia.ui.timelines.harmony.context_menu.HarmonyContextMenu.exec"
        ) as exec_mock:
            hui.on_right_click(0, 0, None)

        exec_mock.assert_called_once()


class TestCopyPaste:
    def test_paste_single_into_timeline(self, harmony_tlui, tilia_state):
        _, hui = harmony_tlui.create_harmony(0)
        click_harmony_ui(hui)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        click_timeline_ui(harmony_tlui, 10)
        tilia_state.current_time = 50
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)
        assert len(harmony_tlui) == 2
        assert harmony_tlui[1].get_data("time") == 50

    def test_paste_multiple_into_timeline(self, harmony_tlui, tilia_state):
        _, hui1 = harmony_tlui.create_harmony(0)
        _, hui2 = harmony_tlui.create_harmony(10)
        _, hui3 = harmony_tlui.create_harmony(20)
        click_harmony_ui(hui1)
        click_harmony_ui(hui2, modifier="shift")
        click_harmony_ui(hui3, modifier="shift")
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        click_timeline_ui(harmony_tlui, 10)
        tilia_state.current_time = 50
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)
        assert len(harmony_tlui) == 6
        assert harmony_tlui[3].get_data("time") == 50
        assert harmony_tlui[4].get_data("time") == 60
        assert harmony_tlui[5].get_data("time") == 70

    def test_paste_single_into_element(self, harmony_tlui):
        attributes_to_copy = {
            "step": 2,
            "accidental": 1,
            "quality": "minor",
            "applied_to": 4,
            "inversion": 1,
            "comments": "some comments",
            "display_mode": "chord",
            "custom_text": "some custom text",
        }
        _, copied_hui = harmony_tlui.create_harmony(0, **attributes_to_copy)
        _, target_hui = harmony_tlui.create_harmony(
            10,
            step=1,
            accidental=-1,
            quality="major",
            applied_to=4,
            inversion=0,
            comments="other comments",
            display_mode="roman",
            custom_text="other custom text",
        )

        click_harmony_ui(copied_hui)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        click_harmony_ui(target_hui)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)
        assert len(harmony_tlui) == 2
        for attr, value in attributes_to_copy.items():
            assert target_hui.get_data(attr) == attributes_to_copy[attr]

    def test_paste_multiple_into_element(self, harmony_tlui):
        attributes_to_copy = {
            "step": 2,
            "accidental": 1,
            "quality": "minor",
            "applied_to": 4,
            "inversion": 1,
            "comments": "some comments",
            "display_mode": "chord",
            "custom_text": "some custom text",
        }
        copied_huis = []
        for i in range(3):
            _, hui1 = harmony_tlui.create_harmony(i * 10, **attributes_to_copy)
            copied_huis.append(hui1)

        _, target_hui = harmony_tlui.create_harmony(
            50,
            step=1,
            accidental=-1,
            quality="major",
            applied_to=4,
            inversion=0,
            comments="other comments",
            display_mode="roman",
            custom_text="other custom text",
        )

        for hui in copied_huis:
            click_harmony_ui(hui, modifier="shift")
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        click_timeline_ui(harmony_tlui, 90)
        click_harmony_ui(target_hui)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)
        assert len(harmony_tlui) == 6
        for attr, value in attributes_to_copy.items():
            assert target_hui.get_data(attr) == attributes_to_copy[attr]
