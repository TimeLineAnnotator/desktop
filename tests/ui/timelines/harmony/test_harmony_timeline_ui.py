import pytest

import tilia.ui.commands
from tests.mock import Serve
from tests.ui.timelines.harmony.interact import click_harmony_ui
from tilia.requests import Get
from tilia.ui import commands

FLAT_SIGN = "`b"
SHARP_SIGN = "`#"


def add_harmony(time: float | None = None, **kwargs):
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
        if not time:
            tilia.ui.commands.execute("timeline.harmony.add_harmony")
        else:
            tilia.ui.commands.execute("timeline.harmony.add_harmony", time)


def add_mode(time: float | None = None, **kwargs):
    default_params = {
        "step": 0,
        "accidental": 0,
        "type": "major",
        "level": 2,
    }
    default_params.update(kwargs)
    with Serve(Get.FROM_USER_MODE_PARAMS, (True, default_params)):
        if not time:
            tilia.ui.commands.execute("timeline.harmony.add_mode")
        else:
            tilia.ui.commands.execute("timeline.harmony.add_mode", time)


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

    @pytest.mark.parametrize(
        "step,quality,inversion,expected",
        [
            (0, "major", 1, "I6"),
            (0, "major", 2, "I64"),
            (1, "minor-seventh", 0, "ii7"),
            (1, "minor-seventh", 1, "ii65"),
            (4, "dominant-seventh", 1, "V65"),
            (4, "dominant-seventh", 2, "V43"),
            (4, "dominant-seventh", 3, "V42"),
        ],
    )
    def test_roman_label_has_no_blank_accidental_placeholder(
        self, step, quality, inversion, expected, harmony_tlui
    ):
        # "s" marks an accidental slot left blank; MusAnalysis only consumes it
        # inside the three-figure "%" stack, so it must not reach shorter
        # figures, where it would be drawn as a literal letter.
        add_harmony(step=step, quality=quality, inversion=inversion)

        assert harmony_tlui.harmonies()[0].label == expected

    def test_roman_label_keeps_blank_accidental_placeholder_in_stacked_figures(
        self, harmony_tlui
    ):
        add_harmony(step=4, quality="dominant-ninth", inversion=3)

        assert harmony_tlui.harmonies()[0].label == "V%sss432"

    def test_roman_label_for_ninth_chord_high_inversion(self, harmony_tlui):
        # inversion=4 places the 9th in the bass; label is dynamically computed
        add_harmony(
            display_mode="roman", quality="half-diminished-minor-ninth", inversion=4
        )
        label = harmony_tlui.harmonies()[0].label
        assert label  # no crash, non-empty


class TestLetterSymbolLabel:
    def test_no_inversion_has_no_bass_note(self, harmony_tlui):
        add_harmony(display_mode="letter", quality="major")
        assert "/" not in harmony_tlui.harmonies()[0].letter_symbol_label

    def test_first_inversion_shows_third(self, harmony_tlui):
        add_harmony(display_mode="letter", quality="major", inversion=1)
        assert harmony_tlui.harmonies()[0].letter_symbol_label.endswith("/E")

    def test_second_inversion_shows_fifth(self, harmony_tlui):
        add_harmony(display_mode="letter", quality="major", inversion=2)
        assert harmony_tlui.harmonies()[0].letter_symbol_label.endswith("/G")

    def test_seventh_chord_third_inversion_shows_flat_bass(self, harmony_tlui):
        add_harmony(display_mode="letter", quality="dominant-seventh", inversion=3)
        assert harmony_tlui.harmonies()[0].letter_symbol_label.endswith("/B`b")

    def test_ninth_chord_fourth_inversion_shows_ninth(self, harmony_tlui):
        add_harmony(display_mode="letter", quality="dominant-ninth", inversion=4)
        assert harmony_tlui.harmonies()[0].letter_symbol_label.endswith("/D")


class TestModeLabel:
    def test_dorian_label(self, harmony_tlui):
        add_mode(type="dorian")
        assert harmony_tlui.modes()[0].label == "C Dorian"

    def test_phrygian_label(self, harmony_tlui):
        add_mode(type="phrygian")
        assert harmony_tlui.modes()[0].label == "C Phrygian"

    def test_major_still_gives_note_only(self, harmony_tlui):
        add_mode(type="major")
        assert harmony_tlui.modes()[0].label == "C"

    def test_minor_still_gives_lowercase_note(self, harmony_tlui):
        add_mode(type="minor")
        assert harmony_tlui.modes()[0].label == "c"

    def test_dorian_with_flat_tonic(self, harmony_tlui):
        add_mode(step=6, accidental=-1, type="dorian")  # Bb dorian
        assert harmony_tlui.modes()[0].label == "B`b Dorian"


class TestCopyPaste:
    def test_paste_multiple_to_harmony_with_mode_as_first_copied(self, harmony_tlui):
        add_harmony()
        add_mode()
        commands.execute("media.seek", 10)
        add_harmony()

        click_harmony_ui(harmony_tlui.modes()[0])
        click_harmony_ui(harmony_tlui.harmonies()[1], modifier="ctrl")
        commands.execute("timeline.component.copy")

        click_harmony_ui(harmony_tlui.harmonies()[1])
        commands.execute("timeline.component.paste")

        assert len(harmony_tlui) == 5
