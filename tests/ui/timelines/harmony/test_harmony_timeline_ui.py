import pytest

import tilia.ui.commands
from tests.mock import Serve
from tests.ui.timelines.harmony.interact import (
    click_harmony_ui,
    click_mode_ui,
    label_as_typed,
    numeral_part,
)
from tests.utils import get_command_action, get_command_names, undoable
from tilia.requests import Get
from tilia.ui import commands
from tilia.ui.commands import get_qaction
from tilia.ui.dialogs.harmony_params import SelectHarmonyParams
from tilia.ui.timelines.harmony.constants import QUALITY_TO_ABBREVIATION

FLAT_SIGN = "`b"
SHARP_SIGN = "`#"

MAJOR = {"step": 0, "accidental": 0, "type": "major"}  # C major
MINOR = {"step": 5, "accidental": 0, "type": "minor"}  # A minor
D_MINOR = {"step": 1, "accidental": 0, "type": "minor"}
EB_MINOR = {"step": 2, "accidental": -1, "type": "minor"}
FS_MINOR = {"step": 3, "accidental": 1, "type": "minor"}


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
            (6, "augmented-seventh", 1, "VII##653"),
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
            (6, 0, "augmented-seventh", 1),  # double accidental
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
        "mode,step,accidental,quality,expected",
        [
            (MINOR, 4, 1, "major-seventh", "`#VII^x7"),  # G#maj7: F## for F
            (MAJOR, 0, -1, "dominant-seventh", "`bIb\u200cb7"),  # Cb7: Bbb for B
        ],
    )
    def test_root_position_figure_double_accidental_is_drawn_raised(
        self, mode, step, accidental, quality, expected, harmony_tlui
    ):
        # MusAnalysis raises a lone "#" or "b" beside the figure, but reads "##"
        # or "bb" as the accidentals of a two-figure stack and drops the second
        # one below the first.
        add_mode(**mode)
        add_harmony(step=step, accidental=accidental, quality=quality)

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "mode,step,accidental,inversion,expected",
        [
            (MAJOR, 6, 0, 0, "viio7"),  # Bo7: Ab not in key
            (MAJOR, 6, 0, 1, "viio65"),
            (MAJOR, 6, 0, 2, "viio43"),
            (MAJOR, 6, 0, 3, "viio42"),  # Ab in the bass
            (MAJOR, 0, 0, 1, "io%ssb653"),  # Co7: its fifth, Gb, keeps the flat
            (MAJOR, 3, 1, 0, "`#ivo7"),  # F#o7: Eb not in key
            (MINOR, 4, 1, 0, "viio7"),  # G#o7: F in key
        ],
    )
    def test_fully_diminished_seventh_figure_has_no_accidental(
        self, mode, step, accidental, inversion, expected, harmony_tlui
    ):
        # The ° already says the seventh is diminished, so vii°7 in a major key
        # reads viio7 and viio65, as textbooks write them, not viiob7 and
        # viiob65.
        add_mode(**mode)
        add_harmony(
            step=step,
            accidental=accidental,
            quality="diminished-seventh",
            inversion=inversion,
        )

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


