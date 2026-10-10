from unittest.mock import Mock, patch

import pytest

from tests.ui.timelines.harmony.interact import click_harmony_ui
from tests.ui.timelines.harmony.test_harmony_timeline_ui import add_harmony, add_mode
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


class TestChordFieldInspectorEdit:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def open_inspector_for(self, harmony_ui, qtui):
        click_harmony_ui(harmony_ui)
        commands.execute("timeline.element.inspect")
        return qtui._windows[WindowKind.INSPECT]

    @pytest.mark.parametrize(
        "field_name, attr, new_value",
        [
            pytest.param("Accidental", "accidental", -1, id="chord-accidental"),
            pytest.param("Applied to", "applied_to", 2, id="chord-applied-to"),
            pytest.param("Inversion", "inversion", 1, id="chord-inversion"),
            pytest.param("Quality", "quality", "minor", id="chord-quality"),
            pytest.param("Step", "step", 3, id="chord-step"),
            pytest.param(
                "Display mode", "display_mode", "letter", id="chord-display-as"
            ),
        ],
    )
    def test_combo_field_edit_changes_component_and_ui(
        self, qtui, harmony_tlui, tluis, tmp_path, field_name, attr, new_value
    ):
        # Editing the field through the inspector (not set_component_data)
        # changes the component, changes what the body shows, is undoable,
        # and survives save/reopen.
        add_harmony()
        harmony = harmony_tlui.harmonies()[0]
        inspector = self.open_inspector_for(harmony, qtui)
        combo = inspector.field_name_to_widgets[field_name][1]
        text_before = harmony.body.toPlainText()

        with undoable():
            combo.setCurrentIndex(combo.findData(new_value))

        assert harmony.get_data(attr) == new_value
        assert harmony.body.toPlainText() != text_before

        save_and_reopen(tmp_path)
        reloaded_tlui = [t for t in tluis if isinstance(t, HarmonyTimelineUI)][0]
        assert reloaded_tlui.harmonies()[0].get_data(attr) == new_value

    @pytest.mark.parametrize(
        "initial_display_mode, new_display_mode, expect_custom_text",
        [
            pytest.param("roman", "custom", True, id="chord-display-as-custom"),
            pytest.param("custom", "roman", False, id="chord-display-as-not-custom"),
        ],
    )
    def test_display_mode_custom_transitions(
        self,
        qtui,
        harmony_tlui,
        tluis,
        tmp_path,
        initial_display_mode,
        new_display_mode,
        expect_custom_text,
    ):
        # Switching into "custom" shows the custom text verbatim; switching
        # away from "custom" shows the computed label again, not the stale
        # custom text. Each param uses a fresh element so the
        # single inspector-field edit under test stays a single undo entry
        # (two edits to the same field through the same open inspector
        # collapse into one entry — see
        # test_clearing_comments_via_inspector_is_undoable in
        # tests/ui/timelines/range/test_range_timeline_ui.py).
        add_harmony(display_mode=initial_display_mode, custom_text="my custom text")
        harmony = harmony_tlui.harmonies()[0]
        inspector = self.open_inspector_for(harmony, qtui)
        display_combo = inspector.field_name_to_widgets["Display mode"][1]

        with undoable():
            display_combo.setCurrentIndex(display_combo.findData(new_display_mode))

        assert harmony.get_data("display_mode") == new_display_mode
        assert (harmony.body.toPlainText() == "my custom text") == expect_custom_text

        save_and_reopen(tmp_path)
        reloaded_tlui = [t for t in tluis if isinstance(t, HarmonyTimelineUI)][0]
        assert reloaded_tlui.harmonies()[0].get_data("display_mode") == new_display_mode

    @pytest.mark.parametrize(
        "font_type, expected_family",
        [
            pytest.param(
                "analytic",
                "MusAnalysis",
                id="chord-custom-text-font-analytic",
            ),
            pytest.param("normal", "Arial", id="chord-custom-text-font-regular"),
        ],
    )
    def test_custom_text_edit_under_font(
        self, qtui, harmony_tlui, tluis, tmp_path, font_type, expected_family
    ):
        # "font 'regular'" in the checklist is FONT_TYPES's "normal" value
        # (tilia/timelines/harmony/constants.py); the combo has no entry
        # literally spelled "regular".
        add_harmony(
            display_mode="custom",
            custom_text_font_type=font_type,
            custom_text="old text",
        )
        harmony = harmony_tlui.harmonies()[0]
        inspector = self.open_inspector_for(harmony, qtui)
        custom_label_edit = inspector.field_name_to_widgets["Custom label"][1]
        assert harmony.body.font().family() == expected_family

        with undoable():
            custom_label_edit.setText("new custom text")

        assert harmony.get_data("custom_text") == "new custom text"
        assert harmony.body.toPlainText() == "new custom text"
        assert harmony.body.font().family() == expected_family

        save_and_reopen(tmp_path)
        reloaded_tlui = [t for t in tluis if isinstance(t, HarmonyTimelineUI)][0]
        reloaded_harmony = reloaded_tlui.harmonies()[0]
        assert reloaded_harmony.get_data("custom_text") == "new custom text"
        assert reloaded_harmony.body.toPlainText() == "new custom text"

    def test_custom_label_font_combo_changes_body_font(
        self, qtui, harmony_tlui, tluis, tmp_path
    ):
        add_harmony(
            display_mode="custom",
            custom_text_font_type="analytic",
            custom_text="styled text",
        )
        harmony = harmony_tlui.harmonies()[0]
        inspector = self.open_inspector_for(harmony, qtui)
        font_combo = inspector.field_name_to_widgets["Custom label font"][1]
        assert harmony.body.font().family() == "MusAnalysis"

        with undoable():
            font_combo.setCurrentIndex(font_combo.findData("normal"))

        assert harmony.get_data("custom_text_font_type") == "normal"
        assert harmony.body.font().family() == "Arial"

        save_and_reopen(tmp_path)
        reloaded_tlui = [t for t in tluis if isinstance(t, HarmonyTimelineUI)][0]
        assert (
            reloaded_tlui.harmonies()[0].get_data("custom_text_font_type") == "normal"
        )


