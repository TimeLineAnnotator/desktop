import music21.harmony
import pytest

from tilia.timelines.harmony.components.harmony import SPECIAL_ABBREVIATIONS_TO_QUALITY
from tilia.ui.dialogs.harmony_params import SelectHarmonyParams
from tilia.ui.timelines.harmony.constants import NOTE_NAME_TO_INT


def parse_text(text):
    dialog = SelectHarmonyParams()
    dialog.line_edit.insert(text)
    return dialog.result()


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
