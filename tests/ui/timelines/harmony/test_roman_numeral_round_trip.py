"""
Roman-numeral labels and typed input agree: a label typed back in its key gives
the chord it labels.

These tests run over every quality, inversion and root, which is too many chords
to add to a timeline one by one, so they call `to_roman_numeral` for the label
and `get_params_from_text` for the typing back, the function the Add harmony
dialog reads its text with.
"""

import json
from functools import cache
from pathlib import Path

import music21
import pytest

from tests.ui.timelines.harmony.interact import label_as_typed, numeral_part
from tilia.timelines.harmony.components.harmony import get_params_from_text
from tilia.timelines.harmony.constants import HARMONY_QUALITIES
from tilia.ui.timelines.harmony.utils import to_roman_numeral

KEYS = {
    "A minor": ("A", "minor"),
    "Eb minor": ("E-", "minor"),
    "F# minor": ("F#", "minor"),
    "C major": ("C", "major"),  # the same labels as before, as a control
}

MINOR_KEYS = [name for name in KEYS if name.endswith("minor")]

# Every root: each step with a flat, a natural and a sharp.
ROOTS = [(step, accidental) for step in range(7) for accidental in (-1, 0, 1)]

# Labelled by a fixed text, with no numeral to read back.
FIXED_LABEL_QUALITIES = ["Italian", "French", "German", "Neapolitan"]

NUMERAL_QUALITIES = [q for q in HARMONY_QUALITIES if q not in FIXED_LABEL_QUALITIES]

# The (quality, inversions) a label is read back as, when its figures need no
# accidental. Figures are figured bass, relative to the key signature, and
# music21 reads an accidental beside a figure as an alteration of the chord's
# own tone, so a label whose figures carry one is not read back as the same
# chord (in C major, either). Left out are what typing can't make: qualities
# music21 reads no Roman numeral as (the ninth chords and up, the half-
# diminished seventh, whose symbol is drawn "o\" but typed "ø" or "/o", the
# suspended chords, power, pedal, Tristan), and the inversions that share a
# label with another chord (the dominant and major seventh's third inversion
# are both I42, and the augmented seventh's second is V43).
READ_BACK_INVERSIONS = {
    "major": [0, 1, 2],
    "minor": [0, 1, 2],
    "augmented": [0, 2],
    "diminished": [0, 1, 2],
    "dominant-seventh": [0, 1, 2],
    "major-seventh": [0, 1, 2],
    "minor-seventh": [0, 1, 2, 3],
    "augmented-seventh": [0],
    "diminished-seventh": [0, 1, 2, 3],
}

# The numerals of a major triad and a minor triad, in every major and minor key,
# as the code labelled them before the case of a numeral chose the sixth and
# seventh degrees of a minor key. Each list runs through ROOTS. A minor key's
# sixth and seventh degrees changed, and are null.
NUMERALS_BEFORE = json.loads(
    (Path(__file__).parent / "roman_numerals_before_minor_rule.json").read_text()
)


def key_of(key_name: str) -> music21.key.Key:
    tonic, mode = KEYS[key_name]
    return music21.key.Key(tonic, mode=mode)


@cache
def read_back(label: str, key_name: str) -> tuple | None:
    """
    The chord the Add harmony dialog reads a label as, in a key, if any:
    (step, accidental, quality, inversion, applied_to).
    """
    success, params = get_params_from_text(label_as_typed(label), key_of(key_name))
    if not success:
        return None
    return (
        params["step"],
        params["accidental"],
        params["quality"],
        params["inversion"],
        params["applied_to"],
    )


def has_figure_accidental(label: str) -> bool:
    figures = label[len(numeral_part(label)) :]
    return any(char in figures for char in "#bx%`(")


@pytest.mark.parametrize("key_name", MINOR_KEYS)
@pytest.mark.parametrize("quality", NUMERAL_QUALITIES)
def test_numeral_is_read_back_as_the_same_root(key_name, quality):
    # A bare numeral reads as a major triad if it is upper-case and a minor one
    # if it is lower-case, so this also tests the case of the numeral. The
    # numeral does not depend on the inversion: it is the same in every one of
    # a quality's labels, so this runs in root position, and the inversions that
    # can be typed are read back whole by the next test.
    key = key_of(key_name)
    lower_case = quality.startswith(("minor", "diminished", "half-diminished"))
    expected_quality = "minor" if lower_case else "major"

    wrong = []
    for step, accidental in ROOTS:
        label = to_roman_numeral(step, accidental, quality, key, 0, 0)
        read = read_back(numeral_part(label), key_name)
        if not read or read[:3] != (step, accidental, expected_quality):
            wrong.append((step, accidental, label, read))

    assert not wrong, f"(step, accidental, label, read): {wrong}"


@pytest.mark.parametrize("key_name", KEYS)
@pytest.mark.parametrize("quality", READ_BACK_INVERSIONS)
def test_label_is_read_back_as_the_same_chord(key_name, quality):
    key = key_of(key_name)

    checked = 0
    wrong = []
    for inversion in READ_BACK_INVERSIONS[quality]:
        for step, accidental in ROOTS:
            label = to_roman_numeral(step, accidental, quality, key, 0, inversion)
            if has_figure_accidental(label):
                continue
            checked += 1
            read = read_back(label, key_name)
            if read != (step, accidental, quality, inversion, 0):
                wrong.append((inversion, step, accidental, label, read))

    assert checked
    assert not wrong, f"(inversion, step, accidental, label, read): {wrong}"


@pytest.mark.parametrize("quality", FIXED_LABEL_QUALITIES)
@pytest.mark.parametrize("key_name", KEYS)
def test_fixed_labels_are_the_same_in_every_key(key_name, quality):
    # They name no numeral, so there is none to read back or to change.
    labels = {
        to_roman_numeral(step, accidental, quality, key_of(key_name), 0, 0)
        for step, accidental in ROOTS
    }

    assert len(labels) == 1


@pytest.mark.parametrize("key_name", NUMERALS_BEFORE)
@pytest.mark.parametrize("quality", ["major", "minor"])
def test_numerals_outside_a_minor_keys_sixth_and_seventh_are_unchanged(
    key_name, quality
):
    tonic, mode = key_name.split()
    key = music21.key.Key(tonic, mode=mode)

    numerals = NUMERALS_BEFORE[key_name][quality]
    for (step, accidental), before in zip(ROOTS, numerals, strict=True):
        if before is not None:
            assert to_roman_numeral(step, accidental, quality, key, 0, 0) == before
