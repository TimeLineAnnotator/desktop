"""Text in any script: written as UTF-8 characters, in NFC, and read back
unchanged; a byte-order mark read and never written; a score's content kept
as imported. CI runs these on Windows, macOS and Linux."""

import codecs
import json
import unicodedata

import pytest

from tilia_core import tla

BOM = codecs.BOM_UTF8

# A label in each script the format promises to keep: German, Portuguese,
# Greek, Chinese, a right-to-left script (Hebrew) and emoji, each in NFC.
SCRIPTS = {
    "German": "Hauptsatz – Überleitung",
    "Portuguese": "Exposição",
    "Greek": "Θέμα β",
    "Chinese": "主題",
    "Hebrew": "נושא",
    "emoji": "Schluss 🎵🎻",
}
# Those that NFD writes otherwise: a letter and its combining marks.
DECOMPOSABLE = ["German", "Portuguese", "Greek"]

DOCUMENT_ID = "019a0000-0000-7000-8000-000000000000"
TIMELINE_ID = "019a0000-0000-7000-8000-000000000001"
MARKER_ID = "019a0000-0000-7000-8000-000000000002"
SCORE_ID = "019a0000-0000-7000-8000-000000000003"


def nfd(text):
    return unicodedata.normalize("NFD", text)


def document(text):
    """A document with `text` in every place text goes: a label, a comment, a
    timeline's name, the media's path, and metadata names and values on the
    document, a timeline and a component."""
    marker = tla.Component(
        id=MARKER_ID,
        kind="marker",
        attrs={"time": 1.0, "label": text, "comments": text},
        metadata={text: text, "tags": [text]},
    )
    timeline = tla.Timeline(
        id=TIMELINE_ID,
        kind="marker",
        ordinal=1,
        name=text,
        metadata={"author": text, text: "x"},
        attrs={"height": 30},
        components={MARKER_ID: marker},
    )
    doc = tla.new_document()
    doc.document_id = DOCUMENT_ID
    doc.media_path = f"../audio/{text}.flac"
    doc.metadata = {"title": text, text: "x", "genre": ["Lied", text]}
    doc.timelines = {TIMELINE_ID: timeline}
    return doc


def text_of(doc):
    """What `document` puts in each place, as `doc` has it."""
    timeline = doc.timelines[TIMELINE_ID]
    marker = timeline.components[MARKER_ID]
    return {
        "label": marker.attrs["label"],
        "comments": marker.attrs["comments"],
        "component metadata": marker.metadata,
        "timeline name": timeline.name,
        "timeline metadata": timeline.metadata,
        "media path": doc.media_path,
        "document metadata": doc.metadata,
    }


def with_score(doc, lines):
    score = tla.Score(id=SCORE_ID, format="mei", lines=lines)
    score.source = {"file": "Ständchen.musicxml"}
    doc.scores = {SCORE_ID: score}
    return doc


@pytest.fixture(params=list(SCRIPTS), ids=str)
def text(request):
    return SCRIPTS[request.param]


@pytest.fixture(params=DECOMPOSABLE, ids=str)
def decomposable(request):
    return SCRIPTS[request.param]


def test_the_texts_are_in_nfc_and_the_decomposable_ones_have_another_form():
    # So that the tests below compare what they mean to.
    for name, text in SCRIPTS.items():
        assert unicodedata.is_normalized("NFC", text), name
        assert (nfd(text) != text) == (name in DECOMPOSABLE), name


# Written as characters and read back unchanged


def test_text_is_written_as_utf8_characters_not_escapes(text):
    data = tla.canonical_bytes(document(text))
    assert json.dumps(text, ensure_ascii=False).encode("utf-8") in data
    assert b"\\u" not in data


def test_text_reads_back_unchanged(text):
    data = tla.canonical_bytes(document(text))
    assert text_of(tla.loads(data)) == text_of(document(text))


def test_text_reads_back_unchanged_from_a_file(text, tmp_path):
    path = tmp_path / "text.tla"
    path.write_bytes(tla.canonical_bytes(document(text)))
    doc = tla.read(path)
    assert text_of(doc) == text_of(document(text))
    assert tla.canonical_bytes(doc) == path.read_bytes()


# NFC


def test_text_typed_in_nfd_is_written_in_nfc(decomposable):
    # As a program that keeps text decomposed, such as one on macOS, gives it.
    written = tla.canonical_bytes(document(nfd(decomposable)))
    assert written == tla.canonical_bytes(document(decomposable))
    assert nfd(decomposable).encode("utf-8") not in written


def test_a_file_holding_nfd_text_reads_as_nfc(decomposable):
    # A hand edit in an editor that writes NFD.
    nfc_bytes = tla.canonical_bytes(document(decomposable))
    nfd_bytes = nfc_bytes.decode("utf-8").replace(decomposable, nfd(decomposable))
    nfd_bytes = nfd_bytes.encode("utf-8")
    assert nfd_bytes != nfc_bytes
    doc = tla.loads(nfd_bytes)
    assert text_of(doc) == text_of(document(decomposable))
    assert tla.canonical_bytes(doc) == nfc_bytes


def test_a_label_in_nfd_and_one_in_nfc_are_written_alike(decomposable):
    # So that the same label typed on two computers is the same label.
    typed_here = tla.loads(tla.canonical_bytes(document(decomposable)))
    typed_there = tla.loads(tla.canonical_bytes(document(nfd(decomposable))))
    assert text_of(typed_here) == text_of(typed_there)


# Byte-order marks


def test_a_file_with_a_byte_order_mark_reads_and_is_written_without_one(text, tmp_path):
    written = tla.canonical_bytes(document(text))
    path = tmp_path / "bom.tla"
    path.write_bytes(BOM + written)
    doc = tla.read(path)
    assert text_of(doc) == text_of(document(text))
    assert tla.canonical_bytes(doc) == written
    assert not tla.canonical_bytes(doc).startswith(BOM)


def test_a_file_with_a_byte_order_mark_and_crlf_is_written_in_the_one_form():
    # What Notepad's "UTF-8 with BOM" gives on Windows.
    written = tla.canonical_bytes(document(SCRIPTS["German"]))
    edited = BOM + written.replace(b"\n", b"\r\n")
    assert tla.canonical_bytes(tla.loads(edited)) == written


# Scores


def test_score_content_is_written_as_imported_not_in_nfc(decomposable):
    # A score's content is the file imported: the core never changes it.
    lines = ["<mei>", f"  <title>{nfd(decomposable)}</title>", "</mei>", ""]
    doc = with_score(document(nfd(decomposable)), lines)
    data = tla.canonical_bytes(doc)
    assert json.dumps(lines[1], ensure_ascii=False).encode("utf-8") in data
    again = tla.loads(data)
    assert again.scores[SCORE_ID].lines == lines
    # The labels around it are in NFC all the same.
    assert text_of(again) == text_of(document(decomposable))
    assert tla.canonical_bytes(again) == data


def test_score_content_in_a_file_is_read_as_it_is(decomposable):
    lines = ["<mei>", f"  <title>{decomposable}</title>", "</mei>", ""]
    data = tla.canonical_bytes(with_score(document(decomposable), lines))
    edited = data.decode("utf-8").replace(decomposable, nfd(decomposable))
    doc = tla.loads(edited.encode("utf-8"))
    assert doc.scores[SCORE_ID].lines[1] == f"  <title>{nfd(decomposable)}</title>"
    assert text_of(doc) == text_of(document(decomposable))
