import pytest

from tilia_core.harmony import (
    _QUAL,
    _SPECIAL,
    QUALITIES,
    HarmonyError,
    _roman_suffix,
    chord_matches,
    chord_props,
    is_chord_symbol,
    key_matches,
    key_props,
    parse_chord,
    parse_key,
)


def key(text):
    k = parse_key(text)
    return {
        "kind": "MODE",
        "step": k.tonic[0],
        "accidental": k.tonic[1],
        "type": k.mode,
    }


def chord(name, quality="major", inversion=0, applied_to=0):
    step, alter = parse_chord(name).root
    return {
        "kind": "HARMONY",
        "step": step,
        "accidental": alter,
        "quality": quality,
        "inversion": inversion,
        "applied_to": applied_to,
    }


def yes(lit, ch, k):
    assert chord_matches(parse_chord(lit), ch, k), (lit, ch, k)


def no(lit, ch, k):
    assert not chord_matches(parse_chord(lit), ch, k), (lit, ch, k)


def bad(lit):
    with pytest.raises(HarmonyError):
        parse_chord(lit)


C, c, G, g, D, Bb = key("C"), key("c"), key("G"), key("g"), key("D"), key("Bb")


def real(fields, inversion=0, applied_to=0):
    name, quality = fields.split(":")
    return chord(name, quality, inversion, applied_to)


g7 = chord("G", "dominant-seventh")
g7b = chord("G", "dominant-seventh", 1)
it6 = chord("Ab", "Italian")
d_v = chord("D", "major", 0, 4)


# symbol or numeral: the first letter decides
@pytest.mark.parametrize(
    "text", ["G7", "F#m7b5", "C/E", "Bbmaj7", "Ebdim7", "A", " G7 "]
)
def test_chord_symbols(text):
    assert is_chord_symbol(text) and parse_chord(text).kind == "symbol", text


@pytest.mark.parametrize(
    "text",
    ["V7", "bVI", "vii°7", "V/V", "iiø7", "I", "#iv°7", "It6", "Fr6", "Ger65", "N6"],
)
def test_roman_numerals(text):
    assert not is_chord_symbol(text) and parse_chord(text).kind == "roman", text


def test_empty_and_lower_case_are_not_chord_symbols():
    assert not is_chord_symbol("") and not is_chord_symbol("c")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "  ",
        "H7",
        "c7",
        "g",
        "X",
        "C/D",
        "Cm/E",
        "C9/D",
        "G7/C",
        "C/",
        "V/V/V",
        "IM",
        "Vb9",
        "viiø6",
        "vo13",
        "Vq",
        "Iv",
        "IIII",
        "V/V7",
        "C#b",
        "Cxyz",
        "C6/9",
    ],
)
def test_unreadable_chord_literals(text):
    bad(text)


# figures and slash basses fix the inversion; bare numerals and symbols don't
@pytest.mark.parametrize(
    "lit, quality, inversion",
    [
        ("V7", "dominant-seventh", None),
        ("V65", "dominant-seventh", 1),
        ("V43", "dominant-seventh", 2),
        ("V42", "dominant-seventh", 3),
        ("V2", "dominant-seventh", 3),
        ("V6/5", "dominant-seventh", 1),
        ("I", "major", None),
        ("I6", "major", 1),
        ("I64", "major", 2),
        ("I53", "major", 0),
        ("V753", "dominant-seventh", 0),
        ("G7", "dominant-seventh", None),
        ("G7/B", "dominant-seventh", 1),
        ("G7/D", "dominant-seventh", 2),
        ("G7/F", "dominant-seventh", 3),
        ("C/E", "major", 1),
        ("C/G", "major", 2),
        ("C/C", "major", 0),
        ("Cm/Eb", "minor", 1),
        ("Bbmaj7/A", "major-seventh", 3),
        ("Csus4/F", "suspended-fourth", 1),
        ("C6/A", "major-sixth", 3),
    ],
)
def test_quality_and_inversion(lit, quality, inversion):
    s = parse_chord(lit)
    assert (s.quality, s.inversion) == (quality, inversion), (lit, s)


