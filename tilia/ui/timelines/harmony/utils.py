import music21

from tilia.ui.timelines.harmony.constants import (
    INT_TO_ROMAN,
    NOTE_NAME_TO_INT,
    INT_TO_NOTE_NAME,
    INT_TO_MUSIC21_ACCIDENTAL, ACCIDENTAL_NUMBER_TO_MUSANALYSIS_STR,
)


def _handle_special_qualities(quality: str) -> str | None:
    match quality:
        case "Italian":
            return "It6+"
        case "French":
            return "Fr6+"
        case "German":
            return "Gr6+"
        case "Neapolitan":
            return "N6"
        case "Tristan":
            return "Trista@n"


QUALITY_TO_ROMAN_NUMERAL_SUFFIX = {
    "major": ("", "6", "64", None),
    "minor": ("", "6", "64", None),
    "augmented": ("+", "+6", "+64", None),
    "diminished": ("o", "o6", "o64", None),
    # seventh
    "dominant-seventh": ("7", "65", "43", "2"),
    "major-seventh": ("^^7", "65", "43", "2"),
    "minor-major-seventh": ("^^7", "65", "43", "2"),
    "minor-seventh": ("7", "65", "43", "2"),
    "augmented-major-seventh": ("+^^7", "65", "43", "2"),
    "augmented-seventh": ("+7", "65", "43", "2"),
    "half-diminished-seventh": ("o\\7", "o\\65", "o\\43", "o\\2"),
    "diminished-seventh": ("o7", "o65", "o43", "o2"),
    "seventh-flat-five": "7((b5))",
    # sixth
    "major-sixth": ("((6))", "6((4))", "64((2))", "7"),
    "minor-sixth": ("((6))", "6((4))", "64((2))", "7"),
    # ninth
    "major-ninth": ("9", "%765", "%543", "%432"),
    "dominant-ninth": ("9", "%765", "%543", "%432"),
    "minor-major-ninth": ("^^9", "%765", "%543", "%432"),
    "minor-ninth": ("9", "%765", "%543", "%432"),
    "augmented-major-ninth": ("+^^9", "+%765", "+%543", "+%432"),
    "augmented-dominant-ninth": ("+^^9", "+%765", "+%543", "+%432"),
    "half-diminished-ninth": ("o\\9", "o%765", "o%543", "o%432"),
    "half-diminished-minor-ninth": ("o\\b9", "o%sbs765", "%sbs543", "sbs%432"),
    "diminished-ninth": ("o9", "o%765", "o%543", "o%432"),
    "diminished-minor-ninth": ("ob9", "%sbs765", "%sbs543", "%sbs432"),
    # eleventh
    "dominant-11th": ("11", "%sbs765((9))", "%sbs543((7))", "%sbs432((5))"),
    "major-11th": ("^^11", "%sbs765((9))", "%sbs543((7))", "%sbs432((5))"),
    "minor-major-11th": ("11", "%sbs765((9))", "%sbs543((7))", "%sbs432((5))"),
    "minor-11th": ("11", "%sbs765((9))", "%sbs543((7))", "%sbs432((5))"),
    "augmented-major-11th": (
        "+11   ",
        "+%sbs765((9))",
        "+%sbs543((7))",
        "+%sbs432((5))",
    ),
    "augmented-11th": ("+11", "+%sbs765((9))", "+%sbs543((7))", "+%sbs432((5))"),
    "half-diminished-11th": (
        "o\\11",
        "o\\%sbs765((9))",
        "o\\%sbs543((7))",
        "o\\%sbs432((5))",
    ),
    "diminished-11th": ("o11", "o%sbs765((9))", "o%sbs543((7))", "o%sbs432((5))"),
    # thirteenth
    "major-13th": "^^13",
    "dominant-13th": ("13", "%sbs765((11))", "%sbs543((9))", "%sbs432((5))"),
    "minor-major-13th": ("^^13", "%sbs765((11))", "%sbs543((9))", "%sbs432((5))"),
    "minor-13th": ("13", "%sbs765((11))", "%sbs543((9))", "%sbs432((5))"),
    "augmented-major-13th": ("+13", "+%sbs765((11))", "+%sbs543((9))", "+%sbs432((5))"),
    "augmented-dominant-13th": (
        "+13",
        "+%sbs765((11))",
        "+%sbs543((9))",
        "+%sbs432((5))",
    ),
    "half-diminished-13th": (
        "o\\13",
        "o\\%sbs765((11))",
        "o\\%sbs543((9))",
        "o\\%sbs432((5))",
    ),
    # other
    "suspended-second": ("52", "74", "54", None),
    "suspended-fourth": ("54", "52", "74", None),
    "suspended-fourth-seventh": ("74", "54", "52", None),
    "pedal": ("`p`e`d`a`l", None, None, None),
    "power": ("`p`o`w`e`r", None, None, None),
}

INT_TO_APPLIED_TO_SUFFIX = {
    0: "",
    1: "/II",
    2: "/III",
    3: "/IV",
    4: "/V",
    5: "/VI",
    6: "/VII",
}


def _get_note_degree(key: music21.key.Key, note):
    steps = [p.step for p in key.pitches]
    return (
        steps.index(note.step) + 1
    )  # +1 is needed because music21's degrees are 1-based


def _get_roman_numeral_accidental(
    key: music21.key.Key, note_step: int, note_accidental: int
):
    tonic = INT_TO_NOTE_NAME[note_step]
    accidental_symbol = INT_TO_MUSIC21_ACCIDENTAL[note_accidental]
    note = music21.note.Note(tonic + accidental_symbol)
    is_diatonic = (note.step, note.pitch.pitchClass) in (
        (p.step, p.pitchClass) for p in key.pitches
    )
    if is_diatonic:
        return 0

    degree = _get_note_degree(key, note)
    key_degree_accidental = key.pitchFromDegree(degree).alter
    return note.pitch.alter - key_degree_accidental


def to_roman_numeral(
    step: int,
    accidental: int,
    quality: str,
    key: music21.key.Key,
    applied_to: int,
    inversion: int,
) -> str:
    if result := _handle_special_qualities(quality):
        return result

    key_step = NOTE_NAME_TO_INT[key.tonic.step]
    numeral = INT_TO_ROMAN[(step - key_step - applied_to) % 7]
    if quality.startswith(("minor", "diminished", "half-diminished")):
        numeral = numeral.lower()

    result_accidental = _get_roman_numeral_accidental(key, step, accidental)
    # Applied chords require a different calculation of their prefixes.
    # For now, let's leave them without a prefix, as that will be,
    # by far, the most common correct prefix.
    result_prefix = ACCIDENTAL_NUMBER_TO_MUSANALYSIS_STR[result_accidental] if not applied_to else ""
    quality_suffix = QUALITY_TO_ROMAN_NUMERAL_SUFFIX[quality][inversion]
    applied_to_suffix = INT_TO_APPLIED_TO_SUFFIX[applied_to]
    
    if "11th" in quality:
        quality_suffix += "    "

    return result_prefix + numeral + quality_suffix + applied_to_suffix
