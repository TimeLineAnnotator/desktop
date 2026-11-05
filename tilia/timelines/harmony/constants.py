import music21.harmony as _m21h
import music21.key as _m21k

from tilia_core import rules

MODE_TYPES = [m for m in _m21k.modeSharpsAlter.keys() if m not in ("ionian", "aeolian")]

# The dominant with a sixth and a fourth over its root, which resolve to its
# fifth and third. Its sixth and fourth are not added tones, but it is written
# and typed as if they were, on the major triad: "V(64)".
#
# Two gaps are left until the harmony model is overhauled. Any major triad
# takes it, not only the dominant, so "I(64)" is accepted too. And "Gadd64" is
# read as it, though music21 reads a 64th as the root doubled, so its music21
# chord has the root, third and fifth, and no sixth or fourth.
CADENTIAL_SIX_FOUR_TONE = "64"


def _list_harmony_qualities() -> list[str]:
    # Each added-tone quality comes right after its base quality.
    qualities = list(_m21h.CHORD_TYPES)
    for quality, (base, _) in reversed(rules.ADDED_TONE_QUALITIES.items()):
        qualities.insert(qualities.index(base) + 1, quality)
    return qualities


HARMONY_QUALITIES = _list_harmony_qualities()

NOTE_NAME_TO_INT = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
INT_TO_NOTE_NAME = {v: k for k, v in NOTE_NAME_TO_INT.items()}

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