# In a minor key, the case of a numeral on the sixth or seventh degree chooses
# the degree, as in music21's RomanNumeral: vi and vii (minor, diminished,
# half-diminished) are the raised degrees, VI and VII (major, augmented) the
# natural ones, and an accidental moves the degree from there.
MINOR_KEY_SIXTH_AND_SEVENTH_LABELS = [
    # A minor
    (MINOR, 4, 1, "diminished-seventh", "viio7"),  # G#o7
    (MINOR, 4, 1, "diminished", "viio"),  # G#o
    (MINOR, 3, 1, "minor", "vi"),  # F#m
    (MINOR, 3, 1, "diminished", "vio"),  # F#o
    (MINOR, 4, 1, "major", "`#VII"),  # G#
    (MINOR, 3, 0, "major", "VI"),  # F
    (MINOR, 4, 0, "major", "VII"),  # G
    (MINOR, 4, 0, "minor", "`bvii"),  # Gm
    (MINOR, 3, 0, "minor", "`bvi"),  # Fm
    # Eb minor, whose natural sixth is Cb and natural seventh Db
    (EB_MINOR, 0, 0, "major", "`#VI"),  # C
    (EB_MINOR, 0, -1, "major", "VI"),  # Cb
    (EB_MINOR, 0, 0, "minor", "vi"),  # Cm
    (EB_MINOR, 0, -1, "minor", "`bvi"),  # Cbm
    (EB_MINOR, 1, 0, "major", "`#VII"),  # D
    (EB_MINOR, 1, -1, "major", "VII"),  # Db
    (EB_MINOR, 1, 0, "diminished-seventh", "viio7"),  # Do7
    (EB_MINOR, 1, -1, "minor", "`bvii"),  # Dbm
    # F# minor, whose natural sixth is D and natural seventh E
    (FS_MINOR, 1, 1, "minor", "vi"),  # D#m
    (FS_MINOR, 1, 0, "major", "VI"),  # D
    (FS_MINOR, 1, 1, "major", "`#VI"),  # D#
    (FS_MINOR, 1, 0, "minor", "`bvi"),  # Dm
    (FS_MINOR, 2, 1, "diminished-seventh", "viio7"),  # E#o7
    (FS_MINOR, 2, 0, "major", "VII"),  # E
    (FS_MINOR, 2, 1, "major", "`#VII"),  # E#
    (FS_MINOR, 2, 0, "minor", "`bvii"),  # Em
]


