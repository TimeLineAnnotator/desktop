"""Pitch-class set analysis in equal temperaments, by default 24 notes to the
octave (quarter tones), with pitch class 0 on C.

Set classes are taken under transposition and inversion, and prime forms use
Rahn's rule, which differs from Forte's in a few classes (5-20 is (01568), not
(01378)). A set that also exists in 12 notes to the octave gets its Forte name.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

QUARTER_TONES = 24
SEMITONES = 12


def _rahn_key(form: tuple[int, ...], modulus: int) -> tuple[int, ...]:
    """Distances from the form's first pitch class, last first: the smaller
    key is the one more packed to the left."""
    return tuple((pc - form[0]) % modulus for pc in reversed(form[1:]))


def normal_form(pcs: Iterable[int], modulus: int = QUARTER_TONES) -> tuple[int, ...]:
    """The set's most compact ordering. Of symmetric sets' equally compact
    orderings, the one starting on the lowest pitch class."""
    ordered = sorted({pc % modulus for pc in pcs})
    if not ordered:
        return ()
    rotations = (tuple(ordered[i:] + ordered[:i]) for i, _ in enumerate(ordered))
    return min(rotations, key=lambda r: (_rahn_key(r, modulus), r[0]))


def prime_form(pcs: Iterable[int], modulus: int = QUARTER_TONES) -> tuple[int, ...]:
    """The set class's representative, starting on 0."""
    pcs = list(pcs)
    if not pcs:
        return ()
    forms = []
    for candidate in (pcs, [-pc for pc in pcs]):
        form = normal_form(candidate, modulus)
        forms.append(tuple((pc - form[0]) % modulus for pc in form))
    return min(forms, key=lambda form: _rahn_key(form, modulus))


def interval_class_vector(
    pcs: Iterable[int], modulus: int = QUARTER_TONES
) -> tuple[int, ...]:
    """How many times each interval class occurs. Entry `i` counts interval
    class `i + 1`, and the last entry is the half-octave."""
    ordered = sorted({pc % modulus for pc in pcs})
    vector = [0] * (modulus // 2)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            interval = (b - a) % modulus
            vector[min(interval, modulus - interval) - 1] += 1
    return tuple(vector)


@lru_cache(maxsize=None)
def _forte_name_of_semitones(pcs: tuple[int, ...]) -> str | None:
    # Imported here since music21 takes seconds to load, and only analysis needs it.
    import music21

    if not pcs:
        return None
    chord = music21.chord.Chord(list(pcs))
    cardinality, _, number = chord.forteClassTnI.partition("-")
    return f"{cardinality}-{'Z' if chord.hasZRelation else ''}{number}"


def forte_name(pcs: Iterable[int], modulus: int = QUARTER_TONES) -> str | None:
    """The set's Forte name, or None if it doesn't exist in 12 notes to the
    octave. A set of only quarter tones is such a set a quarter tone away."""
    prime = prime_form(pcs, modulus)
    step = modulus // SEMITONES
    if modulus % SEMITONES or any(pc % step for pc in prime):
        return None
    return _forte_name_of_semitones(prime_form((pc // step for pc in prime), SEMITONES))


@dataclass(frozen=True)
class PitchClassSetAnalysis:
    pitch_classes: tuple[int, ...]
    normal_form: tuple[int, ...]
    prime_form: tuple[int, ...]
    interval_class_vector: tuple[int, ...]
    forte_name: str | None

    @property
    def cardinality(self) -> int:
        return len(self.pitch_classes)


def analyse(pcs: Iterable[int], modulus: int = QUARTER_TONES) -> PitchClassSetAnalysis:
    pcs = sorted({pc % modulus for pc in pcs})
    return PitchClassSetAnalysis(
        pitch_classes=tuple(pcs),
        normal_form=normal_form(pcs, modulus),
        prime_form=prime_form(pcs, modulus),
        interval_class_vector=interval_class_vector(pcs, modulus),
        forte_name=forte_name(pcs, modulus),
    )
