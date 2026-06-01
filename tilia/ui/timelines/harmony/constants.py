import music21.harmony
import music21.pitch

ROMAN_TO_INT = {
    "I": 0,
    "II": 1,
    "III": 2,
    "IV": 3,
    "V": 4,
    "VI": 5,
    "VII": 6,
}
INT_TO_ROMAN = {v: k for k, v in ROMAN_TO_INT.items()}

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


NOTE_NAME_TO_INT = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
INT_TO_NOTE_NAME = {v: k for k, v in NOTE_NAME_TO_INT.items()}

STEP_TO_PITCH_CLASS = {
    i: music21.pitch.Pitch(s).pitchClass
    for i, s in enumerate(["C", "D", "E", "F", "G", "A", "B"])
}

QUALITY_TO_ABBREVIATION = {
    qlt: data[1][0] for qlt, data in music21.harmony.CHORD_TYPES.items()
}


CHORD_COMMON_NAME_TO_TYPE = {
    "augmented seventh chord": "augmented-seventh",
    "half-diminished seventh chord": "half-diminished-seventh",
    "major seventh chord": "major-seventh",
    "augmented triad": "augmented",
    "diminished seventh chord": "diminished-seventh",
    "dominant seventh chord": "dominant-seventh",
    "diminished triad": "diminished",
    "minor seventh chord": "minor-seventh",
    "augmented major tetrachord": "augmented-major-13th",
    "major triad": "major",
    "minor triad": "minor",
}