@pytest.mark.parametrize(
    "lit, canonical",
    [
        ("V6/5/V", "V65/V"),
        ("viio7/v", "vii°7/v"),
        ("C-7", "Cm7"),
        ("Bbmaj7/A", "Bbmaj7/A"),
        ("C♯m7♭5", "C#m7b5"),
        ("VII°", "vii°"),
        ("ii%7", "iiø7"),
        ("I53", "I53"),
        ("-VI", "bVI"),
        ("Gr6", "Ger+6"),
    ],
)
def test_canonical_spelling(lit, canonical):
    assert parse_chord(lit).canonical == canonical, (lit, parse_chord(lit).canonical)


def test_needs_key():
    assert parse_chord("V7").needs_key and not parse_chord("G7").needs_key
    assert not parse_chord("It6").needs_key and issubclass(HarmonyError, ValueError)


# every TiLiA quality: the canonical spellings parse back to it, and a
# common alternative spelling reads the same
@pytest.mark.parametrize("name", QUALITIES)
def test_every_quality_parses_back(name):
    if name in _SPECIAL:
        assert parse_chord(_SPECIAL[name]).quality == name
        return
    q = _QUAL[name]
    assert parse_chord("C" + q.symbol).quality == name, name
    numeral = "i" if q.lower else "I"
    assert parse_chord(numeral + _roman_suffix(q, None)).quality == name, name


@pytest.mark.parametrize(
    "lit, quality",
    [
        ("Cmaj7", "major-seventh"),
        ("CM7", "major-seventh"),
        ("CΔ", "major-seventh"),
        ("CΔ7", "major-seventh"),
        ("Cm", "minor"),
        ("Cmin", "minor"),
        ("C-", "minor"),
        ("C-7", "minor-seventh"),
        ("Cmin7", "minor-seventh"),
        ("C°", "diminished"),
        ("Co", "diminished"),
        ("C°7", "diminished-seventh"),
        ("Cdim7", "diminished-seventh"),
        ("Cø", "half-diminished-seventh"),
        ("C%7", "half-diminished-seventh"),
        ("C-7b5", "half-diminished-seventh"),
        ("Cm7(b5)", "half-diminished-seventh"),
        ("C+", "augmented"),
        ("Caug", "augmented"),
        ("C7#5", "augmented-seventh"),
        ("Cm(maj7)", "minor-major-seventh"),
        ("CmΔ7", "minor-major-seventh"),
        ("C-maj7", "minor-major-seventh"),
        ("C+maj7", "augmented-major-seventh"),
        ("CMaj7", "major-seventh"),
        ("C7(b5)", "seventh-flat-five"),
        ("C6", "major-sixth"),
        ("Cm6", "minor-sixth"),
        ("CΔ9", "major-ninth"),
        ("C9", "dominant-ninth"),
        ("Cm9", "minor-ninth"),
        ("C9#5", "augmented-dominant-ninth"),
        ("Cø9", "half-diminished-ninth"),
        ("Cdimb9", "diminished-minor-ninth"),
        ("C13", "dominant-13th"),
        ("Cm11", "minor-11th"),
        ("Csus", "suspended-fourth"),
        ("C7sus", "suspended-fourth-seventh"),
        ("C5", "power"),
        ("Cpedal", "pedal"),
        ("C♯m7♭5", "half-diminished-seventh"),
        ("Ab", "major"),
        ("Cb", "major"),
        ("V", "major"),
        ("v", "minor"),
        ("V7", "dominant-seventh"),
        ("v7", "minor-seventh"),
        ("IM7", "major-seventh"),
        ("Imaj7", "major-seventh"),
        ("IΔ7", "major-seventh"),
        ("iM7", "minor-major-seventh"),
        ("iiø7", "half-diminished-seventh"),
        ("ii%7", "half-diminished-seventh"),
        ("viiø", "half-diminished-seventh"),
        ("ii7b5", "half-diminished-seventh"),
        ("V7b5", "seventh-flat-five"),
        ("vii°", "diminished"),
        ("viio", "diminished"),
        ("VII°", "diminished"),
        ("vii°7", "diminished-seventh"),
        ("viidim7", "diminished-seventh"),
        ("III+", "augmented"),
        ("IIIaug", "augmented"),
        ("III+7", "augmented-seventh"),
        ("III+M7", "augmented-major-seventh"),
        ("Iadd6", "major-sixth"),
        ("V9", "dominant-ninth"),
        ("IM9", "major-ninth"),
        ("ii9", "minor-ninth"),
        ("viiøb9", "half-diminished-minor-ninth"),
        ("vii°b9", "diminished-minor-ninth"),
        ("V11", "dominant-11th"),
        ("V13", "dominant-13th"),
        ("Vsus4", "suspended-fourth"),
        ("V7sus4", "suspended-fourth-seventh"),
        ("I5", "power"),
        ("It+6", "Italian"),
        ("It6", "Italian"),
        ("Fr43", "French"),
        ("Fr4/3", "French"),
        ("Ger65", "German"),
        ("Gr+6", "German"),
        ("N", "Neapolitan"),
    ],
)
def test_alternative_spellings(lit, quality):
    assert parse_chord(lit).quality == quality, (lit, parse_chord(lit).quality)