class TestInvalidInversionInspectorEdit:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def open_inspector_for(self, harmony_ui, qtui):
        click_harmony_ui(harmony_ui)
        commands.execute("timeline.element.inspect")
        return qtui._windows[WindowKind.INSPECT]

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "An invalid inversion is silently discarded with no "
            "user-facing error. tilia/ui/timelines/base/timeline.py "
            "on_inspector_field_edited calls element.set_data(attr, value) "
            "and ignores the (value, success) tuple it returns, so "
            "validate_set_data()==False in "
            "tilia/timelines/base/component/base.py never reaches "
            "errors.display()/Post.DISPLAY_ERROR."
        ),
    )
    def test_invalid_inversion_is_refused_with_error(
        self, qtui, harmony_tlui, tilia_errors
    ):
        add_harmony(quality="major", inversion=0)  # major: valid inversions 0-2
        harmony = harmony_tlui.harmonies()[0]
        self.open_inspector_for(harmony, qtui)

        # The Inversion combo only ever lists valid choices for the current
        # quality, so a real user can't pick an invalid one through it.
        # Post the event the widget would send if it could, to exercise the
        # validation/error path itself.
        post(Post.INSPECTOR_FIELD_EDITED, "Inversion", 9, harmony.id, 0)

        assert harmony.get_data("inversion") == 0  # refused, not applied
        tilia_errors.assert_error()

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "No error is ever shown for an invalid inversion (see "
            "test_invalid_inversion_is_refused_with_error), so the "
            "wording can't be checked either. The historical message read "
            "'...for this letter type', which should say 'chord quality' "
            "instead."
        ),
    )
    def test_invalid_inversion_error_mentions_chord_quality(
        self, qtui, harmony_tlui, tilia_errors
    ):
        add_harmony(quality="major", inversion=0)
        harmony = harmony_tlui.harmonies()[0]
        self.open_inspector_for(harmony, qtui)

        post(Post.INSPECTOR_FIELD_EDITED, "Inversion", 9, harmony.id, 0)

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("chord quality")


