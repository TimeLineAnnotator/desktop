import pytest

import tilia.ui.actions
from tests.mock import Serve
from tilia.requests import Get
from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.harmony.constants import INT_TO_ACCIDENTAL

FLAT_SIGN = INT_TO_ACCIDENTAL[-1]
SHARP_SIGN = INT_TO_ACCIDENTAL[1]


class TestRomanNumeralDisplay:
    @staticmethod
    def _add_harmony(**kwargs):
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
            tilia.ui.actions.trigger(TiliaAction.HARMONY_ADD)

    @staticmethod
    def _add_mode(**kwargs):
        default_params = {
            "step": 0,
            "accidental": 0,
            "type": "major",
            "level": 2,
        }
        default_params.update(kwargs)
        with Serve(Get.FROM_USER_MODE_PARAMS, (True, default_params)):
            tilia.ui.actions.trigger(TiliaAction.MODE_ADD)

    @pytest.mark.parametrize(
        "accidental,accidental_label", [(1, "♯"), (0, ""), (-1, "♭")]
    )
    def test_roman_label_start_with_accidental(
        self, accidental, accidental_label, harmony_tlui
    ):
        self._add_harmony(accidental=accidental)

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
        self._add_mode(step=1, accidental=-1, type="major")  # Db major
        self._add_harmony(step=harmony_step, accidental=harmony_accidental)

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
        self._add_mode(step=6, accidental=-1, type="minor")  # Bb minor
        self._add_harmony(step=harmony_step, accidental=harmony_accidental)

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
        self._add_mode(step=6, accidental=0, type="major")  # B major
        self._add_harmony(step=harmony_step, accidental=harmony_accidental)

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
        self._add_mode(step=0, accidental=1, type="minor")  # C# minor
        self._add_harmony(step=harmony_step, accidental=harmony_accidental)

        assert harmony_tlui[0].label.startswith(expected_start)