# chord symbols: absolute root and quality, exact spelling, no key needed
@pytest.mark.parametrize("k", [C, c, None], ids=["C", "c", "no-key"])
def test_symbol_matches_in_any_key(k):
    yes("G7", g7b, k)
    yes("G7/B", g7b, k)


@pytest.mark.parametrize(
    "lit, ch",
    [
        ("G7/D", g7b),
        ("G", g7b),
        ("Gmaj7", g7b),
        ("Gb7", g7b),
        ("Gb", chord("F#")),
        ("F#", chord("Gb")),
        ("C/E", chord("C", "major", 0)),
    ],
)
def test_symbol_does_not_match(lit, ch):
    no(lit, ch, None)


@pytest.mark.parametrize(
    "lit, ch",
    [
        ("F#", chord("F#")),
        ("F#m7b5", chord("F#", "half-diminished-seventh")),
        ("Bbmaj7", chord("Bb", "major-seventh", 3)),
        ("C/E", chord("C", "major", 1)),
    ],
)
def test_symbol_matches(lit, ch):
    yes(lit, ch, None)


# Roman numerals: through the key, strict quality, case matters
@pytest.mark.parametrize(
    "lit, ch, k",
    [
        ("V7", g7, C),
        ("I7", g7, G),  # I7 = dominant 7th on I
        ("V", chord("G"), C),
        ("I", chord("C"), C),
        ("i", chord("C", "minor"), C),
        ("IV7", chord("F", "dominant-seventh"), C),
        ("IVM7", chord("F", "major-seventh"), C),
        ("IVmaj7", chord("F", "major-seventh"), C),
        ("ii7", chord("D", "minor-seventh"), C),
        ("viiø7", chord("B", "half-diminished-seventh"), C),
        ("vii°7", chord("B", "diminished-seventh"), C),
    ],
)
def test_roman_matches_through_key(lit, ch, k):
    yes(lit, ch, k)


@pytest.mark.parametrize(
    "lit, ch, k",
    [
        ("V", g7, C),
        ("v7", g7, C),
        ("V7", g7, None),  # no key, no Roman numeral
        ("V7", g7, G),
        ("IM7", g7, G),
        ("V7", chord("G"), C),
        ("i", chord("C"), C),
        ("I", chord("C", "minor"), C),
        ("IV7", chord("F", "major-seventh"), C),
    ],
)
def test_roman_does_not_match(lit, ch, k):
    no(lit, ch, k)


