import pytest

from tilia_core.tla import (
    BeatUnit,
    Component,
    Document,
    FileChanged,
    Measure,
    Score,
    Timeline,
)
from tilia_core.tla.model import (
    component_kind_from_file,
    component_kind_to_file,
    timeline_kind_from_file,
    timeline_kind_to_file,
)

TIMELINE_KINDS = [
    ("Slider", "slider"),
    ("Hierarchy", "hierarchy"),
    ("Marker", "marker"),
    ("Beat", "beat"),
    ("Harmony", "harmony"),
    ("Range", "range"),
    ("Score", "score"),
    ("Pdf", "pdf"),
    ("AudioWave", "audiowave"),
]

COMPONENT_KINDS = [
    ("HIERARCHY", "hierarchy"),
    ("MARKER", "marker"),
    ("RANGE", "range"),
    ("HARMONY", "harmony"),
    ("MODE", "mode"),
    ("BEAT", "beat"),
    ("PDF_MARKER", "pdf_marker"),
    ("NOTE", "note"),
    ("STAFF", "staff"),
    ("CLEF", "clef"),
    ("KEY_SIGNATURE", "key_signature"),
    ("TIME_SIGNATURE", "time_signature"),
    ("BAR_LINE", "bar_line"),
    ("SCORE_ANNOTATION", "score_annotation"),
]


@pytest.mark.parametrize("in_file, in_api", TIMELINE_KINDS)
def test_timeline_kinds_both_ways(in_file, in_api):
    assert timeline_kind_from_file(in_file) == in_api
    assert timeline_kind_to_file(in_api) == in_file


@pytest.mark.parametrize("in_file, in_api", COMPONENT_KINDS)
def test_component_kinds_both_ways(in_file, in_api):
    assert component_kind_from_file(in_file) == in_api
    assert component_kind_to_file(in_api) == in_file


def test_timeline_kinds_are_read_in_any_letter_case():
    # TiLiA 0.7 reads them so, and its own migration writes "Audiowave".
    assert timeline_kind_from_file("Audiowave") == "audiowave"
    assert timeline_kind_from_file("HIERARCHY") == "hierarchy"


def test_unknown_kinds_keep_their_names():
    assert timeline_kind_from_file("Lyrics") == "Lyrics"
    assert timeline_kind_to_file("Lyrics") == "Lyrics"
    assert component_kind_from_file("CHORD_SYMBOL") == "CHORD_SYMBOL"
    assert component_kind_to_file("CHORD_SYMBOL") == "CHORD_SYMBOL"


def test_component_kinds_are_read_exactly():
    # As TiLiA 0.7 reads them: "Hierarchy" isn't a component kind.
    assert component_kind_from_file("Hierarchy") == "Hierarchy"


def score(lines):
    return Score(id="s", format="mei", lines=lines)


@pytest.mark.parametrize(
    "lines, text",
    [
        (["<mei>", "</mei>", ""], "<mei>\n</mei>\n"),
        (["<mei>", "</mei>"], "<mei>\n</mei>"),
        ([""], ""),
    ],
)
def test_score_text_joins_its_lines(lines, text):
    assert score(lines).text == text


@pytest.mark.parametrize(
    "text, lines",
    [
        ("<mei>\r\n</mei>\r\n", ["<mei>", "</mei>", ""]),
        ("<mei>\n</mei>", ["<mei>", "</mei>"]),
        ("a\rb", ["a\rb"]),
        ('\t"x" \\ ü\n', ['\t"x" \\ ü', ""]),
        ("", [""]),
    ],
)
def test_setting_score_text_splits_it(text, lines):
    s = score([])
    s.text = text
    assert s.lines == lines


def test_score_defaults():
    s = score(["x"])
    assert (s.source, s.license, s.extra) == (None, None, {})


def test_an_empty_score_has_one_form():
    # Setting the text it has changes nothing, as the writer will see it.
    s = Score(id="s", format="mei")
    assert s.lines == [""]
    s.text = s.text
    assert s.lines == [""]


def test_measure_defaults():
    m = Measure(
        id="b1",
        number=1,
        label="1",
        beats=["b1", "b2"],
        beat_unit=BeatUnit(denominator=4, units="1"),
        source="tapped",
    )
    assert m.beat_units == []
    assert m.force_display is False
    assert m.next is None
    assert m.metadata == {}


def test_beat_unit_is_not_assumed_by_default():
    assert BeatUnit(denominator=8, units="3").assumed is False


def test_document_defaults():
    doc = Document(document_id="d", format_version="1.0.0-draft.1")
    assert doc.time_unit == "seconds"
    assert (doc.media_path, doc.media_length) == ("", None)
    assert (doc.metadata, doc.timelines, doc.scores, doc.extra) == ({}, {}, {}, {})
    assert doc.app_name == "TiLiA"
    assert doc.warnings == []
    assert doc.origin is None


def test_defaults_are_not_shared():
    a = Document(document_id="a", format_version="1.0.0-draft.1")
    b = Document(document_id="b", format_version="1.0.0-draft.1")
    a.metadata["title"] = "A"
    assert b.metadata == {}


def test_timeline_and_component_defaults():
    tl = Timeline(id="t", kind="hierarchy", ordinal=1)
    assert tl.name == ""
    assert (tl.metadata, tl.attrs, tl.components, tl.extra) == ({}, {}, {}, {})
    assert tl.measures is None
    assert tl.raw is None
    c = Component(id="c", kind="hierarchy")
    assert (c.attrs, c.metadata, c.extra) == ({}, {}, {})


def test_file_changed():
    from pathlib import Path

    error = FileChanged(Path("corpus") / "piece.tla", expected="ab", found=None)
    assert (error.path, error.expected, error.found) == (
        Path("corpus") / "piece.tla",
        "ab",
        None,
    )
    assert "piece.tla" in str(error)


@pytest.mark.parametrize(
    "expected, found, message",
    [
        ("ab", "cd", "piece.tla has changed since it was read"),
        ("ab", None, "piece.tla was removed or became unreadable after it was read"),
        (None, "cd", "piece.tla already exists"),
        (None, None, "piece.tla already exists"),
    ],
)
def test_file_changed_says_what_happened(expected, found, message):
    from pathlib import Path

    error = FileChanged(Path("corpus") / "piece.tla", expected, found)
    assert str(error) == message


def test_file_changed_given_a_path_as_text():
    from pathlib import Path

    error = FileChanged("corpus/piece.tla", expected="ab", found="cd")
    assert error.path == Path("corpus") / "piece.tla"
    assert "piece.tla" in str(error)
