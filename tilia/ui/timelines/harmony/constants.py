import music21.harmony
import music21.pitch

from tilia.timelines.harmony.constants import ADDED_TONE_QUALITIES

ACCIDENTAL_TO_INT = {"": 0, "♯": 1, "♭": -1, "𝄪": 2, "𝄫": -2}


class Accidental:
    TYPE_TO_NUMBER_TO_SYMBOL = {
        "music21": {0: "", 1: "#", -1: "-", 2: "##", -2: "--"},
        "musanalysis": {
            -2: "`b`b",
            -1: "`b",
            0: "",
            1: "`#",
            2: "`x",
        },
        "frontend": {
            -2: "bb",
            -1: "b",
            0: "",
            1: "#",
            2: "##",
        },
    }

    @staticmethod
    def get_from_int(symbol_type: str, value: int):
        if symbol_type not in Accidental.TYPE_TO_NUMBER_TO_SYMBOL:
            raise ValueError("Invalid symbol type")

        number_to_symbol = Accidental.TYPE_TO_NUMBER_TO_SYMBOL[symbol_type]

        def get_substitute():
            if isinstance(value, float) or isinstance(value, int):
                positivity = 1 if value > 0 else -1
                tones = int(abs(value // 2))
                semitones = int(abs(value % 2))
                return (
                    number_to_symbol[positivity] * semitones
                    + number_to_symbol[positivity * 2] * tones
                )
            raise KeyError

        return number_to_symbol.get(value, get_substitute())


STEP_TO_PITCH_CLASS = {
    i: music21.pitch.Pitch(s).pitchClass
    for i, s in enumerate(["C", "D", "E", "F", "G", "A", "B"])
}

QUALITY_TO_ABBREVIATION = {
    qlt: data[1][0] for qlt, data in music21.harmony.CHORD_TYPES.items()
}


def _added_tone_abbreviation(tone: str) -> str:
    """
    Write an added tone after its base's abbreviation: an altered tone as it
    is, as in "C7b9", the cadential six-four's in parentheses, as it is
    labelled, as in "G(64)", and any other after "add", as in "Cadd9".
    """
    if tone.startswith(("b", "#")):
        return tone
    if tone == "64":
        return "(64)"
    return "add" + tone


QUALITY_TO_ABBREVIATION |= {
    quality: QUALITY_TO_ABBREVIATION[base] + _added_tone_abbreviation(tone)
    for quality, (base, tone) in ADDED_TONE_QUALITIES.items()
}
