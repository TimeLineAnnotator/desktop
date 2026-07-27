import music21.harmony as _m21h
import music21.key as _m21k

HARMONY_DISPLAY_MODES = ["letter", "roman", "custom"]
HARMONY_ACCIDENTALS = [2, 1, 0, -1, -2]
MODE_TYPES = [m for m in _m21k.modeSharpsAlter.keys() if m not in ("ionian", "aeolian")]
FONT_TYPES = ["analytic", "normal"]
HARMONY_QUALITIES = list(_m21h.CHORD_TYPES.keys())

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
    if quality in _NO_INVERSION_QUALITIES:
        return 0
    intervals_str = str(_m21h.CHORD_TYPES[quality][0])  # type: ignore[index]
    return len(intervals_str.split(",")) - 1
