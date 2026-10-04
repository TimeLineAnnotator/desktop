"""Chord and key literals for the query language's harmony lanes.

The query language searches TiLiA harmony timelines with chord symbols (``G7``, ``F#m7b5``,
``C/E``), Roman numerals (``V7``, ``bVI``, ``vii°7``, ``V65/V``) and keys
(``c``, ``Eb``). This module reads those literals and matches them against
TiLiA components; the query engine decides which components to try and which
key is in force. Standard library only: TiLiA's semantics were read from its
source (TiLiA 0.6.3) and re-implemented here without music21.

What TiLiA stores
-----------------
A harmony timeline holds two kinds of point component:

``HARMONY``, one chord, spelled in absolute terms
    ``step`` 0-6 (C D E F G A B) plus ``accidental`` (-2..2) is the root, so
    F# is step 3, accidental 1. ``quality`` is one of the 51 names in
    :data:`QUALITIES` (music21's chord kinds: "major", "dominant-seventh",
    "half-diminished-seventh", ...). ``inversion`` 0-3 says which chord tone is
    in the bass, counting in stacking order: root, third, fifth, seventh (a sus
    chord's 2nd/4th stands in for the third, a sixth chord's 6th for the
    seventh). ``applied_to`` 0-6 is the scale degree, counted in letter steps
    above the tonic of the key in force, whose key the chord belongs to: 0 =
    not applied, 4 = V. So D major with applied_to=4 under C major is V/V.
    TiLiA keeps the target as a bare step; it stores neither its accidental
    nor its mode.
``MODE``, one key
    ``step`` + ``accidental`` is the tonic, ``type`` is "major" or "minor".

No Roman numeral is stored. TiLiA works one out for display from the chord and
the key in force (``tilia/ui/timelines/harmony/utils.py``), and so does this
module.

Literals
--------
* A **chord symbol** starts with an upper-case letter A-G: root, then
  accidentals (``#``/``♯``, ``b``/``♭``, ``x``), then a quality suffix
  (``m``/``min``/``-``, ``dim``/``°``/``o``, ``aug``/``+``, ``7``,
  ``maj7``/``M7``/``Δ``, ``m7b5``/``ø``/``%``, ``mM7``, ``sus4``, ``9``, ...),
  then optionally ``/bass``.
* Anything else is read as a **Roman numeral**: accidentals (``b``, ``#``,
  ``-``), the numeral (``I``..``VII``, ``i``..``vii``), a quality mark (``°``
  or ``o`` diminished, ``ø`` or ``%`` half-diminished, ``+`` or ``aug``
  augmented, ``M``/``maj``/``Δ`` major seventh), a figure, and optionally
  ``/target`` (``V7/IV``). The names ``It+6``, ``Fr+6``, ``Ger+6`` (also
  ``It6``, ``Fr43``, ``Ger65``, ``Gr6``, ...) and ``N6`` are Roman numerals too,
  so :func:`is_chord_symbol` is False for ``Fr6`` and ``Ger6``.
* A **key** is a note name whose case gives the mode: ``C`` = C major, ``c`` =
  C minor, ``Eb`` = E-flat major, ``f#`` = F-sharp minor, ``bb`` = B-flat minor.
  ``C minor``, ``c major``, ``Cm`` and ``CM`` are accepted too.

Matching rules
--------------
* **Exact spelling.** Roots, slash basses and keys compare by letter and
  accidental, not by sound: ``F#`` does not match a Gb chord. A Roman
  numeral's degree is counted in letter steps (as TiLiA counts it), so Gb major
  under D major is ``bIV``, not ``III``.
* **Strict quality.** A literal names exactly one TiLiA quality. ``V`` matches
  major triads on 5̂ only, never V7; ``C`` never matches C7.
* **Inversions.** No figure and no bass means any inversion: ``V7`` matches V7
  in every position (``V7[inversion = 0]`` narrows it). A figure or a slash
  bass names one inversion: ``I6``/``I64``; ``V65``/``V43``/``V2`` (also
  ``V42``); ``G7/B``. ``I53``, ``V753`` and ``C/C`` ask for root position.
  9th/11th/13th, sixth, sus and power chords take no figures.
* **Sevenths come from the literal, never from the key.** As in TiLiA's own
  display and the DCML annotation standard: upper case + 7 is a dominant
  seventh, lower case + 7 a minor seventh, ``M7`` a major seventh (``IM7`` =
  ``Imaj7`` = ``IΔ7``), lower case + ``M7`` minor-major, ``ø7`` half-diminished,
  ``°7`` diminished, ``+7`` augmented, ``+M7`` augmented-major. So ``IV7`` under
  C is F7 and Fmaj7 is ``IVM7``. 9ths, 11ths and 13ths follow the same pattern.
* **Roman numerals go through the key in force.** The numeral picks a degree
  of that key (major scale or natural minor) and the accidentals move it.
  In minor, ^6 and ^7 follow music21's "cautionary" reading: numerals of minor,
  diminished and half-diminished quality (``vi``, ``vii°``, ``viiø7``) stand
  on the raised degree, all others (``VI``, ``VII``, ``VII7``) on the natural
  one; a ``#`` on such a raised numeral or a ``b`` on a natural one is a
  courtesy accidental. So under c minor ``vii°`` and ``#vii°`` are both B°,
  ``VII`` and ``bVII`` both Bb, ``VI`` is Ab, ``#VI`` A major and ``bvi`` Ab
  minor. TiLiA needs this leniency: it displays B° under c minor as ``#viio``,
  yet its own text entry (music21's default reading) takes ``#viio`` for B#°.
* **Applied chords** resolve the target in the key in force (its case gives the
  mode of the tonicized key: ``/V`` major, ``/ii`` minor), then the numeral in
  that key. A literal with a target matches only chords stored with that
  ``applied_to``; a literal without one matches only unapplied chords. A D
  major chord stored as II under C is not ``V/V``, and V/V is not ``II``: the
  analyst's reading counts. Because the target's accidental is not stored,
  ``V7/bVI`` matches Eb7 stored with applied_to=5 under C major.
* **No key, no Roman numeral.** With ``key=None``, Roman numerals never match;
  chord symbols do not need a key. The root-less names ``It+6``, ``Fr+6``,
  ``Ger+6`` and ``N6`` are the exception: they match TiLiA's Italian, French,
  German and Neapolitan qualities whatever the stored root, applied target or
  key, because TiLiA labels them that way in both display modes.
* **A slash bass must be a chord tone, up to the seventh.** That is all TiLiA
  can store. ``C/D`` or ``C9/D`` raises :class:`HarmonyError` instead of
  silently matching nothing.

Display (:func:`chord_props`)
-----------------------------
``symbol`` is lead-sheet spelling (``G7/B``, ``Bbmaj7``, ``F#m7b5``,
``Ebdim7``, ``Caug``). ``roman`` is textbook spelling with the inversion figure
(``V65/V``, ``vii°7``, ``bVI``, ``I64``); root-position triads and sevenths
carry no ``53``/``753``. For an applied chord the target is written in the case
of the key's diatonic triad (ii iii IV V vi vii in major; ii III iv V VI VII in
minor). When the root needs an accidental, it goes on the target if that leaves
the numeral plain: Eb7 applied to VI under C is ``V7/bVI``. Every derived
label parses back to a literal that matches its chord. Where this differs from
TiLiA's own label (TiLiA writes B° under c minor as ``#viio`` and omits all
accidentals on applied chords) the label here is the one that means the
stored chord.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

__all__ = [
    "HarmonyError",
    "ChordSpec",
    "KeySpec",
    "QUALITIES",
    "is_chord_symbol",
    "parse_chord",
    "chord_matches",
    "chord_props",
    "parse_key",
    "key_matches",
    "key_props",
]


class HarmonyError(ValueError):
    """A chord or key literal that cannot be read."""


# --------------------------------------------------------------------------- #
# Pitch spelling. A pitch is (step 0-6, alteration in semitones).
# --------------------------------------------------------------------------- #
LETTERS = "CDEFGAB"  # TiLiA's step 0..6
_NATURAL_PC = (0, 2, 4, 5, 7, 9, 11)
_MAJOR = (0, 2, 4, 5, 7, 9, 11)  # semitones of each degree above the tonic
_MINOR = (0, 2, 3, 5, 7, 8, 10)  # natural minor (^6/^7: _numeral_root)
_ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII")

Pitch = tuple[int, int]


def _acc_text(alter: int) -> str:
    return "#" * alter if alter > 0 else "b" * -alter


def _pitch_name(p: Pitch) -> str:
    return LETTERS[p[0]] + _acc_text(p[1])


def _transpose(p: Pitch, steps: int, semis: int) -> Pitch:
    """``p`` moved up by an interval of ``steps`` letters and ``semis`` semitones."""
    step = (p[0] + steps) % 7
    d = (_NATURAL_PC[p[0]] + p[1] + semis - _NATURAL_PC[step]) % 12
    return step, (d - 12 if d > 6 else d)


def _degree(tonic: Pitch, mode: str, degree: int) -> Pitch:
    return _transpose(tonic, degree, (_MINOR if mode == "minor" else _MAJOR)[degree])


def _numeral_root(
    tonic: Pitch, mode: str, degree: int, alter: int, raised: bool
) -> Pitch:
    """The root a numeral names: ``degree`` (0 = I) of the key, moved by the
    numeral's ``alter`` (b = -1). ``raised`` is True for minor, diminished and
    half-diminished numerals: in minor they sit on raised ^6/^7.

    This is music21's ``Minor67Default.CAUTIONARY``: on ^6/^7 of a minor key a
    sharp counts from the natural degree (``#vii°`` = ``vii°`` = B in c) and a
    flat from the raised one (``bVI`` = ``VI`` = Ab, ``bvi`` = Ab minor).
    """
    step, base = _degree(tonic, mode, degree)
    if mode == "minor" and degree in (5, 6):
        if alter == 0:
            alter = 1 if raised else 0
        elif alter < 0:
            alter += 1
    return step, base + alter


def _find_alter(tonic: Pitch, mode: str, degree: int, raised: bool, root: Pitch) -> int:
    """The accidental a numeral needs to name ``root``; the plainest wins."""
    for alter in (0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6):
        if _numeral_root(tonic, mode, degree, alter, raised) == root:
            return alter
    raise AssertionError(f"no accidental reaches {root} from {tonic}")  # unreachable


def _accidentals(text: str, literal: str, flat: str = "b", spelled: bool = True) -> int:
    """'#' = +1, 'x' = +2, the ``flat`` characters = -1 each; no mixing. A
    ``spelled`` note (root, bass, tonic) has at most two, as in TiLiA."""
    up = text.count("#") + 2 * text.count("x")
    down = sum(text.count(c) for c in flat)
    if up and down:
        raise HarmonyError(f"{literal!r}: sharps and flats mixed in one accidental")
    if spelled and max(up, down) > 2:
        raise HarmonyError(
            f"{literal!r}: TiLiA spells notes with at most a double " "sharp or flat"
        )
    return up - down


# --------------------------------------------------------------------------- #
# The qualities TiLiA knows (tilia/timelines/harmony/constants.py), in order.
# --------------------------------------------------------------------------- #
QUALITIES = (
    "major",
    "minor",
    "augmented",
    "diminished",
    "dominant-seventh",
    "major-seventh",
    "minor-major-seventh",
    "minor-seventh",
    "augmented-major-seventh",
    "augmented-seventh",
    "half-diminished-seventh",
    "diminished-seventh",
    "seventh-flat-five",
    "major-sixth",
    "minor-sixth",
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
    "dominant-11th",
    "major-11th",
    "minor-major-11th",
    "minor-11th",
    "augmented-major-11th",
    "augmented-11th",
    "half-diminished-11th",
    "diminished-11th",
    "major-13th",
    "dominant-13th",
    "minor-major-13th",
    "minor-13th",
    "augmented-major-13th",
    "augmented-dominant-13th",
    "half-diminished-13th",
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
)

# Root-less names: TiLiA labels these qualities without their root or target
# (utils._handle_special_qualities, HarmonyUI.letter_symbol_label).
_SPECIAL = {"Neapolitan": "N6", "Italian": "It+6", "French": "Fr+6", "German": "Ger+6"}

# chord-tone intervals: name -> (letter steps, semitones) above the root
_IV = {
    "1": (0, 0),
    "2": (1, 2),
    "b3": (2, 3),
    "3": (2, 4),
    "4": (3, 5),
    "#4": (3, 6),
    "b5": (4, 6),
    "5": (4, 7),
    "#5": (4, 8),
    "6": (5, 9),
    "#6": (5, 10),
    "bb7": (6, 9),
    "b7": (6, 10),
    "7": (6, 11),
    "b9": (1, 1),
    "9": (1, 2),
    "#9": (1, 3),
    "11": (3, 5),
    "13": (5, 9),
}


@dataclass(frozen=True)
class _Quality:
    name: str
    tones: tuple[tuple[int, int], ...]  # chord tones in TiLiA's inversion order
    symbol: str  # chord-symbol suffix
    family: str | None  # "triad"/"seventh" take inversion figures
    mark: str  # Roman suffix (triad/seventh: the mark only)

    @property
    def lower(self) -> bool:
        """Written with a lower-case numeral (TiLiA's rule); raised ^6/^7 in minor."""
        return self.name.startswith(("minor", "diminished", "half-diminished"))


_TABLE = (
    # name                          chord tones            symbol    family     Roman
    ("major", "1 3 5", "", "triad", ""),
    ("minor", "1 b3 5", "m", "triad", ""),
    ("augmented", "1 3 #5", "aug", "triad", "+"),
    ("diminished", "1 b3 b5", "dim", "triad", "°"),
    ("dominant-seventh", "1 3 5 b7", "7", "seventh", ""),
    ("major-seventh", "1 3 5 7", "maj7", "seventh", "M"),
    ("minor-major-seventh", "1 b3 5 7", "mM7", "seventh", "M"),
    ("minor-seventh", "1 b3 5 b7", "m7", "seventh", ""),
    ("augmented-major-seventh", "1 3 #5 7", "+M7", "seventh", "+M"),
    ("augmented-seventh", "1 3 #5 b7", "+7", "seventh", "+"),
    ("half-diminished-seventh", "1 b3 b5 b7", "m7b5", "seventh", "ø"),
    ("diminished-seventh", "1 b3 b5 bb7", "dim7", "seventh", "°"),
    ("seventh-flat-five", "1 3 b5 b7", "7b5", None, "7b5"),
    ("major-sixth", "1 3 5 6", "6", None, "add6"),
    ("minor-sixth", "1 b3 5 6", "m6", None, "add6"),
    ("major-ninth", "1 3 5 7 9", "maj9", None, "M9"),
    ("dominant-ninth", "1 3 5 b7 9", "9", None, "9"),
    ("minor-major-ninth", "1 b3 5 7 9", "mM9", None, "M9"),
    ("minor-ninth", "1 b3 5 b7 9", "m9", None, "9"),
    ("augmented-major-ninth", "1 3 #5 7 9", "+M9", None, "+M9"),
    ("augmented-dominant-ninth", "1 3 #5 b7 9", "+9", None, "+9"),
    ("half-diminished-ninth", "1 b3 b5 b7 9", "m9b5", None, "ø9"),
    ("half-diminished-minor-ninth", "1 b3 b5 b7 b9", "m7b5b9", None, "øb9"),
    ("diminished-ninth", "1 b3 b5 bb7 9", "dim9", None, "°9"),
    ("diminished-minor-ninth", "1 b3 b5 bb7 b9", "dim7b9", None, "°b9"),
    ("dominant-11th", "1 3 5 b7 9 11", "11", None, "11"),
    ("major-11th", "1 3 5 7 9 11", "maj11", None, "M11"),
    ("minor-major-11th", "1 b3 5 7 9 11", "mM11", None, "M11"),
    ("minor-11th", "1 b3 5 b7 9 11", "m11", None, "11"),
    ("augmented-major-11th", "1 3 #5 7 9 11", "+M11", None, "+M11"),
    ("augmented-11th", "1 3 #5 b7 9 11", "+11", None, "+11"),
    ("half-diminished-11th", "1 b3 b5 b7 9 11", "m11b5", None, "ø11"),
    ("diminished-11th", "1 b3 b5 bb7 9 11", "dim11", None, "°11"),
    ("major-13th", "1 3 5 7 9 11 13", "maj13", None, "M13"),
    ("dominant-13th", "1 3 5 b7 9 11 13", "13", None, "13"),
    ("minor-major-13th", "1 b3 5 7 9 11 13", "mM13", None, "M13"),
    ("minor-13th", "1 b3 5 b7 9 11 13", "m13", None, "13"),
    ("augmented-major-13th", "1 3 #5 7 9 11 13", "+M13", None, "+M13"),
    ("augmented-dominant-13th", "1 3 #5 b7 9 11 13", "+13", None, "+13"),
    ("half-diminished-13th", "1 b3 b5 b7 9 11 13", "m13b5", None, "ø13"),
    ("suspended-second", "1 2 5", "sus2", None, "sus2"),
    ("suspended-fourth", "1 4 5", "sus4", None, "sus4"),
    ("suspended-fourth-seventh", "1 4 5 b7", "7sus4", None, "7sus4"),
    ("pedal", "1", "ped", None, "ped"),
    ("power", "1 5", "5", None, "5"),
    ("Tristan", "1 #4 #6 #9", "tristan", None, "tristan"),
)
_QUAL = {
    name: _Quality(name, tuple(_IV[i] for i in tones.split()), sym, fam, mark)
    for name, tones, sym, fam, mark in _TABLE
}
assert set(_QUAL) | set(_SPECIAL) == set(QUALITIES)

# Chord-symbol suffixes, after _norm_symbol_suffix. The first is the canonical one.
_SYMBOL_ALIASES = {
    "major": ("", "M", "maj", "major"),
    "minor": ("m", "min", "mi", "minor"),
    "augmented": ("aug", "+"),
    "diminished": ("dim", "o"),
    "dominant-seventh": ("7", "dom7", "dom"),
    "major-seventh": ("maj7", "M7", "ma7", "7M", "7maj"),
    "minor-major-seventh": ("mM7", "mmaj7", "minmaj7", "m#7", "m7M"),
    "minor-seventh": ("m7", "min7", "mi7"),
    "augmented-major-seventh": (
        "+M7",
        "+maj7",
        "augmaj7",
        "augM7",
        "maj7#5",
        "M7#5",
        "maj7+",
        "M7+",
    ),
    "augmented-seventh": ("+7", "7+", "aug7", "7#5", "7aug"),
    "half-diminished-seventh": ("m7b5", "ø7", "ø", "min7b5", "mi7b5", "m7-5"),
    "diminished-seventh": ("dim7", "o7"),
    "seventh-flat-five": ("7b5", "7-5", "dom7dim5", "7dim5"),
    "major-sixth": ("6", "M6", "maj6", "add6"),
    "minor-sixth": ("m6", "min6", "madd6"),
    "major-ninth": ("maj9", "M9"),
    "dominant-ninth": ("9", "dom9"),
    "minor-major-ninth": ("mM9", "mmaj9", "minmaj9"),
    "minor-ninth": ("m9", "min9"),
    "augmented-major-ninth": ("+M9", "+maj9", "augmaj9", "maj9#5", "M9#5"),
    "augmented-dominant-ninth": ("+9", "9#5", "aug9", "9+"),
    "half-diminished-ninth": ("m9b5", "ø9"),
    "half-diminished-minor-ninth": ("m7b5b9", "øb9", "ø7b9"),
    "diminished-ninth": ("dim9", "o9"),
    "diminished-minor-ninth": ("dim7b9", "dimb9", "ob9", "o7b9"),
    "dominant-11th": ("11", "dom11"),
    "major-11th": ("maj11", "M11"),
    "minor-major-11th": ("mM11", "mmaj11", "minmaj11"),
    "minor-11th": ("m11", "min11"),
    "augmented-major-11th": ("+M11", "+maj11", "augmaj11"),
    "augmented-11th": ("+11", "aug11", "11#5"),
    "half-diminished-11th": ("m11b5", "ø11"),
    "diminished-11th": ("dim11", "o11"),
    "major-13th": ("maj13", "M13"),
    "dominant-13th": ("13", "dom13"),
    "minor-major-13th": ("mM13", "mmaj13", "minmaj13"),
    "minor-13th": ("m13", "min13"),
    "augmented-major-13th": ("+M13", "+maj13", "augmaj13"),
    "augmented-dominant-13th": ("+13", "aug13", "13#5"),
    "half-diminished-13th": ("m13b5", "ø13"),
    "suspended-second": ("sus2",),
    "suspended-fourth": ("sus4", "sus"),
    "suspended-fourth-seventh": ("7sus4", "7sus"),
    "pedal": ("ped", "pedal"),
    "power": ("5", "power"),
    "Tristan": ("tristan", "trist"),
}
_SYMBOL_SUFFIX = {
    alias: q for q, aliases in _SYMBOL_ALIASES.items() for alias in aliases
}
assert len(_SYMBOL_SUFFIX) == sum(map(len, _SYMBOL_ALIASES.values())), "duplicate alias"
assert all(_SYMBOL_ALIASES[q][0] == _QUAL[q].symbol for q in _QUAL)

# Roman numerals: the figure (body) after the quality mark. Triad and seventh
# figures fix the inversion; other bodies name a quality family.
_TRIAD_FIG = {"": None, "53": 0, "6": 1, "63": 1, "64": 2}
_SEVENTH_FIG = {
    "7": None,
    "753": 0,
    "65": 1,
    "653": 1,
    "43": 2,
    "643": 2,
    "42": 3,
    "642": 3,
    "2": 3,
}
# (mark, body kind) -> quality on an upper-case numeral, on a lower-case one
_ROMAN_QUALITY = {
    ("", "triad"): ("major", "minor"),
    ("o", "triad"): ("diminished",) * 2,
    ("+", "triad"): ("augmented",) * 2,
    ("", "seventh"): ("dominant-seventh", "minor-seventh"),
    ("M", "seventh"): ("major-seventh", "minor-major-seventh"),
    ("o", "seventh"): ("diminished-seventh",) * 2,
    ("ø", "seventh"): ("half-diminished-seventh",) * 2,
    ("+", "seventh"): ("augmented-seventh",) * 2,
    ("+M", "seventh"): ("augmented-major-seventh",) * 2,
    ("", "7b5"): ("seventh-flat-five", "half-diminished-seventh"),
    ("", "add6"): ("major-sixth", "minor-sixth"),
    ("", "9"): ("dominant-ninth", "minor-ninth"),
    ("M", "9"): ("major-ninth", "minor-major-ninth"),
    ("+", "9"): ("augmented-dominant-ninth",) * 2,
    ("+M", "9"): ("augmented-major-ninth",) * 2,
    ("ø", "9"): ("half-diminished-ninth",) * 2,
    ("o", "9"): ("diminished-ninth",) * 2,
    ("ø", "b9"): ("half-diminished-minor-ninth",) * 2,
    ("o", "b9"): ("diminished-minor-ninth",) * 2,
    ("", "11"): ("dominant-11th", "minor-11th"),
    ("M", "11"): ("major-11th", "minor-major-11th"),
    ("+", "11"): ("augmented-11th",) * 2,
    ("+M", "11"): ("augmented-major-11th",) * 2,
    ("ø", "11"): ("half-diminished-11th",) * 2,
    ("o", "11"): ("diminished-11th",) * 2,
    ("", "13"): ("dominant-13th", "minor-13th"),
    ("M", "13"): ("major-13th", "minor-major-13th"),
    ("+", "13"): ("augmented-dominant-13th",) * 2,
    ("+M", "13"): ("augmented-major-13th",) * 2,
    ("ø", "13"): ("half-diminished-13th",) * 2,
    **{
        ("", body): (q,) * 2
        for body, q in (
            ("sus2", "suspended-second"),
            ("sus4", "suspended-fourth"),
            ("sus", "suspended-fourth"),
            ("7sus4", "suspended-fourth-seventh"),
            ("7sus", "suspended-fourth-seventh"),
            ("5", "power"),
            ("power", "power"),
            ("ped", "pedal"),
            ("pedal", "pedal"),
            ("trist", "Tristan"),
            ("tristan", "Tristan"),
        )
    },
}
_TRIAD_FIGURES = ("", "6", "64")
_SEVENTH_FIGURES = ("7", "65", "43", "2")

# Default mode of an applied chord's target, per degree of the key in force:
# the diatonic triad's (I ii iii IV V vi vii / i ii III iv V VI VII).
_TARGET_MODE = {
    "major": ("major", "minor", "minor", "major", "major", "minor", "minor"),
    "minor": ("minor", "minor", "major", "minor", "major", "major", "major"),
}


def _roman_suffix(
    q: _Quality, inversion: int | None, explicit_root: bool = False
) -> str:
    """Quality mark plus inversion figure: ``"°"``, ``"65"``, ``"M2"``, ``"ø7"``."""
    if q.family == "triad":
        if inversion is None or not 0 <= inversion < 3:
            return q.mark
        return q.mark + (
            "53" if inversion == 0 and explicit_root else _TRIAD_FIGURES[inversion]
        )
    if q.family == "seventh":
        if inversion is None or not 0 <= inversion < 4:
            return q.mark + "7"
        return q.mark + (
            "753" if inversion == 0 and explicit_root else _SEVENTH_FIGURES[inversion]
        )
    return q.mark


def _numeral_text(degree: int, lower: bool) -> str:
    return _ROMANS[degree].lower() if lower else _ROMANS[degree]


# --------------------------------------------------------------------------- #
# Literals
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChordSpec:
    """A parsed chord literal. ``kind`` is "symbol" or "roman"; ``inversion``
    None means any inversion. Symbols carry ``root``; Roman numerals carry
    ``degree`` (0 = I), ``alter`` (their accidental) and, if applied,
    ``target`` = (degree, alter, "major"/"minor"). ``special`` marks the
    root-less It+6/Fr+6/Ger+6/N6. ``canonical`` is the normalized spelling."""

    kind: str
    text: str
    quality: str
    inversion: int | None = None
    root: Pitch | None = None
    degree: int | None = None
    alter: int = 0
    target: tuple[int, int, str] | None = None
    special: bool = False
    canonical: str = ""

    @property
    def needs_key(self) -> bool:
        """Whether matching needs the key in force (Roman numerals do)."""
        return self.kind == "roman" and not self.special


@dataclass(frozen=True)
class KeySpec:
    """A parsed key literal: ``tonic`` = (step, alter), ``mode`` "major"/"minor"."""

    text: str
    tonic: Pitch
    mode: str
    canonical: str = ""


_DIGIT_SLASH = re.compile(r"(?<=\d)/(?=\d)")  # 6/5 -> 65, 4/3 -> 43
_SPECIAL_RE = (
    (re.compile(r"It(?:\+?6\+?|\+)?", re.I), "Italian"),
    (re.compile(r"Fr(?:\+?(?:6|43)\+?|\+)?", re.I), "French"),
    (re.compile(r"(?:Ger|Gr)(?:\+?(?:6|65)\+?|\+)?", re.I), "German"),
    (re.compile(r"N6?"), "Neapolitan"),
)
_NOTE_HEAD = re.compile(r"([A-G])([#bx]*)(.*)")
_NOTE = re.compile(r"([A-G])([#bx]*)")
_ROMAN_HEAD = re.compile(r"([#b-]*)([IViv]+)(.*)")
_TARGET = re.compile(r"([#b-]*)([IViv]+)(o|ø|\+)?")
_ROMAN_BODY = re.compile(r"(\+M|o|ø|\+|M)?(.*)")
_DELTA_ALONE = re.compile(r"[Δ∆](?!\d)")  # CΔ = Cmaj7, but CΔ9 = Cmaj9
_DELTA = re.compile(r"[Δ∆]")
_SYMBOL_WORDS = re.compile(
    r"maj|min|dim|aug|sus|dom|add|pedal|ped|power|tristan|trist", re.I
)
_ROMAN_WORDS = re.compile(r"sus|add|pedal|ped|power|tristan|trist", re.I)
_ROMAN_MARKS = (
    (re.compile(r"maj", re.I), "M"),
    (re.compile(r"aug", re.I), "+"),
    (re.compile(r"dim", re.I), "o"),
)


def _lower(m: re.Match[str]) -> str:
    return m.group(0).lower()


def _clean(text: str) -> str:
    """Drop whitespace, unify accidentals, join figures written 6/5."""
    t = "".join(text.split())
    t = t.replace("𝄪", "##").replace("𝄫", "bb").replace("♯", "#").replace("♭", "b")
    return _DIGIT_SLASH.sub("", t)


def _special(t: str) -> str | None:
    for rx, quality in _SPECIAL_RE:
        if rx.fullmatch(t):
            return quality
    return None


def _norm_marks(s: str) -> str:
    s = s.replace("(", "").replace(")", "")
    s = s.replace("°", "o").replace("º", "o").replace("Ø", "ø").replace("%", "ø")
    return s


def _norm_symbol_suffix(s: str) -> str:
    s = _DELTA.sub("maj", _DELTA_ALONE.sub("maj7", _norm_marks(s)))
    if s.startswith("-"):  # C-7 = Cm7
        s = "m" + s[1:]
    return _SYMBOL_WORDS.sub(_lower, s)


def _norm_roman_suffix(s: str) -> str:
    s = _DELTA.sub("M", _DELTA_ALONE.sub("M7", _norm_marks(s)))
    for rx, mark in _ROMAN_MARKS:
        s = rx.sub(mark, s)
    return _ROMAN_WORDS.sub(_lower, s)


def is_chord_symbol(text: str) -> bool:
    """True if ``text`` reads as a chord symbol: it starts with A-G (upper case).
    ``Fr6``/``Ger6`` are augmented-sixth names, read as Roman numerals."""
    if not isinstance(text, str):
        return False
    t = _clean(text)
    return bool(t) and t[0] in "ABCDEFG" and _special(t) is None


def parse_chord(text: str) -> ChordSpec:
    """Read a chord symbol or Roman numeral (module docstring has the grammar)."""
    if not isinstance(text, str):
        raise HarmonyError(f"a chord literal must be text, not {type(text).__name__}")
    return _parse_chord(text)


@lru_cache(maxsize=1024)
def _parse_chord(text: str) -> ChordSpec:
    t = _clean(text)
    if not t:
        raise HarmonyError("empty chord literal")
    special = _special(t)
    if special:
        return ChordSpec(
            "roman", text, special, special=True, canonical=_SPECIAL[special]
        )
    if t[0] in "ABCDEFG":
        return _parse_symbol(text, t)
    if _ROMAN_HEAD.match(t):
        return _parse_roman(text, t)
    if t[0] in "abcdefg":
        raise HarmonyError(
            f"{text!r}: a chord symbol starts with an upper-case letter "
            f"A-G ({t[0].upper()}{t[1:]}); lower case is a minor key"
        )
    raise HarmonyError(
        f"{text!r} is neither a chord symbol (G7, F#m7b5, C/E) nor a "
        "Roman numeral (V7, bVI, vii°7, V65/V)"
    )


def _parse_symbol(text: str, t: str) -> ChordSpec:
    head, slash, bass_text = t.partition("/")
    m = _NOTE_HEAD.fullmatch(head)
    root = (LETTERS.index(m.group(1)), _accidentals(m.group(2), text))
    quality = _SYMBOL_SUFFIX.get(_norm_symbol_suffix(m.group(3)))
    if quality is None:
        raise HarmonyError(
            f"{text!r}: unknown chord quality {m.group(3)!r} after "
            f"{_pitch_name(root)} (try m, dim, aug, 7, maj7, m7, m7b5, "
            "dim7, sus4, 9 ...)"
        )
    q = _QUAL[quality]
    inversion = None
    if slash:
        b = _NOTE.fullmatch(bass_text)
        if not b:
            raise HarmonyError(
                f"{text!r}: after '/' a chord symbol takes a bass note "
                f"(C/E, G7/B), not {bass_text!r}"
            )
        # a bass is not stored, only implied: Cbdim7/Bbbb is a real third inversion
        bass = (
            LETTERS.index(b.group(1)),
            _accidentals(b.group(2), text, spelled=False),
        )
        members = [_transpose(root, *iv) for iv in q.tones]
        if bass not in members:
            raise HarmonyError(
                f"{text!r}: {_pitch_name(bass)} is not a chord tone of "
                f"{_pitch_name(root)}{q.symbol} ({', '.join(map(_pitch_name, members))}); "
                "TiLiA can only put a chord tone in the bass"
            )
        inversion = members.index(bass)
        if inversion > 3:
            raise HarmonyError(
                f"{text!r}: TiLiA stores inversions up to the seventh in "
                "the bass (inversion 0-3)"
            )
    canonical = _pitch_name(root) + q.symbol
    if inversion is not None:
        canonical += "/" + _pitch_name(_transpose(root, *q.tones[inversion]))
    return ChordSpec("symbol", text, quality, inversion, root=root, canonical=canonical)


def _parse_numeral(numeral: str, literal: str) -> tuple[int, bool]:
    if numeral.upper() not in _ROMANS or numeral not in (
        numeral.upper(),
        numeral.lower(),
    ):
        raise HarmonyError(
            f"{literal!r}: {numeral!r} is not a Roman numeral (I-VII, i-vii)"
        )
    return _ROMANS.index(numeral.upper()), numeral.islower()


def _parse_roman(text: str, t: str) -> ChordSpec:
    primary, *targets = t.split("/")
    if len(targets) > 1:
        raise HarmonyError(
            f"{text!r}: TiLiA stores a single applied target (V/V); "
            "a chain like V/V/V cannot match"
        )
    m = _ROMAN_HEAD.fullmatch(primary)
    if not m:
        raise HarmonyError(f"{text!r} is not a Roman numeral (V7, bVI, vii°7, V65/V)")
    alter = _accidentals(m.group(1), text, flat="b-", spelled=False)
    degree, lower = _parse_numeral(m.group(2), text)
    quality, inversion = _roman_quality(m.group(3), lower, text, m.group(2))

    target = None
    if targets:
        tm = _TARGET.fullmatch(_norm_roman_suffix(targets[0]))
        if not tm:
            raise HarmonyError(
                f"{text!r}: the applied target must be a plain numeral "
                f"(V/V, V7/ii, vii°7/bVI), not {targets[0]!r}"
            )
        t_degree, t_lower = _parse_numeral(tm.group(2), text)
        t_mode = (
            "minor"
            if tm.group(3) in ("o", "ø")
            else "major"
            if tm.group(3) == "+"
            else "minor"
            if t_lower
            else "major"
        )
        target = (
            t_degree,
            _accidentals(tm.group(1), text, flat="b-", spelled=False),
            t_mode,
        )

    q = _QUAL[quality]
    canonical = (
        _acc_text(alter)
        + _numeral_text(degree, q.lower)
        + _roman_suffix(q, inversion, explicit_root=True)
    )
    if target:
        canonical += (
            "/" + _acc_text(target[1]) + _numeral_text(target[0], target[2] == "minor")
        )
    return ChordSpec(
        "roman",
        text,
        quality,
        inversion,
        degree=degree,
        alter=alter,
        target=target,
        canonical=canonical,
    )


def _roman_quality(
    rest: str, lower: bool, text: str, numeral: str
) -> tuple[str, int | None]:
    """Quality and inversion from what follows the numeral (``"o65"``, ``"M7"``)."""
    mark, body = _ROMAN_BODY.fullmatch(_norm_roman_suffix(rest)).groups()
    mark = mark or ""
    if body in _TRIAD_FIG:
        kind, inversion = "triad", _TRIAD_FIG[body]
        if mark == "ø" and body == "":  # viiø: there is no ø triad
            return "half-diminished-seventh", None
    elif body in _SEVENTH_FIG:
        kind, inversion = "seventh", _SEVENTH_FIG[body]
    else:
        kind, inversion = body, None
    pair = _ROMAN_QUALITY.get((mark, kind))
    if pair:
        return pair[lower], inversion
    if mark in ("M", "+M") and kind == "triad":
        hint = "'M' marks a major seventh: write " + numeral + mark + "7"
    elif mark == "ø" and kind == "triad":
        hint = "half-diminished chords are sevenths: ø7, ø65, ø43, ø2"
    elif kind == "b9":
        hint = "TiLiA has a minor ninth only on half-diminished (øb9) and diminished (°b9) chords"
    elif (mark, kind) == ("o", "13"):
        hint = "TiLiA has no diminished 13th chord"
    else:
        hint = "expected a figure such as 6, 64, 7, 65, 43, 2, 9 or a mark °, ø, +, M7"
    raise HarmonyError(f"{text!r}: cannot read {rest!r} after {numeral} ({hint})")


_KEY_RE = re.compile(r"([A-Ga-g])([#bx]*)-?((?i:major|minor|maj|min)|M|m)?")


def parse_key(text: str) -> KeySpec:
    """Read a key: ``C`` = C major, ``c`` = C minor, ``Eb``, ``f#``, ``bb`` (B-flat
    minor); a mode word (``C minor``, ``Cm``) overrides the letter's case."""
    if not isinstance(text, str):
        raise HarmonyError(f"a key must be text, not {type(text).__name__}")
    return _parse_key(text)


@lru_cache(maxsize=256)
def _parse_key(text: str) -> KeySpec:
    t = "".join(text.split()).replace("♯", "#").replace("♭", "b")
    m = _KEY_RE.fullmatch(t)
    if not m:
        raise HarmonyError(f"{text!r} is not a key: write C (major), c (minor), Eb, f#")
    word = m.group(3)
    if word is None:
        mode = "minor" if m.group(1).islower() else "major"
    elif word in ("M", "m"):
        mode = "major" if word == "M" else "minor"
    else:
        mode = "major" if word.lower().startswith("maj") else "minor"
    tonic = (LETTERS.index(m.group(1).upper()), _accidentals(m.group(2), text))
    name = _pitch_name(tonic)
    return KeySpec(text, tonic, mode, name if mode == "major" else name.lower())


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _chord_fields(chord: dict[str, Any]) -> tuple[int, int, str, int, int]:
    """(step, accidental, quality, inversion, applied_to) with TiLiA's defaults."""
    return (
        _int(chord.get("step")) % 7,
        _int(chord.get("accidental")),
        chord.get("quality") or "major",
        _int(chord.get("inversion")),
        _int(chord.get("applied_to")) % 7,
    )


def _key_fields(mode: dict[str, Any]) -> tuple[int, int, str]:
    return (
        _int(mode.get("step")) % 7,
        _int(mode.get("accidental")),
        "minor" if mode.get("type") == "minor" else "major",
    )


@lru_cache(maxsize=2048)
def _resolve(spec: ChordSpec, key: tuple[int, int, str]) -> Pitch:
    """The root a Roman numeral names under ``key``."""
    tonic, mode = key[:2], key[2]
    if spec.target:
        t_degree, t_alter, t_mode = spec.target
        tonic = _numeral_root(tonic, mode, t_degree, t_alter, t_mode == "minor")
        mode = t_mode
    return _numeral_root(
        tonic, mode, spec.degree, spec.alter, _QUAL[spec.quality].lower
    )


def chord_matches(
    spec: ChordSpec, chord: dict[str, Any], key: dict[str, Any] | None
) -> bool:
    """Does the HARMONY component ``chord`` match ``spec`` under the MODE
    component ``key`` in force (None: no key precedes the chord)?"""
    step, alter, quality, inversion, applied = _chord_fields(chord)
    if quality != spec.quality:
        return False
    if spec.special:
        return True
    if spec.inversion is not None and inversion != spec.inversion:
        return False
    if spec.kind == "symbol":
        return (step, alter) == spec.root
    if key is None:
        return False
    if applied != (spec.target[0] if spec.target else 0):
        return False
    return (step, alter) == _resolve(spec, _key_fields(key))


def key_matches(spec: KeySpec, mode: dict[str, Any]) -> bool:
    """Does the MODE component ``mode`` match ``spec`` (tonic spelling and mode)?"""
    step, alter, typ = _key_fields(mode)
    return (step, alter) == spec.tonic and typ == spec.mode


# --------------------------------------------------------------------------- #
# Display
# --------------------------------------------------------------------------- #
def _roman_label(
    root: Pitch, q: _Quality, inversion: int, applied: int, key: tuple[int, int, str]
) -> str:
    tonic, mode = key[:2], key[2]
    suffix = _roman_suffix(q, inversion)
    if not applied:
        degree = (root[0] - tonic[0]) % 7
        alter = _find_alter(tonic, mode, degree, q.lower, root)
        return _acc_text(alter) + _numeral_text(degree, q.lower) + suffix
    degree = (root[0] - tonic[0] - applied) % 7
    default = _TARGET_MODE[mode][applied]
    other = "minor" if default == "major" else "major"
    # Prefer a plain numeral: put any accidental on the target (V7/bVI).
    for t_alter, t_mode in (
        (0, default),
        (0, other),
        (-1, "major"),
        (1, "major"),
        (-1, "minor"),
        (1, "minor"),
        (-2, "major"),
        (2, "major"),
    ):
        t_tonic = _numeral_root(tonic, mode, applied, t_alter, t_mode == "minor")
        if _numeral_root(t_tonic, t_mode, degree, 0, q.lower) == root:
            alter = 0
            break
    else:
        t_alter, t_mode = 0, default
        t_tonic = _numeral_root(tonic, mode, applied, 0, default == "minor")
        alter = _find_alter(t_tonic, t_mode, degree, q.lower, root)
    return (
        _acc_text(alter)
        + _numeral_text(degree, q.lower)
        + suffix
        + "/"
        + _acc_text(t_alter)
        + _numeral_text(applied, t_mode == "minor")
    )


@lru_cache(maxsize=4096)
def _labels(
    step: int,
    alter: int,
    quality: str,
    inversion: int,
    applied: int,
    key: tuple[int, int, str] | None,
) -> tuple[str, str | None, str | None]:
    """(symbol, roman, bass) of one chord."""
    root = (step, alter)
    if quality in _SPECIAL:
        return _SPECIAL[quality], _SPECIAL[quality], None
    q = _QUAL.get(quality)
    if q is None:  # not a TiLiA quality
        return f"{_pitch_name(root)}[{quality}]", None, None
    bass = (
        _transpose(root, *q.tones[inversion]) if 0 <= inversion < len(q.tones) else None
    )
    symbol = _pitch_name(root) + q.symbol
    if bass is not None and inversion:
        symbol += "/" + _pitch_name(bass)
    roman = None if key is None else _roman_label(root, q, inversion, applied, key)
    return symbol, roman, (_pitch_name(bass) if bass else None)


def chord_props(chord: dict[str, Any], key: dict[str, Any] | None) -> dict[str, Any]:
    """Derived, JSON-friendly properties of a HARMONY component under the key
    in force: ``root``, ``quality``, ``inversion``, ``applied_to`` (as stored),
    ``symbol``, ``roman`` (None without a key, except It+6/Fr+6/Ger+6/N6),
    ``key`` (the key in force, ``"C"``/``"c"``, or None) and ``bass``."""
    step, alter, quality, inversion, applied = _chord_fields(chord)
    symbol, roman, bass = _labels(
        step,
        alter,
        quality,
        inversion,
        applied,
        None if key is None else _key_fields(key),
    )
    return {
        "root": _pitch_name((step, alter)),
        "quality": quality,
        "inversion": inversion,
        "applied_to": _int(chord.get("applied_to")),
        "symbol": symbol,
        "roman": roman,
        "key": None if key is None else key_props(key)["key"],
        "bass": bass,
    }


def key_props(mode: dict[str, Any]) -> dict[str, Any]:
    """``{"tonic": "Eb", "mode": "major", "key": "Eb"}`` for a MODE component;
    ``key`` is lower case for minor (``"eb"``)."""
    step, alter, typ = _key_fields(mode)
    tonic = _pitch_name((step, alter))
    return {
        "tonic": tonic,
        "mode": typ,
        "key": tonic if typ == "major" else tonic.lower(),
    }
