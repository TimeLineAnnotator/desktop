import pytest

import tilia.ui.actions
from tests.mock import Serve
from tests.ui.timelines.harmony.interact import click_harmony_ui
from tilia.requests import Get

FLAT_SIGN = "`b"
SHARP_SIGN = "`#"


def add_harmony(**kwargs):
    default_params = {
        "step": 0,
        "accidental": 0,
        "inversion": 0,
        "quality": "major",
        "applied_to": 0,
        "display_mode": "roman",
        "level": 1,
    }
    default_params.update(kwargs)
    with Serve(Get.FROM_USER_HARMONY_PARAMS, (True, default_params)):
        tilia.ui.actions.trigger("harmony_add")


def add_mode(**kwargs):
    default_params = {
        "step": 0,
        "accidental": 0,
        "type": "major",
        "level": 2,
    }
    default_params.update(kwargs)
    with Serve(Get.FROM_USER_MODE_PARAMS, (True, default_params)):
        tilia.ui.actions.trigger("mode_add")


class TestRomanNumeralDisplay:
    @pytest.mark.parametrize(
        "accidental,accidental_label", [(1, "`#"), (0, ""), (-1, "`b")]
    )
    def test_roman_label_start_with_accidental(
        self, accidental, accidental_label, harmony_tlui
    ):
        add_harmony(accidental=accidental)

        assert harmony_tlui[0].label.startswith(accidental_label)

    @pytest.mark.parametrize(
        "harmony_step,harmony_accidental,expected_start",
        [
            (1, -2, FLAT_SIGN),  # Dbb
            (1, -1, "I"),  # Db
            (1, 0, SHARP_SIGN),  # D
            (5, -2, FLAT_SIGN),  # Abb
            (5, -1, "V"),  # Ab
            (5, 0, SHARP_SIGN),  # A
        ],
    )
    def test_roman_label_does_not_start_with_accidental_when_root_is_diatonic_flat_major_key(
        self, harmony_step, harmony_accidental, expected_start, harmony_tlui
    ):
        add_mode(step=1, accidental=-1, type="major")  # Db major
        add_harmony(step=harmony_step, accidental=harmony_accidental)

        assert harmony_tlui[0].label.startswith(expected_start)

    @pytest.mark.parametrize(
        "harmony_step,harmony_accidental,expected_start",
        [
            (6, -2, FLAT_SIGN),  # Bbb
            (6, -1, "I"),  # Bb
            (6, 0, SHARP_SIGN),  # B
            (3, -1, FLAT_SIGN),  # Fb
            (3, 0, "V"),  # F
            (3, 1, SHARP_SIGN),  # F#
        ],
    )
    def test_roman_label_does_not_start_with_accidental_when_root_is_diatonic_flat_minor_key(
        self, harmony_step, harmony_accidental, expected_start, harmony_tlui
    ):
        add_mode(step=6, accidental=-1, type="minor")  # Bb minor
        add_harmony(step=harmony_step, accidental=harmony_accidental)

        assert harmony_tlui[0].label.startswith(expected_start)

    @pytest.mark.parametrize(
        "harmony_step,harmony_accidental,expected_start",
        [
            (6, -1, FLAT_SIGN),  # Bb
            (6, 0, "I"),  # B
            (6, 1, SHARP_SIGN),  # B#
            (3, 0, FLAT_SIGN),  # F
            (3, 1, "V"),  # F#
            (3, 2, SHARP_SIGN),  # F##
        ],
    )
    def test_roman_label_does_not_start_with_accidental_when_root_is_diatonic_sharp_major_key(
        self, harmony_step, harmony_accidental, expected_start, harmony_tlui
    ):
        add_mode(step=6, accidental=0, type="major")  # B major
        add_harmony(step=harmony_step, accidental=harmony_accidental)

        assert harmony_tlui[0].label.startswith(expected_start)

    @pytest.mark.parametrize(
        "harmony_step,harmony_accidental,expected_start",
        [
            (0, 0, FLAT_SIGN),  # C
            (0, 1, "I"),  # C#
            (0, 2, SHARP_SIGN),  # C##
            (4, 0, FLAT_SIGN),  # G
            (4, 1, "V"),  # G#
            (4, 2, SHARP_SIGN),  # G##
        ],
    )
    def test_roman_label_does_not_start_with_accidental_when_root_is_diatonic_sharp_minor_key(
        self, harmony_step, harmony_accidental, expected_start, harmony_tlui
    ):
        add_mode(step=0, accidental=1, type="minor")  # C# minor
        add_harmony(step=harmony_step, accidental=harmony_accidental)

        assert harmony_tlui[0].label.startswith(expected_start)


class TestCopyPaste:
    def test_paste_multiple_to_harmony_with_mode_as_first_copied(
        self, tilia_state, harmony_tlui, user_actions
    ):
        add_harmony()
        add_mode()
        tilia_state.current_time = 10
        add_harmony()

        click_harmony_ui(harmony_tlui.modes()[0])
        click_harmony_ui(harmony_tlui.harmonies()[1], modifier="ctrl")
        user_actions.trigger("timeline_element_copy")

        click_harmony_ui(harmony_tlui.harmonies()[1])
        user_actions.trigger("timeline_element_paste")

        assert len(harmony_tlui) == 5