# inversions
@pytest.mark.parametrize(
    "lit, ch, k",
    [
        ("V65", g7b, C),
        ("V7", g7b, C),
        ("I6", chord("C", "major", 1), C),
        ("I64", chord("C", "major", 2), C),
        ("V42", chord("G", "dominant-seventh", 3), C),
        ("IVM65", chord("F", "major-seventh", 1), C),
    ],
)
def test_inversion_matches(lit, ch, k):
    yes(lit, ch, k)


@pytest.mark.parametrize(
    "lit, ch, k",
    [
        ("V43", g7b, C),
        ("V2", g7b, C),
        ("I64", chord("C", "major", 1), C),
    ],
)
def test_inversion_does_not_match(lit, ch, k):
    no(lit, ch, k)


# chromatic numerals and enharmonics: letter steps decide the degree
@pytest.mark.parametrize(
    "lit, ch, k",
    [
        ("bVI", chord("Ab"), C),
        ("bII6", chord("Db", "major", 1), C),
        ("iii", chord("F#", "minor"), D),
        ("III", chord("F#"), D),
        ("bIII", chord("F"), D),
        ("bIV", chord("Gb"), D),
        ("#iv°7", chord("F#", "diminished-seventh"), C),
    ],
)
def test_chromatic_matches(lit, ch, k):
    yes(lit, ch, k)


@pytest.mark.parametrize(
    "lit, ch, k",
    [
        ("VI", chord("Ab"), C),
        ("III", chord("F#", "minor"), D),
        ("III", chord("Gb"), D),
    ],
)
def test_chromatic_does_not_match(lit, ch, k):
    no(lit, ch, k)


# minor keys: ^6 and ^7 by quality, courtesy accidentals accepted
@pytest.mark.parametrize(
    "lit, name, quality",
    [
        ("i", "C", "minor"),
        ("ii°", "D", "diminished"),
        ("III", "Eb", "major"),
        ("iv", "F", "minor"),
        ("IV", "F", "major"),
        ("v", "G", "minor"),
        ("V", "G", "major"),
        ("V7", "G", "dominant-seventh"),
        ("VI", "Ab", "major"),
        ("bVI", "Ab", "major"),
        ("vi", "A", "minor"),
        ("#vi", "A", "minor"),
        ("#VI", "A", "major"),
        ("bvi", "Ab", "minor"),
        ("vi°", "A", "diminished"),
        ("VII", "Bb", "major"),
        ("bVII", "Bb", "major"),
        ("VII7", "Bb", "dominant-seventh"),
        ("vii°", "B", "diminished"),
        ("#vii°", "B", "diminished"),
        ("vii°7", "B", "diminished-seventh"),
        ("viiø7", "B", "half-diminished-seventh"),
        ("vii", "B", "minor"),
        ("bvii", "Bb", "minor"),
        ("#VII", "B", "major"),
        ("bII", "Db", "major"),
        ("N6", "Db", "Neapolitan"),
    ],
)
def test_minor_key_degrees(lit, name, quality):
    yes(lit, chord(name, quality), c)


@pytest.mark.parametrize(
    "lit, ch",
    [
        ("VI", chord("A")),
        ("vi", chord("Ab", "minor")),
        ("VII", chord("B")),
        ("vii°", chord("Bb", "diminished")),
        ("vii°", chord("B#", "diminished")),
    ],
)
def test_minor_key_degrees_do_not_match(lit, ch):
    no(lit, ch, c)


# applied chords: the target's key, and only chords stored as applied
@pytest.mark.parametrize(
    "lit, ch, k",
    [
        ("V/V", d_v, C),
        ("V/v", d_v, C),
        ("II", chord("D"), C),
        ("V7/V", chord("D", "dominant-seventh", 0, 4), C),
        ("V65/V", chord("D", "dominant-seventh", 1, 4), C),
        ("vii°7/V", chord("F#", "diminished-seventh", 0, 4), C),
        ("V7/IV", chord("C", "dominant-seventh", 0, 3), C),
        ("V7/ii", chord("A", "dominant-seventh", 0, 1), C),
        ("V7/bVI", chord("Eb", "dominant-seventh", 0, 5), C),
        ("V7/vi", chord("E", "dominant-seventh", 0, 5), C),
        ("V7/VI", chord("E", "dominant-seventh", 0, 5), C),
        ("V/vi", chord("E", "major", 0, 5), c),  # a minor: raised ^6 in c
        ("V/VI", chord("Eb", "major", 0, 5), c),
        ("VI/v", chord("Eb", "major", 0, 4), C),  # the target's mode counts
        ("V/I", chord("G"), C),
    ],
)
def test_applied_matches(lit, ch, k):
    yes(lit, ch, k)


