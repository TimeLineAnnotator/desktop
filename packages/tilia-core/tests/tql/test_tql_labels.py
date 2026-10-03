from tilia_core.labels import WholeLabel, fold, nfc


def test_fold_full_case_folding():
    assert fold("STRASSE") == fold("Straße")
    assert fold("ΚΟΣΜΟΣ") == fold("κοσμος")


def test_fold_and_nfc_normalise():
    composed = "Sätze"
    decomposed = "Sätze"
    assert fold(composed) == fold(decomposed)
    assert nfc(decomposed) == composed


def test_whole_label_categories():
    assert WholeLabel().categories(" Verse/Chorus ") == ("verse/chorus",)
    assert WholeLabel().categories("") == ()
    assert WholeLabel().categories("  \t ") == ()


def test_whole_label_group():
    assert WholeLabel().group("x") is None
