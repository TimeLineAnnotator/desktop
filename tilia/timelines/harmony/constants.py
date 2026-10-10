import music21.harmony as _m21h
import music21.key as _m21k

HARMONY_DISPLAY_MODES = ["letter", "roman", "custom"]
HARMONY_ACCIDENTALS = [2, 1, 0, -1, -2]
MODE_TYPES = [m for m in _m21k.modeSharpsAlter.keys() if m not in ("ionian", "aeolian")]
FONT_TYPES = ["analytic", "normal"]

# Qualities that music21 has no chord type for, each a chord type it has plus
# one added tone. The tone is spelled as in a chord symbol, from the root: the
# flat ninth of E7 is F, whatever the key.
ADDED_TONE_QUALITIES = {
    "dominant-seventh-flat-ninth": ("dominant-seventh", "b9"),
    "dominant-seventh-sharp-ninth": ("dominant-seventh", "#9"),
    "dominant-seventh-sharp-eleventh": ("dominant-seventh", "#11"),
    "dominant-seventh-flat-thirteenth": ("dominant-seventh", "b13"),
    "dominant-seventh-added-thirteenth": ("dominant-seventh", "13"),
    "dominant-ninth-sharp-eleventh": ("dominant-ninth", "#11"),
    "major-seventh-sharp-eleventh": ("major-seventh", "#11"),
    "major-seventh-added-sixth": ("major-seventh", "6"),
    "major-sixth-added-ninth": ("major-sixth", "9"),
    "minor-sixth-added-ninth": ("minor-sixth", "9"),
    "major-added-ninth": ("major", "9"),
    "minor-added-ninth": ("minor", "9"),
    "minor-seventh-added-eleventh": ("minor-seventh", "11"),
}


def split_added_tone(quality: str) -> tuple[str, str]:
    """Return the quality's base quality and added tone, or the quality and ""."""
    return ADDED_TONE_QUALITIES.get(quality, (quality, ""))


def _list_harmony_qualities() -> list[str]:
    # Each added-tone quality comes right after its base quality.
    qualities = list(_m21h.CHORD_TYPES)
    for quality, (base, _) in reversed(ADDED_TONE_QUALITIES.items()):
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

# These qualities are locked to root position: the Inspector/Add Harmony
# dialog offer no inversion choices for them, and to_roman_numeral /
# letter_symbol_label render a fixed string regardless of bass note.
#
# - Italian, French, German (augmented sixths): genuinely have no inversions
#   in standard tonal harmony — the augmented-sixth interval that defines
#   the chord only exists with scale degree b6 in the bass.
# - Tristan: referenced in the literature as a single fixed sonority,
#   not a chord family with an established inversion convention.
# - Neapolitan: DOES have real inversions (root position and 2nd inversion
#   occur, though 1st inversion — "N6" — is by far the most common). But
#   music21's own "Neapolitan"/"N6" CHORD_TYPES entry is not the classical
#   Neapolitan-sixth triad at all — it's an unrelated 4-note "all-interval
#   tetrachord" that happens to share the abbreviation. Supporting inversions
#   here means building the real major-triad-on-b2 pitches first, not just
#   removing this quality from the set below.
# - power: DOES have a real inverted voicing (5th in the bass, common in
#   rock/metal), but music21.harmony.ChordSymbol can't construct it via
#   inversion=1 (raises ChordException — see the try/except in
#   HarmonyUI.letter_symbol), and there's no established figured-bass
#   notation for an inverted power chord to reuse in to_roman_numeral.
#
# TODO: Neapolitan and power are the two qualities above actually worth
# revisiting (Italian/French/German/Tristan have no inversions to support).
# Neapolitan needs its pitches constructed independently of music21's
# "N6" chord type before inversions mean anything; power needs a bass
# override in HarmonyUI.letter_symbol (music21 can't invert it directly)
# plus an invented figured-bass notation for to_roman_numeral, since no
# textbook convention exists for an inverted power chord.
_NO_INVERSION_QUALITIES = frozenset(
    {"Italian", "French", "German", "Neapolitan", "Tristan", "power"}
)


def get_inversion_amount(quality: str) -> int:
    if quality not in HARMONY_QUALITIES:
        raise ValueError(f'Invalid harmony quality "{quality}"')
    # An added tone is not one the chord can be inverted to.
    quality, _ = split_added_tone(quality)
    if quality in _NO_INVERSION_QUALITIES:
        return 0
    intervals_str = str(_m21h.CHORD_TYPES[quality][0])  # type: ignore[index]
    return len(intervals_str.split(",")) - 1