class TestRomanNumeralInMinorKeys:
    @pytest.mark.parametrize(
        "mode,step,accidental,quality,expected", MINOR_KEY_SIXTH_AND_SEVENTH_LABELS
    )
    def test_sixth_and_seventh_degrees(
        self, mode, step, accidental, quality, expected, harmony_tlui
    ):
        add_mode(**mode)
        add_harmony(step=step, accidental=accidental, quality=quality)

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "mode,step,accidental,quality,_label", MINOR_KEY_SIXTH_AND_SEVENTH_LABELS
    )
    def test_label_typed_in_its_key_gives_the_same_chord(
        self, mode, step, accidental, quality, _label, harmony_tlui
    ):
        add_mode(**mode)
        add_harmony(step=step, accidental=accidental, quality=quality)
        drawn = harmony_tlui.harmonies()[0].label

        dialog = SelectHarmonyParams(harmony_tlui.get_key_by_time(0))
        dialog.line_edit.setText(label_as_typed(drawn))
        assert dialog.populate_from_text()

        result = dialog.get_result()
        assert (result["step"], result["accidental"], result["quality"]) == (
            step,
            accidental,
            quality,
        )

    @pytest.mark.parametrize(
        "mode,step,accidental",
        [(MINOR, 4, 1), (FS_MINOR, 2, 1), (EB_MINOR, 1, 0)],  # G#o7, E#o7, Do7
    )
    @pytest.mark.parametrize(
        "inversion,expected",
        [(0, "viio7"), (1, "viio65"), (2, "viio43"), (3, "viio42")],
    )
    def test_leading_tone_seventh_figures_have_no_accidental(
        self, mode, step, accidental, inversion, expected, harmony_tlui
    ):
        # The numeral's case and the ° already say that the root is the raised
        # seventh, so the figures do not mark it again.
        add_mode(**mode)
        add_harmony(
            step=step,
            accidental=accidental,
            quality="diminished-seventh",
            inversion=inversion,
        )
        label = harmony_tlui.harmonies()[0].label

        dialog = SelectHarmonyParams(harmony_tlui.get_key_by_time(0))
        dialog.line_edit.setText(label_as_typed(label))
        assert dialog.populate_from_text()
        result = dialog.get_result()

        assert label == expected
        assert (
            result["step"],
            result["accidental"],
            result["quality"],
            result["inversion"],
        ) == (step, accidental, "diminished-seventh", inversion)

    # A root, third or fifth that is the raised sixth or seventh of a minor key
    # gets no accidental on its figure: the numeral's case, the quality symbol
    # (° or +) or the major V already says so.
    @pytest.mark.parametrize(
        "mode,step,accidental,quality,inversion,expected",
        [
            # E is V in A minor, and G# is its third
            (MINOR, 2, 0, "major", 1, "V6"),
            (MINOR, 2, 0, "major", 2, "V64"),
            (MINOR, 2, 0, "dominant-seventh", 1, "V65"),
            (MINOR, 2, 0, "dominant-seventh", 2, "V43"),
            (MINOR, 2, 0, "dominant-seventh", 3, "V42"),
            # G#o and F#o: the root is the raised seventh or sixth
            (MINOR, 4, 1, "diminished", 1, "viio6"),
            (MINOR, 4, 1, "diminished", 2, "viio64"),
            (MINOR, 3, 1, "diminished", 1, "vio6"),
            (MINOR, 3, 1, "diminished", 2, "vio64"),
            (MINOR, 3, 1, "diminished-seventh", 1, "vio65"),
            (MINOR, 3, 1, "diminished-seventh", 2, "vio43"),
            (MINOR, 3, 1, "diminished-seventh", 3, "vio42"),
            # C+: G# is its fifth
            (MINOR, 0, 0, "augmented", 1, "III+6"),
            (MINOR, 0, 0, "augmented", 2, "III+64"),
            # Bm7: F# is its fifth. With it no longer marked, the third
            # inversion is the usual 4/2, not 6/2.
            (MINOR, 6, 0, "minor-seventh", 3, "ii42"),
            # The same in other minor keys
            (D_MINOR, 5, 0, "major", 1, "V6"),  # A: C# is its third
            (D_MINOR, 5, 0, "major", 2, "V64"),
            (EB_MINOR, 6, -1, "dominant-seventh", 1, "V65"),  # Bb7: D
            (EB_MINOR, 6, -1, "dominant-seventh", 2, "V43"),
            (EB_MINOR, 6, -1, "dominant-seventh", 3, "V42"),
            (FS_MINOR, 0, 1, "dominant-seventh", 1, "V65"),  # C#7: E#
            (FS_MINOR, 0, 1, "dominant-seventh", 2, "V43"),
            (FS_MINOR, 0, 1, "dominant-seventh", 3, "V42"),
        ],
    )
    def test_raised_sixth_or_seventh_in_a_triad_tone_has_no_figure_accidental(
        self, mode, step, accidental, quality, inversion, expected, harmony_tlui
    ):
        add_mode(**mode)
        add_harmony(
            step=step, accidental=accidental, quality=quality, inversion=inversion
        )

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "mode,step,accidental",
        [
            (MINOR, 4, 1),  # G#o/7: F# is its seventh
            (D_MINOR, 0, 1),  # C#o/7: B
            (EB_MINOR, 1, 0),  # Do/7: C
            (FS_MINOR, 2, 1),  # E#o/7: D#
        ],
    )
    @pytest.mark.parametrize(
        "inversion,expected",
        [(0, "viio\\7"), (1, "viio\\65"), (2, "viio\\43"), (3, "viio\\42")],
    )
    def test_half_diminished_seventh_has_no_figure_accidental_for_a_raised_sixth(
        self, mode, step, accidental, inversion, expected, harmony_tlui
    ):
        # The ø already says that the seventh is minor, as the ° says that a
        # fully diminished seventh is diminished. In a minor key, that seventh
        # is the raised sixth.
        add_mode(**mode)
        add_harmony(
            step=step,
            accidental=accidental,
            quality="half-diminished-seventh",
            inversion=inversion,
        )

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "step,accidental,quality,expected",
        [
            # The accidental tells a major seventh from a minor one.
            (5, 0, "minor-major-seventh", "i#7"),
            # No symbol says that G#m7's seventh, F#, is not F.
            (4, 1, "minor-seventh", "vii#7"),
            # And the major ninth, F#, from the flat ninth, F.
            (2, 0, "dominant-ninth", "V#9"),
        ],
    )
    def test_seventh_and_ninth_keep_their_figure_accidental(
        self, step, accidental, quality, expected, harmony_tlui
    ):
        add_mode(**MINOR)
        add_harmony(step=step, accidental=accidental, quality=quality)

        assert harmony_tlui.harmonies()[0].label == expected

    def test_raised_tone_on_another_degree_keeps_its_figure_accidental(
        self, harmony_tlui
    ):
        # A major in A minor: its third, C#, is raised too, but it is the third
        # degree, which the numeral's case does not account for.
        add_mode(**MINOR)
        add_harmony(step=5, inversion=2)

        assert harmony_tlui.harmonies()[0].label == "I#64"

    @pytest.mark.parametrize(
        "mode,quality,inversion,expected",
        [
            # G# is not in C major or A dorian, and the key says nothing of it.
            (MAJOR, "major", 2, "III#64"),
            (MAJOR, "dominant-seventh", 2, "III%#ss643"),
            ({"step": 5, "accidental": 0, "type": "dorian"}, "major", 2, "V#64"),
            (
                {"step": 5, "accidental": 0, "type": "dorian"},
                "dominant-seventh",
                2,
                "V%#ss643",
            ),
        ],
    )
    def test_figure_accidental_stays_outside_a_minor_key(
        self, mode, quality, inversion, expected, harmony_tlui
    ):
        add_mode(**mode)
        add_harmony(step=2, quality=quality, inversion=inversion)  # E

        assert harmony_tlui.harmonies()[0].label == expected

    # The case a quality gets is the one it got before: lower-case for the
    # qualities whose name starts with minor, diminished or half-diminished,
    # upper-case for the others, including the suspended chords, the power
    # chord, the pedal and the Tristan chord.
    @pytest.mark.parametrize(
        "quality",
        [
            "minor",
            "minor-seventh",
            "minor-major-seventh",
            "minor-sixth",
            "diminished",
            "diminished-seventh",
            "half-diminished-seventh",
        ],
    )
    @pytest.mark.parametrize(
        "step,accidental,expected",
        [
            (4, 1, "vii"),
            (4, 0, "`bvii"),
            (3, 1, "vi"),
            (3, 0, "`bvi"),
        ],
    )
    def test_lower_case_qualities_start_from_the_raised_degree(
        self, quality, step, accidental, expected, harmony_tlui
    ):
        add_mode(**MINOR)
        add_harmony(step=step, accidental=accidental, quality=quality)

        assert numeral_part(harmony_tlui.harmonies()[0].label) == expected

    @pytest.mark.parametrize(
        "quality",
        [
            "major",
            "dominant-seventh",
            "major-seventh",
            "major-sixth",
            "augmented",
            "augmented-seventh",
            "seventh-flat-five",
            "suspended-second",
            "suspended-fourth",
            "suspended-fourth-seventh",
            "power",
            "pedal",
            "Tristan",
        ],
    )
    @pytest.mark.parametrize(
        "step,accidental,expected",
        [
            (4, 1, "`#VII"),
            (4, 0, "VII"),
            (3, 1, "`#VI"),
            (3, 0, "VI"),
        ],
    )
    def test_upper_case_qualities_start_from_the_natural_degree(
        self, quality, step, accidental, expected, harmony_tlui
    ):
        add_mode(**MINOR)
        add_harmony(step=step, accidental=accidental, quality=quality)

        assert numeral_part(harmony_tlui.harmonies()[0].label) == expected

    @pytest.mark.parametrize(
        "quality,expected",
        [
            ("Italian", "It6+"),
            ("French", "Fr6+"),
            ("German", "Gr6+"),
            ("Neapolitan", "N6"),
        ],
    )
    def test_chords_with_a_fixed_label_have_no_numeral_to_change(
        self, quality, expected, harmony_tlui
    ):
        add_mode(**MINOR)
        add_harmony(step=4, accidental=1, quality=quality)

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "step,accidental,quality,expected",
        [
            (5, 0, "minor", "i"),
            (5, 0, "major", "I"),
            (5, 1, "major", "`#I"),
            (6, 0, "diminished", "iio"),
            (0, 0, "major", "III"),
            (0, -1, "major", "`bIII"),
            (0, 0, "minor", "iii"),
            (1, 0, "minor", "iv"),
            (1, 1, "minor", "`#iv"),
            (2, 0, "major", "V"),
            (2, 1, "major", "`#V"),
            (2, 0, "minor", "v"),
        ],
    )
    def test_other_degrees_are_measured_against_the_key(
        self, step, accidental, quality, expected, harmony_tlui
    ):
        add_mode(**MINOR)
        add_harmony(step=step, accidental=accidental, quality=quality)

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize("applied_to", [1, 3, 4, 6])
    @pytest.mark.parametrize(
        "step,accidental,quality",
        [
            (3, 0, "major"),
            (3, 1, "minor"),
            (4, 0, "minor"),
            (4, 1, "major"),
            (4, 1, "diminished-seventh"),
        ],
    )
    def test_applied_chord_has_no_accidental_prefix(
        self, step, accidental, quality, applied_to, harmony_tlui
    ):
        add_mode(**MINOR)
        add_harmony(
            step=step, accidental=accidental, quality=quality, applied_to=applied_to
        )

        assert not harmony_tlui.harmonies()[0].label.startswith("`")

    @pytest.mark.parametrize(
        "step,accidental,quality,expected",
        [
            (4, 0, "minor", "vii"),  # Gm: the seventh of A dorian is G
            (3, 1, "minor", "vi"),  # F#m: its sixth is F#
            (3, 1, "diminished", "vio"),
            (4, 0, "major", "VII"),
            (4, 1, "major", "`#VII"),
        ],
    )
    def test_dorian_key_is_measured_against_the_key(
        self, step, accidental, quality, expected, harmony_tlui
    ):
        # Only a minor key has a raised sixth and seventh.
        add_mode(step=5, accidental=0, type="dorian")
        add_harmony(step=step, accidental=accidental, quality=quality)

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "step,accidental,quality,expected",
        [
            (3, 1, "minor", "vi"),  # F#m
            (4, 1, "diminished", "viio"),  # G#o
            (4, 1, "minor", "vii"),  # G#m
            (4, 0, "major", "`bVII"),  # G
            (4, 0, "minor", "`bvii"),  # Gm
            (3, 0, "major", "`bVI"),  # F
        ],
    )
    def test_major_key_is_measured_against_the_key(
        self, step, accidental, quality, expected, harmony_tlui
    ):
        add_mode(step=5, accidental=0, type="major")  # A major
        add_harmony(step=step, accidental=accidental, quality=quality)

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

    def test_major_seventh_shows_triangle(self, harmony_tlui):
        add_harmony(display_mode="letter", quality="major-seventh")
        assert harmony_tlui.harmonies()[0].letter_symbol_label == "C^^7"

    def test_major_seventh_inversion_shows_triangle(self, harmony_tlui):
        add_harmony(display_mode="letter", quality="major-seventh", inversion=1)
        assert harmony_tlui.harmonies()[0].letter_symbol_label == "C^^7/E"

    def test_major_seventh_with_flat_root_shows_triangle(self, harmony_tlui):
        add_harmony(
            display_mode="letter", step=6, accidental=-1, quality="major-seventh"
        )
        assert harmony_tlui.harmonies()[0].letter_symbol_label == "B`b^^7"

    @pytest.mark.parametrize("quality", sorted(QUALITY_TO_ABBREVIATION))
    def test_no_quality_spells_out_its_major_seventh(self, harmony_tlui, quality):
        add_harmony(display_mode="letter", quality=quality)
        label = harmony_tlui.harmonies()[0].letter_symbol_label
        assert "maj" not in label
        assert "M" not in label


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