class TestDominantSeventhFlatNinth:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def test_inspector_offers_it_after_dominant_seventh(self, qtui, harmony_tlui):
        add_harmony(quality="dominant-seventh-flat-ninth")
        click_harmony_ui(harmony_tlui.harmonies()[0])
        commands.execute("timeline.element.inspect")
        inspector = qtui._windows[WindowKind.INSPECT]

        quality_combo = inspector.field_name_to_widgets["Quality"][1]
        index = quality_combo.findData("dominant-seventh-flat-ninth")
        assert quality_combo.itemData(index - 1) == "dominant-seventh"
        inversion_combo = inspector.field_name_to_widgets["Inversion"][1]
        assert inversion_combo.count() == 4  # inversions 0, 1, 2, 3

    def test_survives_save_and_reopen(self, harmony_tlui, tluis, tmp_path):
        add_harmony(
            quality="dominant-seventh-flat-ninth", inversion=3, display_mode="letter"
        )

        save_and_reopen(tmp_path)

        reloaded_tlui = [t for t in tluis if isinstance(t, HarmonyTimelineUI)][0]
        harmony = reloaded_tlui.harmonies()[0]
        assert harmony.get_data("quality") == "dominant-seventh-flat-ninth"
        assert harmony.get_data("inversion") == 3
        assert harmony.label == "C7((b9))/B`b"


class TestAddedToneQualities:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    @pytest.mark.parametrize(
        "quality, listed_after, inversions",
        [
            (
                "dominant-seventh-added-thirteenth",
                "dominant-seventh-flat-thirteenth",
                3,
            ),
            ("dominant-ninth-sharp-eleventh", "dominant-ninth", 4),
            ("major-added-ninth", "major", 2),
        ],
    )
    def test_inspector_offers_it_after_its_base(
        self, quality, listed_after, inversions, qtui, harmony_tlui
    ):
        add_harmony(quality=quality)
        click_harmony_ui(harmony_tlui.harmonies()[0])
        commands.execute("timeline.element.inspect")
        inspector = qtui._windows[WindowKind.INSPECT]

        quality_combo = inspector.field_name_to_widgets["Quality"][1]
        index = quality_combo.findData(quality)
        assert quality_combo.itemData(index - 1) == listed_after
        inversion_combo = inspector.field_name_to_widgets["Inversion"][1]
        assert inversion_combo.count() == inversions + 1

    @pytest.mark.parametrize(
        "quality",
        [
            "dominant-seventh-sharp-ninth",
            "dominant-seventh-sharp-eleventh",
            "dominant-seventh-flat-thirteenth",
            "dominant-seventh-added-thirteenth",
            "dominant-ninth-sharp-eleventh",
            "major-seventh-sharp-eleventh",
            "major-seventh-added-sixth",
            "major-sixth-added-ninth",
            "minor-sixth-added-ninth",
            "major-added-ninth",
            "minor-added-ninth",
            "minor-seventh-added-eleventh",
        ],
    )
    def test_survives_save_and_reopen(self, quality, harmony_tlui, tluis, tmp_path):
        add_harmony(quality=quality, inversion=1, display_mode="letter")
        label = harmony_tlui.harmonies()[0].label

        save_and_reopen(tmp_path)

        reloaded_tlui = [t for t in tluis if isinstance(t, HarmonyTimelineUI)][0]
        harmony = reloaded_tlui.harmonies()[0]
        assert harmony.get_data("quality") == quality
        assert harmony.get_data("inversion") == 1
        assert harmony.label == label
