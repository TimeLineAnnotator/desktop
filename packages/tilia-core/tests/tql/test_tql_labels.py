from tilia_core.labels import WholeLabel, fold, nfc


def test_fold_full_case_folding():
    assert fold("STRASSE") == fold("Straße")
    assert fold("ΚΟΣΜΟΣ") == fold("κοσμος")


def test_fold_and_nfc_normalise():
    composed = "Sätze"
    decomposed = "Sätze"
    assert fold(composed) == fold(decomposed)
    assert nfc(decomposed) == composed


def test_fold_is_a_canonical_caseless_match():
    # ᾴ composed (U+1FB4) and as alpha + U+0345 + U+0301, the marks typed in
    # the other order. They are canonically equivalent, but fold equal only
    # when the text is decomposed before case folding (NFD(casefold(NFD(s)))):
    # casefold turns U+0345 into iota, and the marks reorder under NFD.
    composed = "ᾴ"
    reordered = "ᾴ"
    assert fold(composed) == fold(reordered)


def test_fold_returns_nfc():
    # Folded strings reach results and CSV, so they must be composed.
    assert fold("Sätze") == "sätze"
    assert fold("Sätze") == "sätze"
    assert fold("ΚΟΣΜΟΣ") == "κοσμοσ"


def test_whole_label_categories():
    assert WholeLabel().categories(" Verse/Chorus ") == ("verse/chorus",)
    assert WholeLabel().categories("") == ()
    assert WholeLabel().categories("  \t ") == ()


def test_whole_label_group():
    assert WholeLabel().group("x") is None


def test_whole_label_dot_marks_no_subtype():
    # With no grammar a dot is part of the label: "I. Allegro" is one
    # category, and no subtype of "i".
    assert WholeLabel().categories("I. Allegro") == ("i. allegro",)
    assert WholeLabel().supertype("i. allegro") is None
    assert WholeLabel().supertype("bridge.modern") is None
