from unittest.mock import patch

import pytest

from tests.ui.timelines.harmony.interact import click_mode_ui
from tests.ui.timelines.harmony.test_harmony_timeline_ui import add_mode
from tests.ui.timelines.interact import click_timeline_ui
from tests.utils import save_and_reopen, undoable
from tilia.requests import Post, post
from tilia.ui import commands
from tilia.ui.timelines.harmony import HarmonyTimelineUI
from tilia.ui.windows.kinds import WindowKind


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
    def test_paste_single_into_timeline(self, tlui):
        tlui.create_mode(0)
        click_mode_ui(tlui[0])
        commands.execute("timeline.component.copy")
        click_timeline_ui(tlui, 10)
        commands.execute("media.seek", 50)
        commands.execute("timeline.component.paste")
        assert len(tlui) == 2
        assert tlui[1].get_data("time") == 50

    def test_paste_multiple_into_timeline(self, tlui):
        tlui.create_mode(0)
        tlui.create_mode(10)
        tlui.create_mode(20)
        click_mode_ui(tlui[0])
        click_mode_ui(tlui[1], modifier="ctrl")
        click_mode_ui(tlui[2], modifier="ctrl")
        commands.execute("timeline.component.copy")
        click_timeline_ui(tlui, 90)
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
        commands.execute("timeline.component.copy")
        click_mode_ui(tlui[1])
        commands.execute("timeline.component.paste")
        assert len(tlui) == 2
        for attr in attributes_to_copy.keys():
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
            click_mode_ui(mui, modifier="ctrl")
        commands.execute("timeline.component.copy")
        click_timeline_ui(tlui, 90)
        click_mode_ui(target_mui)
        commands.execute("timeline.component.paste")
        assert len(tlui) == 6
        for attr in attributes_to_copy.keys():
            assert target_mui.get_data(attr) == attributes_to_copy[attr]


class TestModeFieldInspectorEdit:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def open_inspector_for(self, mode_ui, qtui):
        click_mode_ui(mode_ui)
        commands.execute("timeline.element.inspect")
        return qtui._windows[WindowKind.INSPECT]

    @pytest.mark.parametrize(
        "field_name, attr, new_value",
        [
            # Reading: "set mode tonic" and "set mode step" are treated as
            # separate rows on the manual checklist, but the Inspector
            # has a single note-name combo for a mode ("Step", whose items
            # are note names — i.e. the mode's tonic). No second field or
            # code path distinguishes a "tonic" from a "step" for a mode
            # (tilia/ui/timelines/harmony/elements/mode_attrs.py
            # INSPECTOR_FIELDS has only Step/Accidental/Type/Comments), and
            # a keyboard-arrow-driven "step through values" interaction
            # (the other plausible reading) could not be simulated
            # reliably here: the focused combo loses Qt focus again as
            # soon as the event loop is spun (QApplication.processEvents),
            # even after get(Get.MAIN_WINDOW).show() + setFocus() first
            # made it the real QApplication.focusWidget() — a real window
            # in the running app would keep it, so this looks like a
            # test-harness limitation rather than an app defect, and isn't
            # a sound basis for an xfail. Both rows are treated as this one
            # field, edited by direct selection.
            pytest.param("Step", "step", 3, id="mode-tonic-step"),
            pytest.param("Accidental", "accidental", 1, id="mode-accidental"),
            pytest.param("Type", "type", "dorian", id="mode-type"),
        ],
    )
    def test_combo_field_edit_changes_component_and_ui(
        self, qtui, harmony_tlui, tluis, tmp_path, field_name, attr, new_value
    ):
        add_mode(step=0, accidental=0, type="major")
        mode = harmony_tlui.modes()[0]
        inspector = self.open_inspector_for(mode, qtui)
        combo = inspector.field_name_to_widgets[field_name][1]
        text_before = mode.body.toPlainText()

        with undoable():
            combo.setCurrentIndex(combo.findData(new_value))

        assert mode.get_data(attr) == new_value
        assert mode.body.toPlainText() != text_before

        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)
        save_and_reopen(tmp_path)
        reloaded_tlui = [t for t in tluis if isinstance(t, HarmonyTimelineUI)][0]
        assert reloaded_tlui.modes()[0].get_data(attr) == new_value
