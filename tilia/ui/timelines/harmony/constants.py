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
INT_TO_ACCIDENTAL = {v: k for k, v in ACCIDENTAL_TO_INT.items()}
INT_TO_MUSIC21_ACCIDENTAL = {0: "", 1: "#", -1: "-", 2: "##", -2: "--"}
ACCIDENTAL_NUMBER_TO_MUSIC21_CHAR = {0: "", 1: "#", -1: "-", 2: "##", -2: "--"}

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
