import pytest

import tilia.ui.commands
from tests.mock import Serve
from tests.ui.timelines.harmony.interact import click_harmony_ui
from tests.utils import get_command_action
from tilia.requests import Get
from tilia.ui import commands
from tilia.ui.commands import get_qaction

FLAT_SIGN = "`b"
SHARP_SIGN = "`#"

MAJOR = {"step": 0, "accidental": 0, "type": "major"}  # C major
MINOR = {"step": 5, "accidental": 0, "type": "minor"}  # A minor


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
            (1, "minor-seventh", 1, "ii65"),
            (4, "dominant-seventh", 1, "V65"),
            (4, "dominant-seventh", 2, "V43"),
            (4, "dominant-seventh", 3, "V42"),
            # Four figures: more than the "%" stack's three slots, so the whole
            # group falls back to the inline form.
            (0, "half-diminished-13th", 4, "io\\bb7542"),
            # Three figures, but a double accidental needs two characters and
            # overflows its single slot — same fallback.
            (0, "diminished-seventh", 1, "iobbb653"),
        ],
    )
    def test_roman_label_has_no_blank_accidental_placeholder(
        self, step, quality, inversion, expected, harmony_tlui
    ):
        # "s" marks an accidental slot left blank. MusAnalysis consumes it only
        # inside the "%" stack, and only there in its exact shape: three slots
        # of one character each, paired with three numbers. Anywhere else it is
        # drawn as a literal letter next to the numeral.
        add_harmony(step=step, quality=quality, inversion=inversion)

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "step,accidental,quality,inversion",
        [
            (6, 0, "major", 1),  # figures (6, None), (3, "#")
            (0, 0, "augmented", 1),  # figures (6, None), (3, "#")
            (1, -1, "major", 2),  # figures (6, None), (4, "-")
            (0, 0, "dominant-seventh", 1),  # figures (6, None), (5, "-")
            (0, 0, "half-diminished-13th", 4),  # four figures
            (0, 0, "diminished-seventh", 1),  # double accidental
        ],
    )
    def test_roman_label_has_no_literal_s_when_figures_carry_accidentals(
        self, step, accidental, quality, inversion, harmony_tlui
    ):
        # A partially accidented figure group is the case the placeholder rule
        # is easiest to get wrong: dropping the blank slot only for fully
        # diatonic groups would leave the letter in every one of these.
        # Asserting on the absence of "s" rather than on the exact string keeps
        # this test independent of how the accidentals end up positioned.
        add_harmony(
            step=step, accidental=accidental, quality=quality, inversion=inversion
        )

        assert "s" not in harmony_tlui.harmonies()[0].label

    def test_roman_label_keeps_blank_accidental_placeholder_in_stacked_figures(
        self, harmony_tlui
    ):
        add_harmony(step=4, quality="dominant-ninth", inversion=3)

        assert harmony_tlui.harmonies()[0].label == "V%sss432"

    def test_roman_label_keeps_stack_when_only_some_figures_are_accidented(
        self, harmony_tlui
    ):
        # Three figures, one accidental, all single-character: still the exact
        # shape the "%" stack takes, so the two blank slots must be kept.
        add_harmony(step=6, quality="dominant-seventh", inversion=1)

        assert harmony_tlui.harmonies()[0].label == "VII%ss#653"

    def test_roman_label_for_ninth_chord_high_inversion(self, harmony_tlui):
        # inversion=4 places the 9th in the bass; label is dynamically computed
        add_harmony(
            display_mode="roman", quality="half-diminished-minor-ninth", inversion=4
        )
        label = harmony_tlui.harmonies()[0].label
        assert label  # no crash, non-empty

    @pytest.mark.parametrize(
        "mode,step,accidental,quality,expected",
        [
            (MAJOR, 0, 0, "major-seventh", "I7"),  # Cmaj7
            (MAJOR, 3, 0, "major-seventh", "IV7"),  # Fmaj7
            (MAJOR, 0, 0, "major-13th", "I13"),  # Cmaj13
            (MINOR, 3, 0, "major-seventh", "VI7"),  # Fmaj7
            (MINOR, 0, 0, "major-seventh", "III7"),  # Cmaj7
            (MINOR, 5, 0, "minor-major-seventh", "i#7"),  # Am(maj7): G# not in key
            (MAJOR, 4, 0, "dominant-seventh", "V7"),  # G7
            (MAJOR, 0, 0, "dominant-seventh", "Ib7"),  # C7: Bb not in key
            (MAJOR, 0, 0, "half-diminished-minor-ninth", "io\\b9"),  # Db not in key
            (MAJOR, 6, 0, "half-diminished-minor-ninth", "viio\\9"),  # C in key
        ],
    )
    def test_root_position_figure_is_the_extension_as_the_key_gives_it(
        self, mode, step, accidental, quality, expected, harmony_tlui
    ):
        # As in the inversions' figures, the number stands for the interval
        # above the bass that the key gives, so a seventh that is in the key
        # needs no mark and one that isn't takes an accidental.
        add_mode(**mode)
        add_harmony(step=step, accidental=accidental, quality=quality)

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "mode,step,accidental,expected",
        [
            (MAJOR, 6, 0, "viio7"),  # Bo7: Ab not in key
            (MAJOR, 3, 1, "`#ivo7"),  # F#o7: Eb not in key
            (MINOR, 4, 1, "`#viio7"),  # G#o7: F in key
        ],
    )
    def test_fully_diminished_seventh_figure_has_no_accidental(
        self, mode, step, accidental, expected, harmony_tlui
    ):
        # The ° already says the seventh is diminished, so vii°7 in a major key
        # reads viio7, as textbooks write it, not viiob7.
        add_mode(**mode)
        add_harmony(step=step, accidental=accidental, quality="diminished-seventh")

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "quality",
        [
            "major-seventh",
            "minor-major-seventh",
            "augmented-major-seventh",
            "minor-major-ninth",
            "augmented-major-ninth",
            "augmented-dominant-ninth",
            "major-11th",
            "major-13th",
            "minor-major-13th",
        ],
    )
    def test_root_position_has_no_major_seventh_triangle(self, quality, harmony_tlui):
        # The triangle ("^^") is chord-symbol notation (C△7); a Roman numeral
        # shows the same seventh with its figure.
        add_harmony(quality=quality)

        assert "^^" not in harmony_tlui.harmonies()[0].label

    @pytest.mark.parametrize("inversion,expected", [(1, "I65"), (2, "I43"), (3, "I42")])
    def test_major_seventh_inversions_show_plain_figures(
        self, inversion, expected, harmony_tlui
    ):
        add_harmony(quality="major-seventh", inversion=inversion)

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "step,accidental,quality,applied_to,expected",
        [
            (0, 0, "dominant-seventh", 3, "V7/IV"),  # C7: Bb is in F major
            (3, 1, "diminished-seventh", 4, "viio7/V"),  # F#o7
        ],
    )
    def test_applied_chord_root_position_figure_has_no_accidental(
        self, step, accidental, quality, applied_to, expected, harmony_tlui
    ):
        # Like the numeral, the figure would need the key the chord is applied
        # to; measured against the main key, V7/IV would read Vb7/IV.
        add_harmony(
            step=step, accidental=accidental, quality=quality, applied_to=applied_to
        )

        assert harmony_tlui.harmonies()[0].label == expected


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


