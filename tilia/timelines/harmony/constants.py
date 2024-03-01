HARMONY_INVERSIONS = [0, 1, 2, 3]
HARMONY_DISPLAY_MODES = ["chord", "roman", "custom"]
HARMONY_ACCIDENTALS = [2, 1, 0, -1, -2]
MODE_TYPES = ["major", "minor"]
FONT_TYPES = ["analytic", "normal"]
# Names are taken from music21.harmony.CHORD_TYPES
HARMONY_QUALITIES = [
    "major",
    "minor",
    "augmented",
    "diminished",
    # seventh
    "dominant-seventh",
    "major-seventh",
    "minor-major-seventh",
    "minor-seventh",
    "augmented-major-seventh",
    "augmented-seventh",
    "half-diminished-seventh",
    "diminished-seventh",
    "seventh-flat-five",
    # sixth
    "major-sixth",
    "minor-sixth",
    # ninth
    "major-ninth",
    "dominant-ninth",
    "minor-major-ninth",
    "minor-ninth",
    "augmented-major-ninth",
    "augmented-dominant-ninth",
    "half-diminished-ninth",
    "half-diminished-minor-ninth",
    "diminished-ninth",
    "diminished-minor-ninth",
    # eleventh
    "dominant-11th",
    "major-11th",
    "minor-major-11th",
    "minor-11th",
    "augmented-major-11th",
    "augmented-11th",
    "half-diminished-11th",
    "diminished-11th",
    # thirteenth
    "major-13th",
    "dominant-13th",
    "minor-major-13th",
    "minor-13th",
    "augmented-major-13th",
    "augmented-dominant-13th",
    "half-diminished-13th",
    # other
    "suspended-second",
    "suspended-fourth",
    "suspended-fourth-seventh",
    "Neapolitan",
    "Italian",
    "French",
    "German",
    "pedal",
    "power",
    "Tristan",
]


def get_inversion_amount(quality: str) -> int:
    if quality not in HARMONY_QUALITIES:
        raise ValueError(f'Invalid harmony quality "{quality}"')

    if quality.endswith(("sixth", "seventh", "ninth", "11th", "13th")):
        return 3  # 4th inversion and beyond are not yet supported
    elif quality == "seventh-flat-five":
        return 3
    elif quality in [
        "power",
        "pedal",
        "French",
        "German",
        "Italian",
        "Neapolitan",
        "Tristan",
    ]:
        return 0
    else:
        return 2
