import music21

from tilia.ui.timelines.harmony.constants import (
    INT_TO_NOTE_NAME,
    INT_TO_ROMAN,
    NOTE_NAME_TO_INT,
    QUALITY_TO_ABBREVIATION,
    Accidental,
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


# Qualities whose notation is bespoke at every inversion and cannot be
# derived from chord structure.
QUALITY_TO_ROMAN_NUMERAL_SUFFIX = {
    "seventh-flat-five": ("7((b5))", None, None, None),
    "major-sixth": ("((6))", "6((4))", "64((2))", "7"),
    "minor-sixth": ("((6))", "6((4))", "64((2))", "7"),
    "suspended-second": ("52", "74", "54", None),
    "suspended-fourth": ("54", "52", "74", None),
    "suspended-fourth-seventh": ("74", "54", "52", None),
    "pedal": ("`p`e`d", None, None, None),
    "power": ("5", None, None, None),
    "Tristan": ("`t`r`i`s`t", None, None, None),
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

_TRIAD_QUALITIES = frozenset({"major", "minor", "augmented", "diminished"})

# Derived from the static table so _get_chord_size skips them correctly.
_STATIC_QUALITIES = frozenset(QUALITY_TO_ROMAN_NUMERAL_SUFFIX)


def _get_inv_prefix(quality: str) -> str:
    """Return the quality prefix prepended to the inversion figured-bass string."""
    if quality.startswith("half-diminished"):
        return "o\\"
    if quality.startswith("diminished"):
        return "o"
    # Augmented 7th chords use no prefix in inversions (only at root position).
    if quality.startswith("augmented") and "seventh" not in quality:
        return "+"
    return ""


def _get_chord_size(quality: str) -> str | None:
    """Return chord-size category for dynamic dispatch; None means use the static table."""
    if quality in _STATIC_QUALITIES:
        return None
    if quality in _TRIAD_QUALITIES:
        return "triad"
    if "seventh" in quality:
        return "seventh"
    if "ninth" in quality:
        return "ninth"
    if "11th" in quality:
        return "eleventh"
    if "13th" in quality:
        return "thirteenth"
    return None


# Qualities that carry the MusAnalysis major-7th triangle ("^^") at root position.
# The set is irregular (e.g. major-ninth omits it while major-11th includes it),
# so it must be listed explicitly.
_MAJOR_MARKER_QUALITIES = frozenset(
    {
        "major-seventh",
        "minor-major-seventh",
        "augmented-major-seventh",
        "minor-major-ninth",
        "augmented-major-ninth",
        "augmented-dominant-ninth",
        "major-11th",
        "major-13th",
        "minor-major-13th",
    }
)

# Qualities with a flat (minor) 9th at root position.
_FLAT_NINTH_QUALITIES = frozenset(
    {
        "half-diminished-minor-ninth",
        "diminished-minor-ninth",
    }
)


def _root_position_suffix(quality: str) -> str:
    """Compute the root-position suffix from the quality name."""
    if quality.startswith("half-diminished"):
        prefix = "o\\"
    elif quality.startswith("diminished"):
        prefix = "o"
    elif quality.startswith("augmented"):
        prefix = "+"
    else:
        prefix = ""

    size = _get_chord_size(quality)
    if size == "triad":
        return prefix

    number = {"seventh": "7", "ninth": "9", "eleventh": "11", "thirteenth": "13"}.get(
        size or "", ""
    )
    major_marker = "^^" if quality in _MAJOR_MARKER_QUALITIES else ""
    flat = "b" if quality in _FLAT_NINTH_QUALITIES else ""
    return prefix + major_marker + flat + number


def _fmt_mod(mod: str | None, none_str: str = "") -> str:
    return none_str if mod is None else mod.replace("-", "b")


def _figs_to_str(figures: list[tuple[int, str | None]]) -> str:
    # MusAnalysis only consumes the "s" placeholder (an accidental slot left
    # blank) inside the three-figure stack introduced by "%". Outside it there
    # is no blank slot, so an unaccidented figure must contribute nothing —
    # otherwise the "s" is rendered as a literal letter next to the numeral.
    stacked = len(figures) > 2
    prefix = "%" if stacked else ""
    accs = "".join(_fmt_mod(mod, "s" if stacked else "") for _, mod in figures)
    nums = "".join(str(n) for n, _ in figures)
    return prefix + accs + nums


def _figure_index_for_pitch(
    figures: list[tuple[int, str | None]],
    pitch: music21.pitch.Pitch | None,
    bass: music21.pitch.Pitch,
) -> int | None:
    """Return index in figures for pitch above bass; None if pitch is None or == bass."""
    if pitch is None:
        return None
    interval = music21.interval.Interval(bass, pitch)
    generic = _to_ascending_generic(interval.generic.directed)
    if generic <= 1:
        return None
    for i, (num, _) in enumerate(figures):
        if num == generic:
            return i
    return None


def _to_ascending_generic(generic: int) -> int:
    """
    Normalise a directed generic interval to an ascending value in [1, 7].

    Negative (descending) intervals are converted to their ascending diatonic
    complement: a descending 3rd becomes an ascending 6th (3 + 6 = 9).
    Values outside [1, 7] — including those produced by the complement step —
    are then folded back into [1, 7] by modular reduction.  The result of 1
    indicates the bass pitch itself (unison or octave equivalent).
    """
    if generic < 0:
        generic = 8 - (-generic - 1) % 7
    return (generic - 1) % 7 + 1


def _get_figures(
    sym: music21.harmony.ChordSymbol,
    key: music21.key.Key,
) -> list[tuple[int, str | None]]:
    """
    Compute figured bass (interval, modifier) pairs for each non-bass chord
    tone, where the modifier reflects the deviation from the diatonic pitch at
    that scale degree above the bass in the given key.
    """
    bass = sym.bass()
    key_pitches = key.pitches
    key_steps = [p.step for p in key_pitches]
    try:
        bass_idx = key_steps.index(bass.step)
    except ValueError:
        bass_idx = None

    figures: list[tuple[int, str | None]] = []
    seen: set[int] = set()
    for pitch in sym.pitches:
        if pitch.step == bass.step:
            continue
        generic = _to_ascending_generic(
            music21.interval.Interval(bass, pitch).generic.directed
        )
        if generic <= 1 or generic in seen:
            continue
        seen.add(generic)
        if bass_idx is None:
            figures.append((generic, None))
        else:
            diatonic_idx = (bass_idx + generic - 1) % 7
            diff = round(pitch.alter - key_pitches[diatonic_idx].alter)
            figures.append((generic, Accidental.get_from_int("music21", diff) or None))

    figures.sort(key=lambda x: -x[0])
    return figures


def _chord_fb(
    sym: music21.harmony.ChordSymbol,
    key: music21.key.Key,
    quality: str,
) -> str:
    """
    Universal figured bass for any chord at any inversion.
    Treats the chord as root + 3rd + 5th + extension; all intermediates (7th of
    9th chords, 7th+9th of 11th chords, etc.) are always implied and dropped
    unconditionally. Of the remaining figures, drops the diatonic 5th first; if
    the 5th is non-diatonic, drops the diatonic 3rd instead (only when the chord
    has an extension, so triads in 2nd inversion keep both 3rd and 5th).
    """
    figures = _get_figures(sym, key)
    bass = sym.bass()
    size = _get_chord_size(quality)

    # Drop intermediate extensions unconditionally (always implied by chord type).
    intermediates: list[music21.pitch.Pitch | None] = []
    if size in ("ninth", "eleventh", "thirteenth"):
        intermediates.append(sym.seventh)
    if size in ("eleventh", "thirteenth"):
        intermediates.append(sym.getChordStep(9))
    if size == "thirteenth":
        intermediates.append(sym.getChordStep(11))

    for pitch in intermediates:
        idx = _figure_index_for_pitch(figures, pitch, bass)
        if idx is not None:
            figures.pop(idx)

    # Drop 5th if diatonic; if the 5th is non-diatonic (must show it) or in the
    # bass, drop the diatonic 3rd instead — but only when the chord has an
    # extension (triads in 2nd inversion need both figures).
    fifth_idx = _figure_index_for_pitch(figures, sym.fifth, bass)
    if fifth_idx is not None and figures[fifth_idx][1] is None:
        figures.pop(fifth_idx)
    elif sym.seventh is not None:
        third_idx = _figure_index_for_pitch(figures, sym.third, bass)
        if third_idx is not None and figures[third_idx][1] is None:
            figures.pop(third_idx)

    return _figs_to_str(figures)


def _compute_quality_suffix(
    quality: str,
    note_name: str,
    inversion: int,
    key: music21.key.Key,
) -> str | None:
    size = _get_chord_size(quality)
    if size in ("triad", "seventh"):
        max_inv = 2 if size == "triad" else 3
        if inversion > max_inv:
            return None
    abbrev = QUALITY_TO_ABBREVIATION[quality]
    sym = music21.harmony.ChordSymbol(note_name + abbrev, inversion=inversion)
    return _get_inv_prefix(quality) + _chord_fb(sym, key, quality)


def _get_note_degree(key: music21.key.Key, note):
    steps = [p.step for p in key.pitches]
    return (
        steps.index(note.step) + 1
    )  # +1 is needed because music21's degrees are 1-based


def _get_roman_numeral_accidental(
    key: music21.key.Key, note_step: int, note_accidental: int
):
    tonic = INT_TO_NOTE_NAME[note_step]
    accidental_symbol = Accidental.get_from_int("music21", note_accidental)
    note = music21.note.Note(tonic + accidental_symbol)
    is_diatonic = (note.step, note.pitch.pitchClass) in (
        (p.step, p.pitchClass) for p in key.pitches
    )
    if is_diatonic:
        return 0

    degree = _get_note_degree(key, note)
    key_degree_pitch = key.pitchFromDegree(degree)
    if key_degree_pitch is None:
        return 0
    key_degree_accidental = key_degree_pitch.alter
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
    result_prefix = (
        Accidental.get_from_int("musanalysis", round(result_accidental))
        if not applied_to
        else ""
    )

    size = _get_chord_size(quality)
    if size is not None:
        if inversion > 0:
            note_name = INT_TO_NOTE_NAME[step] + Accidental.get_from_int(
                "music21", accidental
            )
            quality_suffix = _compute_quality_suffix(quality, note_name, inversion, key)
            if quality_suffix is None:
                quality_suffix = _root_position_suffix(quality)
        else:
            quality_suffix = _root_position_suffix(quality)
    else:
        suffix_table = QUALITY_TO_ROMAN_NUMERAL_SUFFIX.get(quality)
        quality_suffix = (
            suffix_table[inversion]
            if suffix_table and inversion < len(suffix_table)
            else None
        )
        if quality_suffix is None:
            quality_suffix = (suffix_table[0] if suffix_table else "") or ""

    applied_to_suffix = INT_TO_APPLIED_TO_SUFFIX[applied_to]

    if "11th" in quality:
        quality_suffix += "    "

    return result_prefix + numeral + quality_suffix + applied_to_suffix