class TestTimelineUIContextMenu:
    def test_has_no_height_set_action(self, harmony_tlui, tluis):
        context_menu = harmony_tlui.CONTEXT_MENU_CLASS(harmony_tlui, 0, 0)

        assert get_qaction("timeline.set_height") not in context_menu.actions()


class TestAddAtExistingTime:
    def test_add_harmony_at_same_time_shows_error(self, harmony_tlui, tilia_errors):
        add_harmony(0)
        add_harmony(0)

        assert len(harmony_tlui.harmonies()) == 1
        tilia_errors.assert_error()

    def test_add_mode_at_same_time_shows_error(self, harmony_tlui, tilia_errors):
        add_mode(0)
        add_mode(0)

        assert len(harmony_tlui.modes()) == 1
        tilia_errors.assert_error()


class TestKeysRowVisibility:
    """Toggling the keys row (via the harmony timeline's own
    context menu) should reposition timelines below the harmony timeline in
    both directions -- hiding and showing the row."""

    @staticmethod
    def get_context_menu(harmony_tlui):
        return harmony_tlui.CONTEXT_MENU_CLASS(harmony_tlui, 0, 0)

    def test_hide_keys_moves_timelines_below_up(self, harmony_tlui, tluis):
        commands.execute("timelines.add.marker", name="")
        marker_tlui = tluis[1]
        y_before = marker_tlui.view.y()

        context_menu = self.get_context_menu(harmony_tlui)
        hide_keys_action = get_command_action(
            context_menu, "timeline.harmony.hide_keys"
        )
        assert hide_keys_action.isVisible()
        hide_keys_action.trigger()

        assert marker_tlui.view.y() < y_before

    def test_show_keys_moves_timelines_below_down(self, harmony_tlui, tluis):
        commands.execute("timelines.add.marker", name="")
        marker_tlui = tluis[1]

        hide_menu = self.get_context_menu(harmony_tlui)
        get_command_action(hide_menu, "timeline.harmony.hide_keys").trigger()
        y_after_hide = marker_tlui.view.y()

        show_menu = self.get_context_menu(harmony_tlui)
        show_keys_action = get_command_action(show_menu, "timeline.harmony.show_keys")
        assert show_keys_action.isVisible()
        show_keys_action.trigger()

        assert marker_tlui.view.y() > y_after_hide
