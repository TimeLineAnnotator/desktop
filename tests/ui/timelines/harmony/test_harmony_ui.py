from unittest.mock import Mock, patch

import pytest

from tests.ui.timelines.harmony.interact import click_harmony_ui
from tests.ui.timelines.harmony.test_harmony_timeline_ui import add_harmony, add_mode
from tests.ui.timelines.interact import click_timeline_ui
from tilia.requests import Post, post
from tilia.ui import commands
from tilia.ui.windows.kinds import WindowKind


@pytest.fixture
def tlui(harmony_tlui):
    return harmony_tlui


class TestRightClick:
    def test_right_click(self, tlui):
        _, hui = tlui.create_harmony(0)
        with patch(
            "tilia.ui.timelines.harmony.context_menu.HarmonyContextMenu.exec"
        ) as exec_mock:
            tlui[0].on_right_click(0, 0, None)

        exec_mock.assert_called_once()


class TestCopyPaste:
    def test_paste_single_into_timeline(self, tlui):
        _, hui = tlui.create_harmony(0)
        click_harmony_ui(tlui[0])
        commands.execute("timeline.component.copy")
        click_timeline_ui(tlui, 10)
        commands.execute("media.seek", 50)
        commands.execute("timeline.component.paste")
        assert len(tlui) == 2
        assert tlui[1].get_data("time") == 50

    def test_paste_multiple_into_timeline(self, tlui):
        _, hui1 = tlui.create_harmony(0)
        _, hui2 = tlui.create_harmony(10)
        _, hui3 = tlui.create_harmony(20)
        click_harmony_ui(tlui[0])
        click_harmony_ui(tlui[1], modifier="ctrl")
        click_harmony_ui(tlui[2], modifier="ctrl")
        commands.execute("timeline.component.copy")
        click_timeline_ui(tlui, 10)
        commands.execute("media.seek", 50)
        commands.execute("timeline.component.paste")
        assert len(tlui) == 6
        assert tlui[3].get_data("time") == 50
        assert tlui[4].get_data("time") == 60
        assert tlui[5].get_data("time") == 70

    def test_paste_single_into_element(self, tlui):
        attributes_to_copy = {
            "step": 2,
            "accidental": 1,
            "quality": "minor",
            "applied_to": 4,
            "inversion": 1,
            "comments": "some comments",
            "display_mode": "letter",
            "custom_text": "some custom text",
        }
        _, copied_hui = tlui.create_harmony(0, **attributes_to_copy)
        tlui.create_harmony(
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

        click_harmony_ui(tlui[0])
        commands.execute("timeline.component.copy")
        click_harmony_ui(tlui[1])
        commands.execute("timeline.component.paste")
        assert len(tlui) == 2
        for attr in attributes_to_copy.keys():
            assert tlui[1].get_data(attr) == attributes_to_copy[attr]

    def test_paste_multiple_into_element(self, tlui):
        attributes_to_copy = {
            "step": 2,
            "accidental": 1,
            "quality": "minor",
            "applied_to": 4,
            "inversion": 1,
            "comments": "some comments",
            "display_mode": "letter",
            "custom_text": "some custom text",
        }
        for i in range(3):
            tlui.create_harmony(i * 10, **attributes_to_copy)

        copied_huis = [tlui[0], tlui[1], tlui[2]]
        tlui.create_harmony(
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
        target_hui = tlui[3]

        for hui in copied_huis:
            click_harmony_ui(hui, modifier="ctrl")
        commands.execute("timeline.component.copy")
        click_timeline_ui(tlui, 90)
        click_harmony_ui(target_hui)
        commands.execute("timeline.component.paste")
        assert len(tlui) == 6
        for attr in attributes_to_copy.keys():
            assert target_hui.get_data(attr) == attributes_to_copy[attr]


class TestDoubleClick:
    def test_harmony_seeks(self, harmony_tlui, tilia_state):
        add_harmony(10)
        harmony_tlui[0].on_double_left_click(None)

        assert tilia_state.current_time == 10

    def test_harmony_does_not_trigger_drag(self, harmony_tlui):
        add_harmony()
        mock = Mock()
        harmony_tlui[0].setup_drag = mock
        harmony_tlui[0].on_double_left_click(None)

        mock.assert_not_called()

    def test_mode_seeks(self, harmony_tlui, tilia_state):
        add_mode(10)
        harmony_tlui[0].on_double_left_click(None)

        assert tilia_state.current_time == 10

    def test_mode_does_not_trigger_drag(self, harmony_tlui):
        add_mode()
        mock = Mock()
        harmony_tlui[0].setup_drag = mock
        harmony_tlui[0].on_double_left_click(None)

        mock.assert_not_called()


class TestInversionInspectorItems:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def open_inspector_for(self, harmony_ui, qtui):
        click_harmony_ui(harmony_ui)
        commands.execute("timeline.element.inspect")
        return qtui._windows[WindowKind.INSPECT]

    def test_major_triad_has_three_inversion_choices(self, qtui, harmony_tlui):
        add_harmony(quality="major")
        inspector = self.open_inspector_for(harmony_tlui.harmonies()[0], qtui)

        inversion_combo = inspector.field_name_to_widgets["Inversion"][1]
        assert inversion_combo.count() == 3  # inversions 0, 1, 2

    def test_ninth_chord_has_five_inversion_choices(self, qtui, harmony_tlui):
        add_harmony(quality="dominant-ninth")
        inspector = self.open_inspector_for(harmony_tlui.harmonies()[0], qtui)

        inversion_combo = inspector.field_name_to_widgets["Inversion"][1]
        assert inversion_combo.count() == 5  # inversions 0, 1, 2, 3, 4

    def test_inversion_choices_update_when_quality_changes(self, qtui, harmony_tlui):
        add_harmony(quality="major")
        inspector = self.open_inspector_for(harmony_tlui.harmonies()[0], qtui)

        inversion_combo = inspector.field_name_to_widgets["Inversion"][1]
        quality_combo = inspector.field_name_to_widgets["Quality"][1]
        assert inversion_combo.count() == 3  # major: inversions 0, 1, 2

        quality_combo.setCurrentIndex(quality_combo.findData("dominant-ninth"))

        assert inversion_combo.count() == 5  # dominant-ninth: inversions 0, 1, 2, 3, 4

    def test_inversion_clamped_to_max_when_quality_reduces_range(
        self, qtui, harmony_tlui
    ):
        add_harmony(quality="dominant-ninth", inversion=4)
        inspector = self.open_inspector_for(harmony_tlui.harmonies()[0], qtui)

        inversion_combo = inspector.field_name_to_widgets["Inversion"][1]
        quality_combo = inspector.field_name_to_widgets["Quality"][1]
        assert inversion_combo.currentData() == 4

        quality_combo.setCurrentIndex(quality_combo.findData("major"))

        # inversion 4 is invalid for major; should clamp to max (2)
        assert inversion_combo.currentData() == 2
