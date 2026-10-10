import music21.harmony
import music21.key
import pytest

from tilia.timelines.harmony.components.harmony import SPECIAL_ABBREVIATIONS_TO_QUALITY
from tilia.timelines.harmony.constants import NOTE_NAME_TO_INT
from tilia.ui.dialogs.harmony_params import SelectHarmonyParams
from tilia.ui.timelines.harmony.utils import INT_TO_APPLIED_TO_SUFFIX


def type_text(text, key=None):
    dialog = SelectHarmonyParams(key)
    # insert one character at a time
    # to ensure no errors will be raised
    # while the user is typing
    for i in range(len(text)):
        dialog.line_edit.clear()
        dialog.line_edit.insert(text[: i + 1])
    return dialog


def parse_text(text, key=None):
    return type_text(text, key).get_result()


def is_refused(dialog):
    return dialog.line_edit.styleSheet() == "color: red"


class TestChordSymbolParsing:
    @pytest.mark.parametrize("text,step", NOTE_NAME_TO_INT.items())
    def test_only_note_name(self, text, step, qtui):
        params = parse_text(text)
        assert params["accidental"] == 0
        assert params["step"] == step
        assert params["quality"] == "major"

    ACCIDENTAL_TO_INT = {0: "", 1: "#", -1: "b", 2: "##", -2: "bb"}

    @pytest.mark.parametrize("accidental_n, accidental", ACCIDENTAL_TO_INT.items())
    @pytest.mark.parametrize("note,step", NOTE_NAME_TO_INT.items())
    def test_accidental_and_note_name(self, accidental_n, accidental, note, step, qtui):
        params = parse_text(note + accidental)
        assert params["accidental"] == accidental_n
        assert params["step"] == step

    def test_minus_sign_is_parsed_as_quality(self, qtui):
        params = parse_text("D-")
        assert params["accidental"] == 0
        assert params["step"] == 1
        assert params["quality"] == "minor"

    def test_minus_sign_after_accidental_is_parsed_as_minor_quality(self, qtui):
        params = parse_text("Cb-")
        assert params["accidental"] == -1
        assert params["step"] == 0
        assert params["quality"] == "minor"

    def test_minus_sign_after_double_accidental_is_parsed_as_minor_quality(self, qtui):
        params = parse_text("C##-")
        assert params["accidental"] == 2
        assert params["step"] == 0
        assert params["quality"] == "minor"

    def test_b_before_quality(self, qtui):
        params = parse_text("Dbm7")
        assert params["accidental"] == -1
        assert params["step"] == 1
        assert params["quality"] == "minor-seventh"

    @pytest.mark.parametrize("quality", list(music21.harmony.CHORD_TYPES))
    def test_regular_abbreviations(self, quality, qtui):
        for abbreviation in music21.harmony.CHORD_TYPES[quality][1]:
            if abbreviation in SPECIAL_ABBREVIATIONS_TO_QUALITY:
                continue
            params = parse_text("D" + abbreviation)
            assert params["step"] == 1
            assert params["quality"] == quality

    @pytest.mark.parametrize("abbrev", SPECIAL_ABBREVIATIONS_TO_QUALITY)
    def test_special_abbreviations(self, abbrev, qtui):
        params = parse_text("D" + abbrev)
        assert params["step"] == 1
        assert params["quality"] == SPECIAL_ABBREVIATIONS_TO_QUALITY[abbrev]
        pass

    @pytest.mark.parametrize("applied_to,suffix", INT_TO_APPLIED_TO_SUFFIX.items())
    def test_applied_chords(self, applied_to, suffix, qtui):
        params = parse_text("I" + suffix)
        assert params["applied_to"] == applied_to

    def test_slash_chords_where_bass_is_not_in_chord_symbol(self, qtui):
        params = parse_text("G/A")
        assert params["step"] == 4
        assert (
            params["inversion"] == 0
        )  # bass-not-in-chord slash chords are not supported

    @pytest.mark.parametrize(
        "extension",
        ["7#9", "7#11", "m713", "7b9", "11", "7(b13)", "7(b9,#11)", "(b9,#13)"],
    )
    def test_parse_with_extensions_does_not_crash(self, extension, qtui):
        # This only tests that it doesn't crash. Some of these are read as a
        # quality with an added tone, the others without their extensions.
        params = parse_text("C" + extension)
        assert params["step"] == 0

    @pytest.mark.parametrize(
        "text, step, accidental, inversion",
        [
            ("C7b9", 0, 0, 0),
            ("C7(b9)", 0, 0, 0),
            ("Bb7b9", 6, -1, 0),
            ("C7b9/E", 0, 0, 1),
            ("C7(b9)/G", 0, 0, 2),
            ("C7b9/Bb", 0, 0, 3),
        ],
    )
    def test_dominant_seventh_flat_ninth(self, text, step, accidental, inversion, qtui):
        params = parse_text(text)
        assert params["quality"] == "dominant-seventh-flat-ninth"
        assert params["step"] == step
        assert params["accidental"] == accidental
        assert params["inversion"] == inversion

    @pytest.mark.parametrize(
        "text, quality, inversion",
        [
            ("C7#9", "dominant-seventh-sharp-ninth", 0),
            ("C7(#9)/E", "dominant-seventh-sharp-ninth", 1),
            ("C7#11", "dominant-seventh-sharp-eleventh", 0),
            ("C7b13/G", "dominant-seventh-flat-thirteenth", 2),
            ("C7add13", "dominant-seventh-added-thirteenth", 0),
            ("C7(13)/Bb", "dominant-seventh-added-thirteenth", 3),
            ("C9#11/D", "dominant-ninth-sharp-eleventh", 4),
            ("Cmaj7#11", "major-seventh-sharp-eleventh", 0),
            ("CM7(#11)", "major-seventh-sharp-eleventh", 0),
            ("Cmaj7add6/B", "major-seventh-added-sixth", 3),
            ("C6add9", "major-sixth-added-ninth", 0),
            ("C6/9/E", "major-sixth-added-ninth", 1),
            ("C6(9)", "major-sixth-added-ninth", 0),
            ("Cm6/9/G", "minor-sixth-added-ninth", 2),
            ("Cadd9", "major-added-ninth", 0),
            ("C(add9)/E", "major-added-ninth", 1),
            ("C(9)", "major-added-ninth", 0),
            ("Cmadd9/G", "minor-added-ninth", 2),
            ("Cm(add9)", "minor-added-ninth", 0),
            ("Cm7add11/Eb", "minor-seventh-added-eleventh", 1),
            ("Cm7(11)", "minor-seventh-added-eleventh", 0),
        ],
    )
    def test_added_tone_qualities(self, text, quality, inversion, qtui):
        params = parse_text(text)
        assert params["quality"] == quality
        assert params["step"] == 0
        assert params["accidental"] == 0
        assert params["inversion"] == inversion

    @pytest.mark.parametrize(
        "text, step, accidental, quality",
        [
            ("C#7#9", 0, 1, "dominant-seventh-sharp-ninth"),
            ("Bb6/9", 6, -1, "major-sixth-added-ninth"),
            ("F#m7add11", 3, 1, "minor-seventh-added-eleventh"),
        ],
    )
    def test_added_tone_quality_on_altered_root(
        self, text, step, accidental, quality, qtui
    ):
        params = parse_text(text)
        assert params["quality"] == quality
        assert params["step"] == step
        assert params["accidental"] == accidental

    @pytest.mark.parametrize(
        "text",
        [
            "C7b9/Db",
            "C7#9/D#",
            "C7#11/F#",
            "C7b13/Ab",
            "C7add13/A",
            "C9#11/F#",
            "Cmaj7#11/F#",
            "Cmaj7add6/A",
            "C6add9/D",
            "Cm6add9/D",
            "Cadd9/D",
            "Cmadd9/D",
            "Cm7add11/F",
        ],
    )
    def test_added_tone_in_the_bass_is_refused(self, text, qtui):
        # No inversion of the base quality puts the added tone in the bass.
        assert is_refused(type_text(text))

    @pytest.mark.parametrize("text", ["Cm7(b9)", "CM7(b9)", "C(#9)"])
    def test_tone_in_parentheses_that_makes_no_quality_is_refused(self, text, qtui):
        # As before, since music21 reads no parentheses. Without them,
        # "C(#9)" would read as a C sharp ninth chord.
        assert is_refused(type_text(text))

    @pytest.mark.parametrize(
        "text, quality",
        [
            ("Cm7b9", "minor-seventh"),
            ("CM7b9", "major-seventh"),
            ("Cdim7b9", "diminished-seventh"),
            ("C+7b9", "augmented-seventh"),
        ],
    )
    def test_flat_ninth_on_other_sevenths_is_dropped_as_before(
        self, text, quality, qtui
    ):
        # TiLiA has no quality for these, so the flat ninth is dropped, as
        # before. The text is set at once, because typing it one character
        # at a time would leave the quality that "Cm7" gives.
        dialog = SelectHarmonyParams()
        dialog.line_edit.setText(text)
        assert dialog.populate_from_text()
        assert dialog.get_result()["quality"] == quality

    @pytest.mark.parametrize(
        "quality, listed_after, text, inversions",
        [
            ("dominant-seventh-flat-ninth", "dominant-seventh", "C7b9", 3),
            ("dominant-seventh-sharp-ninth", "dominant-seventh-flat-ninth", "C7#9", 3),
            (
                "dominant-seventh-sharp-eleventh",
                "dominant-seventh-sharp-ninth",
                "C7#11",
                3,
            ),
            (
                "dominant-seventh-flat-thirteenth",
                "dominant-seventh-sharp-eleventh",
                "C7b13",
                3,
            ),
            (
                "dominant-seventh-added-thirteenth",
                "dominant-seventh-flat-thirteenth",
                "C7add13",
                3,
            ),
            ("dominant-ninth-sharp-eleventh", "dominant-ninth", "C9#11", 4),
            ("major-seventh-sharp-eleventh", "major-seventh", "Cmaj7#11", 3),
            (
                "major-seventh-added-sixth",
                "major-seventh-sharp-eleventh",
                "Cmaj7add6",
                3,
            ),
            ("major-sixth-added-ninth", "major-sixth", "C6add9", 3),
            ("minor-sixth-added-ninth", "minor-sixth", "Cm6add9", 3),
            ("major-added-ninth", "major", "Cadd9", 2),
            ("minor-added-ninth", "minor", "Cmadd9", 2),
            ("minor-seventh-added-eleventh", "minor-seventh", "Cm7add11", 3),
        ],
    )
    def test_added_tone_quality_is_offered_after_its_base(
        self, quality, listed_after, text, inversions, qtui
    ):
        dialog = SelectHarmonyParams()
        combobox = dialog.quality_combobox
        index = combobox.findData(quality)
        assert combobox.itemData(index - 1) == listed_after

        combobox.setCurrentIndex(index)

        assert dialog.line_edit.text() == text
        # The base quality's inversions, plus root position.
        assert dialog.inversion_combobox.count() == inversions + 1
        assert dialog.populate_from_text()
        assert dialog.get_result()["quality"] == quality

    def test_applied_to_is_cleared_when_no_longer_applied(self, qtui):
        # Regression guard: the applied-to combobox was only ever updated when
        # parsing produced a nonzero applied_to, so editing the text back down
        # to a plain (non-applied) chord left the previous selection (e.g. "/V")
        # stuck in the combobox instead of resetting to "none".
        dialog = SelectHarmonyParams()
        dialog.line_edit.setText("V7/V")
        dialog.populate_from_text()
        assert dialog.applied_to_combobox.currentData() == 4

        dialog.line_edit.setText("V7")
        dialog.populate_from_text()
        assert dialog.applied_to_combobox.currentData() == 0