@pytest.mark.parametrize(
    "lit, ch, k",
    [
        ("II", d_v, C),
        ("V", d_v, C),
        ("V/V", chord("D"), C),
        ("V65/V", chord("D", "dominant-seventh", 2, 4), C),
        ("V7/VI", chord("Eb", "dominant-seventh", 0, 5), C),
        ("V/VI", chord("E", "major", 0, 5), c),
        ("VI/V", chord("Eb", "major", 0, 4), C),
        ("V/V", d_v, None),
    ],
)
def test_applied_does_not_match(lit, ch, k):
    no(lit, ch, k)


# the root-less names: quality only, key or no key
@pytest.mark.parametrize("k", [C, c, None], ids=["C", "c", "no-key"])
def test_rootless_names_ignore_key(k):
    yes("It6", it6, k)
    yes("It+6", it6, k)


def test_rootless_names_are_strict_about_quality():
    no("Fr6", it6, C)
    no("bVI", it6, C)
    yes("Ger65", chord("C", "German", 0, 4), None)


# keys: case = mode
@pytest.mark.parametrize(
    "text, tonic, mode, canonical",
    [
        ("c", (0, 0), "minor", "c"),
        ("C", (0, 0), "major", "C"),
        ("Eb", (2, -1), "major", "Eb"),
        ("eb", (2, -1), "minor", "eb"),
        ("f#", (3, 1), "minor", "f#"),
        ("F♯", (3, 1), "major", "F#"),
        ("bb", (6, -1), "minor", "bb"),
        ("B", (6, 0), "major", "B"),
        ("C minor", (0, 0), "minor", "c"),
        ("c major", (0, 0), "major", "C"),
        ("Cm", (0, 0), "minor", "c"),
        ("Bbmin", (6, -1), "minor", "bb"),
    ],
)
def test_parse_key(text, tonic, mode, canonical):
    k = parse_key(text)
    assert (k.tonic, k.mode, k.canonical) == (tonic, mode, canonical), (text, k)


@pytest.mark.parametrize("text", ["", "H", "C#b", "c moll", "Cx#", "7", "major"])
def test_unreadable_keys(text):
    with pytest.raises(HarmonyError):
        parse_key(text)


def test_key_matches():
    assert key_matches(parse_key("c"), c) and not key_matches(parse_key("C"), c)
    assert key_matches(parse_key("Bb"), Bb) and not key_matches(parse_key("A#"), Bb)


def test_key_props():
    assert key_props(key("eb")) == {"tonic": "Eb", "mode": "minor", "key": "eb"}
    assert key_props(Bb) == {"tonic": "Bb", "mode": "major", "key": "Bb"}


# derived labels
def test_chord_props():
    assert chord_props(g7b, C) == {
        "root": "G",
        "quality": "dominant-seventh",
        "inversion": 1,
        "applied_to": 0,
        "symbol": "G7/B",
        "roman": "V65",
        "key": "C",
        "bass": "B",
    }


def test_chord_props_without_key():
    assert chord_props(g7b, None)["roman"] is None
    assert chord_props(g7b, None)["key"] is None
    assert chord_props(it6, None)["roman"] == "It+6"


