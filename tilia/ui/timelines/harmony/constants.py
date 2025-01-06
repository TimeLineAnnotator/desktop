import music21

from tilia.timelines.harmony.constants import HARMONY_QUALITIES

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

STEP_TO_PITCH_CLASS = {0: 0, 1: 2, 2: 4, 3: 5, 4: 7, 5: 9, 6: 11}

QUALITY_TO_ABBREVIATION = {
    qlt: music21.harmony.CHORD_TYPES[qlt][1][0] for qlt in HARMONY_QUALITIES
}

INVERSION_TO_INTERVAL = {1: 3, 2: 5, 3: 7}

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