class TestElementContextMenu:
    def test_harmony_menu_has_cut(self, harmony_tlui):
        add_harmony()
        harmony = harmony_tlui.harmonies()[0]
        menu = harmony.CONTEXT_MENU_CLASS(harmony)
        assert "timeline.component.cut" in get_command_names(menu)

    def test_mode_menu_has_cut(self, harmony_tlui):
        add_mode()
        mode = harmony_tlui.modes()[0]
        menu = mode.CONTEXT_MENU_CLASS(mode)
        assert "timeline.component.cut" in get_command_names(menu)

    def test_cut_harmony(self, harmony_tlui):
        add_harmony()
        harmony = harmony_tlui.harmonies()[0]
        click_harmony_ui(harmony)

        menu = harmony.CONTEXT_MENU_CLASS(harmony)
        with undoable():
            get_command_action(menu, "timeline.component.cut").trigger()

        assert harmony_tlui.harmonies() == []

    def test_cut_mode(self, harmony_tlui):
        add_mode()
        mode = harmony_tlui.modes()[0]
        click_mode_ui(mode)

        menu = mode.CONTEXT_MENU_CLASS(mode)
        with undoable():
            get_command_action(menu, "timeline.component.cut").trigger()

        assert harmony_tlui.modes() == []


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


class TestDominantSeventhFlatNinthLabel:
    # The dominant seventh's label, then the flat ninth in raised parentheses.
    @pytest.mark.parametrize(
        "inversion, figure", [(0, "7"), (1, "65"), (2, "43"), (3, "42")]
    )
    def test_roman(self, inversion, figure, harmony_tlui):
        add_harmony(step=4, quality="dominant-seventh-flat-ninth", inversion=inversion)

        assert harmony_tlui.harmonies()[0].label == f"V{figure}((b9))"

    @pytest.mark.parametrize("inversion", [0, 1, 2, 3])
    def test_roman_in_minor_has_the_dominant_sevenths_figures(
        self, inversion, harmony_tlui
    ):
        # In A minor, E7's figures show its raised third, G sharp.
        add_mode(**MINOR)
        add_harmony(1, step=2, quality="dominant-seventh", inversion=inversion)
        add_harmony(
            2, step=2, quality="dominant-seventh-flat-ninth", inversion=inversion
        )

        labels = {h.get_data("time"): h.label for h in harmony_tlui.harmonies()}
        assert labels[2] == labels[1] + "((b9))"

    def test_roman_applied(self, harmony_tlui):
        add_harmony(step=0, quality="dominant-seventh-flat-ninth", applied_to=3)

        assert harmony_tlui.harmonies()[0].label == "V7((b9))/IV"

    @pytest.mark.parametrize(
        "inversion, expected",
        [
            (0, "C7((b9))"),
            (1, "C7((b9))/E"),
            (2, "C7((b9))/G"),
            (3, "C7((b9))/B`b"),
        ],
    )
    def test_letter(self, inversion, expected, harmony_tlui):
        add_harmony(
            display_mode="letter",
            quality="dominant-seventh-flat-ninth",
            inversion=inversion,
        )

        assert harmony_tlui.harmonies()[0].label == expected

    def test_letter_on_flat_root(self, harmony_tlui):
        add_harmony(
            display_mode="letter",
            step=6,
            accidental=-1,
            quality="dominant-seventh-flat-ninth",
        )

        assert harmony_tlui.harmonies()[0].label == "B`b7((b9))"


