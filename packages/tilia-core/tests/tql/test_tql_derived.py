import examples
import pytest
from grammars import DeClercq

from tilia_core import derived
from tilia_core.labels import WholeLabel

FIXTURES = examples.load()["fixtures"]


def test_hierarchy_structure_of_exposition():
    units = [
        (f"u{n}", level, start, end)
        for n, (_, level, start, end) in enumerate(
            FIXTURES["exposition"]["timelines"][0]["units"]
        )
    ]
    structure = derived.hierarchy_structure(units)
    assert structure["u0"] == (None, 1)  # exposition
    assert structure["u1"] == ("u0", 2)  # MT
    assert structure["u5"] == ("u1", 3)  # continuation at 4, in MT
    assert structure["u7"] == ("u3", 3)  # continuation at 14, in ST
    assert structure["u4"] == ("u1", 3)  # presentation at 0


def test_hierarchy_structure_prefers_the_smallest_parent():
    units = [("a", 3, 0, 10), ("b", 2, 0, 10), ("c", 1, 0, 5), ("d", 2, 0, 20)]
    structure = derived.hierarchy_structure(units)
    assert structure["c"] == ("b", 3)
    assert structure["b"] == ("a", 2)
    assert structure["d"] == (None, 1)


def test_implied_spans():
    assert derived.implied_spans([0, 1, 18], 24) == [1, 18, 24]
    assert derived.implied_spans([30], 24) == [30]
    assert derived.implied_spans([], 24) == []


def test_key_in_force():
    assert derived.key_in_force([0, 3, 8, 9, 20], [1, 8, 16]) == [None, 0, 1, 1, 2]
    assert derived.key_in_force([1.0], [1.0000005]) == [0]
    assert derived.key_in_force([1.0], []) == [None]


def harmony_rows():
    tl = FIXTURES["harmony"]["timelines"][0]
    return tl["keys"], tl["chords"]


def test_chord_spans_and_keys_of_harmony():
    keys, chords = harmony_rows()
    ends = derived.implied_spans([c[0] for c in chords], 24)
    assert dict(zip([c[0] for c in chords], ends, strict=True))[18] == 24
    in_force = derived.key_in_force([c[0] for c in chords], [k[0] for k in keys])
    by_time = dict(zip([c[0] for c in chords], in_force, strict=True))
    assert by_time[7] == 0
    assert by_time[9] == 1
    assert by_time[17] == 2


def test_chord_fields():
    g7 = {"step": 4, "accidental": 0, "quality": "dominant-seventh", "inversion": 0}
    c_minor = {"step": 0, "accidental": 0, "type": "minor"}
    props = derived.chord_fields(g7, c_minor)
    assert props["label"] == "V7"
    assert props["key"] == "c"
    props = derived.chord_fields({**g7, "inversion": 1}, derived.C_MAJOR)
    assert props["label"] == "V65"
    assert props["key"] == "C"


def test_chord_fields_without_a_key_reads_in_c_major():
    g7 = {"step": 4, "accidental": 0, "quality": "dominant-seventh", "inversion": 0}
    props = derived.chord_fields(g7, None)
    assert props["key"] is None
    assert props["roman"] == "V7"


def test_chord_label_prefers_custom_text():
    chord = {"step": 4, "accidental": 0, "quality": "major", "custom_text": "dom"}
    assert derived.chord_fields(chord, derived.C_MAJOR)["label"] == "dom"


def test_key_fields_labels():
    keys, _ = harmony_rows()
    labels = []
    for _, tonic, kind in keys:
        step = "CDEFGAB".index(tonic[0])
        accidental = -1 if tonic.endswith("b") else 0
        mode = {"step": step, "accidental": accidental, "type": kind}
        labels.append(derived.key_fields(mode)["label"])
    assert labels == ["C", "c", "Eb"]


@pytest.mark.parametrize(
    "label, expected",
    [
        ("chorus?", ("chorus",)),
        ("B/bridge/chorus", ("b", "bridge", "chorus")),
        ("intro[over_chorus]", ("intro",)),
        ("blues.12_bar[modified]", ("blues.12_bar",)),
        ("Verse 1", ("verse",)),
        ("verse/Verse 2", ("verse",)),
        ("chorus??", ("chorus",)),
        ("Straße", ("strasse",)),
        ("", ()),
    ],
)
def test_categories_de_clercq(label, expected):
    assert derived.categories(label, DeClercq()) == expected


def test_categories_whole_label():
    assert derived.categories("Verse/Chorus", WholeLabel()) == ("verse/chorus",)
    assert derived.categories("", WholeLabel()) == ()


def test_color():
    assert derived.color("pink") == "#ffc0cb"
    assert derived.color("#FFC0CB") == "#ffc0cb"
    assert derived.color("#fcb") == "#ffccbb"
    assert derived.color(None) is None


def test_field_name():
    assert derived.field_name("Song Title") == "song_title"
    assert derived.field_name("a  \t b") == "a_b"