@pytest.mark.parametrize(
    "ch, k, symbol, roman",
    [
        (chord("B", "diminished"), c, "Bdim", "vii°"),
        (chord("Bb"), c, "Bb", "VII"),
        (chord("Ab", "major", 1), c, "Ab/C", "VI6"),
        (chord("A"), c, "A", "#VI"),
        (chord("Ab", "minor"), c, "Abm", "bvi"),
        (chord("Gb"), D, "Gb", "bIV"),
        (chord("F#", "minor", 2), D, "F#m/C#", "iii64"),
        (chord("Eb", "dominant-seventh", 0, 5), C, "Eb7", "V7/bVI"),
        (chord("F#", "diminished-seventh", 3, 4), C, "F#dim7/Eb", "vii°2/V"),
        (chord("F", "major-seventh", 1), C, "Fmaj7/A", "IVM65"),
        (chord("C", "augmented", 1), C, "Caug/E", "I+6"),
        (chord("E", "German"), C, "Ger+6", "Ger+6"),
    ],
)
def test_derived_labels(ch, k, symbol, roman):
    p = chord_props(ch, k)
    assert (p["symbol"], p["roman"]) == (symbol, roman), (ch, k, p)


# every derived label reads back to a literal that matches its chord
@pytest.mark.parametrize("k", [key(t) for t in ("C", "c", "f#", "Eb", "bb", "A")])
@pytest.mark.parametrize(
    "name",
    [
        "major",
        "minor",
        "diminished",
        "augmented",
        "dominant-seventh",
        "diminished-seventh",
        "half-diminished-seventh",
        "major-seventh",
        "minor-major-seventh",
        "suspended-fourth",
        "dominant-ninth",
        "French",
    ],
)
def test_derived_labels_read_back(k, name):
    roots = [(s, a) for s in range(7) for a in (-1, 0, 1)]
    seventh = name in _QUAL and _QUAL[name].family == "seventh"
    for step, alter in roots:
        for inversion in (0, 1, 3) if seventh else (0, 1):
            for applied in range(7):
                ch = {
                    "step": step,
                    "accidental": alter,
                    "quality": name,
                    "inversion": inversion,
                    "applied_to": applied,
                }
                p = chord_props(ch, k)
                for label in (p["symbol"], p["roman"]):
                    spec = parse_chord(label)
                    assert chord_matches(spec, ch, k), (label, ch, k)
                    assert parse_chord(spec.canonical).canonical == spec.canonical


# real components stored by TiLiA
@pytest.mark.parametrize(
    "ch, k, symbol, roman",
    [
        (real("G:major", 1), G, "G/B", "I6"),
        (real("A:major", 0, 4), G, "A", "V/V"),
        (real("D:dominant-seventh"), G, "D7", "V7"),
        (real("G:major", 2), G, "G/D", "I64"),
        (real("C#:diminished", 0, 4), G, "C#dim", "vii°/V"),
        (real("A:dominant-seventh", 3, 4), g, "A7/G", "V2/V"),
        (real("D:major", 1), g, "D/F#", "V6"),
        (real("C:dominant-seventh", 3, 5), g, "C7/Bb", "VI2/VI"),
        (real("C:major", 1), g, "C/E", "IV6"),
        (real("F:dominant-seventh", 3, 2), g, "F7/Eb", "V2/III"),
        (real("Bb:major"), g, "Bb", "III"),
        (real("Eb:major", 0, 2), g, "Eb", "IV/III"),
        (real("D:major"), Bb, "D", "III"),
        (real("C#:diminished-seventh", 0, 2), Bb, "C#dim7", "vii°7/iii"),
        (real("A:dominant-seventh"), key("d"), "A7", "V7"),
    ],
)
def test_real_components(ch, k, symbol, roman):
    p = chord_props(ch, k)
    assert (p["symbol"], p["roman"]) == (symbol, roman), (ch, k, p)
    yes(roman, ch, k)
    yes(symbol, ch, k)


def test_real_components_applied_spelling():
    yes("vii°7/V", real("C#:diminished-seventh", 0, 4), g)
    no("vii°7/V", real("C##:diminished-seventh", 0, 4), g)  # C## stored
    no("vii°7/ii", real("Bb:diminished-seventh", 0, 1), Bb)  # Bb stored