class TestAddedToneLabel:
    # The base quality's label, then the added tone in raised parentheses. An
    # 11 is written "1\u200c1", as MusAnalysis draws "11" over the parenthesis.
    @pytest.mark.parametrize(
        "step, quality, inversion, expected",
        [
            (4, "dominant-seventh-sharp-ninth", 0, "V7((#9))"),
            (4, "dominant-seventh-sharp-eleventh", 0, "V7((#1\u200c1))"),
            (4, "dominant-seventh-flat-thirteenth", 0, "V7((b13))"),
            (4, "dominant-seventh-added-thirteenth", 0, "V7((13))"),
            (4, "dominant-seventh-added-thirteenth", 2, "V43((13))"),
            (4, "dominant-ninth-sharp-eleventh", 0, "V9((#1\u200c1))"),
            (0, "major-seventh-sharp-eleventh", 0, "I7((#1\u200c1))"),
            (0, "major-seventh-sharp-eleventh", 1, "I65((#1\u200c1))"),
            (0, "major-seventh-added-sixth", 0, "I7((6))"),
            (0, "major-sixth-added-ninth", 0, "I((6))((9))"),
            (1, "minor-sixth-added-ninth", 0, "ii((6))((9))"),
            (0, "major-added-ninth", 0, "I((9))"),
            (0, "major-added-ninth", 1, "I6((9))"),
            (1, "minor-added-ninth", 0, "ii((9))"),
            (1, "minor-seventh-added-eleventh", 0, "ii7((1\u200c1))"),
            (1, "minor-seventh-added-eleventh", 3, "ii42((1\u200c1))"),
        ],
    )
    def test_roman(self, step, quality, inversion, expected, harmony_tlui):
        add_harmony(step=step, quality=quality, inversion=inversion)

        assert harmony_tlui.harmonies()[0].label == expected

    @pytest.mark.parametrize(
        "quality, inversion, expected",
        [
            ("dominant-seventh-sharp-ninth", 0, "C7((#9))"),
            ("dominant-seventh-sharp-ninth", 1, "C7((#9))/E"),
            ("dominant-seventh-sharp-eleventh", 0, "C7((#1\u200c1))"),
            ("dominant-seventh-flat-thirteenth", 0, "C7((b13))"),
            ("dominant-seventh-added-thirteenth", 0, "C7((13))"),
            ("dominant-ninth-sharp-eleventh", 0, "C9((#1\u200c1))"),
            ("dominant-ninth-sharp-eleventh", 4, "C9((#1\u200c1))/D"),
            ("major-seventh-sharp-eleventh", 0, "C^^7((#1\u200c1))"),
            ("major-seventh-added-sixth", 0, "C^^7((6))"),
            ("major-sixth-added-ninth", 0, "C6((9))"),
            ("minor-sixth-added-ninth", 0, "Cm6((9))"),
            ("major-added-ninth", 0, "C((9))"),
            ("major-added-ninth", 2, "C((9))/G"),
            ("minor-added-ninth", 0, "Cm((9))"),
            ("minor-seventh-added-eleventh", 0, "Cm7((1\u200c1))"),
            ("minor-seventh-added-eleventh", 1, "Cm7((1\u200c1))/E`b"),
        ],
    )
    def test_letter(self, quality, inversion, expected, harmony_tlui):
        add_harmony(display_mode="letter", quality=quality, inversion=inversion)

        assert harmony_tlui.harmonies()[0].label == expected

    def test_letter_on_sharp_root(self, harmony_tlui):
        # The root's sharp is written for MusAnalysis, and the tone's is not.
        add_harmony(
            display_mode="letter", accidental=1, quality="dominant-seventh-sharp-ninth"
        )

        assert harmony_tlui.harmonies()[0].label == "C`#7((#9))"


class TestCadentialSixFourLabel:
    # Labelled as the dominant it resolves to, with the 6 stacked over the 4 in
    # parentheses that enclose both.
    def test_roman(self, harmony_tlui):
        add_harmony(step=4, quality="cadential-six-four")

        assert harmony_tlui.harmonies()[0].label == "V(64)"

    def test_roman_in_minor(self, harmony_tlui):
        # In A minor, as in major, the dominant is major: E with C and A over it.
        add_mode(**MINOR)
        add_harmony(1, step=2, quality="cadential-six-four")

        assert harmony_tlui.harmonies()[0].label == "V(64)"

    def test_roman_applied(self, harmony_tlui):
        add_harmony(step=1, quality="cadential-six-four", applied_to=4)

        assert harmony_tlui.harmonies()[0].label == "V(64)/V"

    def test_letter(self, harmony_tlui):
        add_harmony(display_mode="letter", step=4, quality="cadential-six-four")

        assert harmony_tlui.harmonies()[0].label == "G(64)"

    def test_letter_on_flat_root(self, harmony_tlui):
        add_harmony(
            display_mode="letter",
            step=6,
            accidental=-1,
            quality="cadential-six-four",
        )

        assert harmony_tlui.harmonies()[0].label == "B`b(64)"
