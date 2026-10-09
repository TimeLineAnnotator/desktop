import pytest

from tilia_core.tla import (
    BeatUnit,
    Component,
    Document,
    FileChanged,
    Measure,
    Score,
    Timeline,
    UnknownKind,
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


@pytest.mark.parametrize(
    "in_file, in_api",
    [
        ("HIERARCHY_TIMELINE", "hierarchy"),
        ("AUDIOWAVE_TIMELINE", "audiowave"),
        ("PDF_TIMELINE", "pdf"),
    ],
)
def test_timeline_kinds_with_the_suffix_older_versions_wrote(in_file, in_api):
    # TiLiA 0.7 drops "_TIMELINE" from a timeline's kind whenever it opens a
    # file, whatever the file's version.
    assert timeline_kind_from_file(in_file) == in_api


def test_an_unknown_timeline_kind_with_the_suffix_keeps_its_spelling():
    kind = timeline_kind_from_file("LYRICS_TIMELINE")
    assert kind == UnknownKind("LYRICS_TIMELINE")
    assert timeline_kind_to_file(kind) == "LYRICS_TIMELINE"


def test_an_unknown_timeline_kind_keeps_its_spelling():
    assert timeline_kind_from_file("Lyrics") == UnknownKind("Lyrics")
    assert timeline_kind_to_file(UnknownKind("Lyrics")) == "Lyrics"


def test_an_unknown_component_kind_keeps_its_spelling():
    assert component_kind_from_file("LCMA_FORM") == UnknownKind("LCMA_FORM")
    assert component_kind_to_file(UnknownKind("LCMA_FORM")) == "LCMA_FORM"


@pytest.mark.parametrize("in_file", ["marker", "Hierarchy", "Beat"])
def test_component_kinds_are_read_exactly(in_file):
    # As TiLiA 0.7 reads them: "marker" isn't a component kind, although it is
    # the API's name for one, so it stays apart from markers and keeps its spelling.
    kind = component_kind_from_file(in_file)
    assert kind == UnknownKind(in_file)
    assert kind != in_file.lower()
    assert component_kind_to_file(kind) == in_file


def test_an_unknown_kind_is_not_text():
    assert UnknownKind("marker") != "marker"
    assert isinstance(UnknownKind("marker"), UnknownKind)
    assert {UnknownKind("a"), UnknownKind("a")} == {UnknownKind("a")}


@pytest.mark.parametrize(
    "to_file",
    [timeline_kind_to_file, component_kind_to_file],
    ids=["timeline", "component"],
)
def test_a_kind_given_as_text_must_be_known(to_file):
    with pytest.raises(ValueError, match="UnknownKind"):
        to_file("lyrics")


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
        ("a\r\r\nb\r\r\r\n", ["a", "b", ""]),
        ("a\r", ["a\r"]),
        ('\t"x" \\ ü\n', ['\t"x" \\ ü', ""]),
        ("", [""]),
    ],
)
def test_setting_score_text_splits_it(text, lines):
    s = score([])
    s.text = text
    assert s.lines == lines


@pytest.mark.parametrize("text", ["a\r\r\nb", "a\rb\r\n", "a\r", "\r\n\r", ""])
def test_setting_a_score_text_back_changes_nothing(text):
    s = score([])
    s.text = text
    lines = list(s.lines)
    s.text = s.text
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
    assert m.cadenza is False
    assert m.restart is False
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