class TestRomanNumeralParsing:
    # Regression guard: a roman-numeral seventh used to select the triad
    # quality (e.g. "V7" -> "major") because the parser read music21's
    # `impliedQuality`, which only reflects the triad, instead of the full
    # chord type computed from the chord's pitches.
    @pytest.mark.parametrize(
        "text, quality, step, inversion",
        [
            ("V", "major", 4, 0),
            ("V7", "dominant-seventh", 4, 0),
            ("V65", "dominant-seventh", 4, 1),
            ("V43", "dominant-seventh", 4, 2),
            ("V42", "dominant-seventh", 4, 3),
            ("ii7", "minor-seventh", 1, 0),
            ("viio7", "diminished-seventh", 6, 0),
        ],
    )
    def test_quality_step_and_inversion(self, text, quality, step, inversion, qtui):
        params = parse_text(text)
        assert params["quality"] == quality
        assert params["step"] == step
        assert params["inversion"] == inversion

    def test_seventh_quality_is_not_collapsed_to_triad(self, qtui):
        # Direct guard for the reported bug: typing "V7" selected "Major".
        assert parse_text("V7")["quality"] == "dominant-seventh"

    def test_applied_seventh(self, qtui):
        params = parse_text("V7/V")
        assert params["quality"] == "dominant-seventh"
        assert params["applied_to"] == 4
        assert params["step"] == 1

    @pytest.mark.parametrize(
        "key, text, step, inversion, applied_to",
        [
            ("C", "V7b9", 4, 0, 0),
            ("C", "V7(b9)", 4, 0, 0),
            ("C", "Vb9", 4, 0, 0),
            ("C", "V65b9", 4, 1, 0),
            ("C", "V42(b9)", 4, 3, 0),
            ("C", "V7b9/IV", 0, 0, 3),
            ("C", "V7(b9)/II", 5, 0, 1),
            ("a", "V7b9", 2, 0, 0),
            ("a", "Vb9", 2, 0, 0),  # the flat ninth of E7 is F
        ],
    )
    def test_dominant_seventh_flat_ninth(
        self, key, text, step, inversion, applied_to, qtui
    ):
        params = parse_text(text, music21.key.Key(key))
        assert params["quality"] == "dominant-seventh-flat-ninth"
        assert params["step"] == step
        assert params["accidental"] == 0
        assert params["inversion"] == inversion
        assert params["applied_to"] == applied_to

    @pytest.mark.parametrize(
        "text, step, inversion, quality",
        [
            ("V7#9", 4, 0, "dominant-seventh-sharp-ninth"),
            ("V#9", 4, 0, "dominant-seventh-sharp-ninth"),
            ("V65#9", 4, 1, "dominant-seventh-sharp-ninth"),
            ("V7#11", 4, 0, "dominant-seventh-sharp-eleventh"),
            ("V7b13", 4, 0, "dominant-seventh-flat-thirteenth"),
            ("V7add13", 4, 0, "dominant-seventh-added-thirteenth"),
            ("V7(13)", 4, 0, "dominant-seventh-added-thirteenth"),
            ("I7#11", 0, 0, "major-seventh-sharp-eleventh"),
            ("I7(#11)", 0, 0, "major-seventh-sharp-eleventh"),
            ("I7add6", 0, 0, "major-seventh-added-sixth"),
            ("Iadd9", 0, 0, "major-added-ninth"),
            ("I(9)", 0, 0, "major-added-ninth"),
            ("I6(add9)", 0, 1, "major-added-ninth"),
            ("iadd9", 0, 0, "minor-added-ninth"),
            ("ii7add11", 1, 0, "minor-seventh-added-eleventh"),
            ("ii65(11)", 1, 1, "minor-seventh-added-eleventh"),
        ],
    )
    def test_added_tone_qualities(self, text, step, inversion, quality, qtui):
        params = parse_text(text, music21.key.Key("C"))
        assert params["quality"] == quality
        assert params["step"] == step
        assert params["inversion"] == inversion

    @pytest.mark.parametrize(
        "text", ["ii7b9", "I7b9", "viio7b9", "ii7#11", "I7(9)", "Vadd6"]
    )
    def test_tone_that_makes_no_quality_is_refused(self, text, qtui):
        # TiLiA has no quality for these. A minor seventh with a flat ninth,
        # say, is not read as a minor seventh.
        assert is_refused(type_text(text))
