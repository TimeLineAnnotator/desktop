import music21.harmony
import pytest

from tilia.timelines.harmony.components.harmony import SPECIAL_ABBREVIATIONS_TO_QUALITY
from tilia.ui.dialogs.harmony_params import SelectHarmonyParams
from tilia.ui.timelines.harmony.constants import NOTE_NAME_TO_INT
from tilia.ui.timelines.harmony.utils import INT_TO_APPLIED_TO_SUFFIX


def parse_text(text):
    dialog = SelectHarmonyParams()
    # insert one character at a time
    # to ensure no errors will be raised
    # while the user is typing
    for i in range(len(text)):
        dialog.line_edit.clear()
        dialog.line_edit.insert(text[: i + 1])
    return dialog.get_result()


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

    def test_slash_chords_where_bass_is_not_in_chord_symbol(self):
        params = parse_text("G/A")
        assert params["step"] == 4
        assert params["inversion"] == 0  # fourth inversion is not currently supported

    @pytest.mark.parametrize(
        "extension",
        ["7#9", "7#11", "m713", "7b9", "11", "7(b13)", "7(b9,#11)", "(b9,#13)"],
    )
    def test_parse_with_extensions_does_not_crash(self, extension, qtui):
        # This only tests that it doesn't crash
        # extensions are not currently supported
        params = parse_text("C" + extension)
        assert params["step"] == 0
