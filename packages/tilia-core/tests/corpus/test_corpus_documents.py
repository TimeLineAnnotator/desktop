"""The seams with WP3's reader and WP15's settings (contracts/reader.md,
contracts/settings.md), and the stand-ins the tests use until those land."""

import dataclasses
import json

import corpus_docs
import examples
import pytest
from json_reader import JsonDocumentReader

from tilia_core import labels
from tilia_core.corpus.documents import (
    ComponentDoc,
    Document,
    DocumentReader,
    TimelineDoc,
    UnreadableFile,
)
from tilia_core.corpus.settings import CorpusSettings, NoSettings

READER = JsonDocumentReader()
FIXTURES = examples.load()["fixtures"]


def one_kind(kind):
    return corpus_docs.document(corpus_docs.KINDS[kind]("t1", 1), document_id=kind)


# --------------------------------------------------------------------------- #
# The documents
# --------------------------------------------------------------------------- #
def test_the_documents_are_frozen():
    doc = corpus_docs.every_kind()
    for obj, name in (
        (doc, "document_id"),
        (doc.timelines[0], "name"),
        (doc.timelines[0].components[0], "kind"),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, name, "x")


def test_the_fields_are_the_contracts():
    names = {
        Document: [
            "document_id",
            "format_version",
            "media_length",
            "time_unit",
            "fields",
            "timelines",
        ],
        TimelineDoc: [
            "id",
            "kind",
            "name",
            "ordinal",
            "fields",
            "attrs",
            "components",
        ],
        ComponentDoc: ["id", "kind", "attrs", "fields"],
    }
    for cls, fields in names.items():
        assert [f.name for f in dataclasses.fields(cls)] == fields, cls


def test_an_unreadable_file_carries_its_path_line_and_message(tmp_path):
    err = UnreadableFile(tmp_path / "a.tla", "not valid JSON", 12)
    assert (err.path, err.line, err.message) == (
        tmp_path / "a.tla",
        12,
        "not valid JSON",
    )
    assert str(err) == "can't read (line 12): not valid JSON"
    assert UnreadableFile(tmp_path / "a.tla", "too new").line is None
    assert str(UnreadableFile(tmp_path / "a.tla", "too new")) == "can't read: too new"


# --------------------------------------------------------------------------- #
# The stand-in reader
# --------------------------------------------------------------------------- #
def test_the_stand_in_is_a_document_reader():
    reader: DocumentReader = READER
    assert reader.extensions == (".tla",)


@pytest.mark.parametrize("kind", corpus_docs.KINDS)
def test_each_kind_round_trips(tmp_path, kind):
    doc = one_kind(kind)
    path = corpus_docs.write_doc(tmp_path / f"{kind}.tla", doc)
    assert READER.read(path) == doc
    # a file written in the canonical form gives back its own bytes
    assert READER.canonical_bytes(READER.read(path)) == path.read_bytes()


def test_every_kind_in_one_document_round_trips(tmp_path):
    doc = corpus_docs.every_kind()
    assert [tl.kind for tl in doc.timelines] == [
        "hierarchy",
        "marker",
        "range",
        "harmony",
        "beat",
        "score",
        "pdf",
        "spectrogram",
    ]
    path = corpus_docs.write_doc(tmp_path / "all.tla", doc)
    assert READER.read(path) == doc


def test_the_canonical_bytes_are_sorted_json_with_lf_and_a_final_newline():
    data = READER.canonical_bytes(corpus_docs.every_kind())
    text = data.decode("utf-8")
    assert text.endswith("}\n") and "\r" not in text
    assert not data.startswith(b"\xef\xbb\xbf")
    parsed = json.loads(text)
    assert (
        text == json.dumps(parsed, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    )


def test_text_is_written_as_it_is_not_escaped():
    doc = one_kind("marker")
    tl = doc.timelines[0]
    comp = dataclasses.replace(
        tl.components[0], attrs=dict(tl.components[0].attrs, label="Schluß ä")
    )
    doc = dataclasses.replace(
        doc, timelines=(dataclasses.replace(tl, components=(comp,)),)
    )
    assert "Schluß ä".encode() in READER.canonical_bytes(doc)


@pytest.mark.parametrize(
    "distortion",
    [
        {"crlf": True},
        {"shuffle_keys": True},
        {"bom": True},
        {"crlf": True, "shuffle_keys": True, "bom": True},
    ],
    ids=["crlf", "shuffled keys", "bom", "all three"],
)
def test_the_canonical_bytes_ignore_line_endings_key_order_and_a_bom(
    tmp_path, distortion
):
    doc = corpus_docs.every_kind()
    plain = corpus_docs.write_doc(tmp_path / "plain.tla", doc)
    odd = corpus_docs.write_doc(tmp_path / "odd.tla", doc, **distortion)
    assert odd.read_bytes() != plain.read_bytes()
    assert READER.read(odd) == doc
    assert READER.canonical_bytes(READER.read(odd)) == plain.read_bytes()


def test_broken_json_is_unreadable_with_its_line(tmp_path):
    path = corpus_docs.write_doc(tmp_path / "broken.tla", corpus_docs.every_kind())
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[6] = lines[6] + " oops"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(UnreadableFile) as info:
        READER.read(path)
    assert info.value.line == 7
    assert info.value.path == path
    assert info.value.message.startswith("not valid JSON")
    assert str(info.value).startswith("can't read (line 7): not valid JSON")


def test_broken_json_after_a_bom_and_crlf_gives_the_same_line(tmp_path):
    path = tmp_path / "broken.tla"
    path.write_bytes(b'\xef\xbb\xbf{\r\n  "a": 1,\r\n  oops\r\n}\r\n')
    with pytest.raises(UnreadableFile) as info:
        READER.read(path)
    assert info.value.line == 3


def test_json_that_is_no_document_is_unreadable(tmp_path):
    path = tmp_path / "list.tla"
    path.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(UnreadableFile) as info:
        READER.read(path)
    assert info.value.line is None


def test_a_file_that_isnt_utf8_is_unreadable(tmp_path):
    path = tmp_path / "latin1.tla"
    path.write_bytes('{"a": "Schluß"}'.encode("latin-1"))
    with pytest.raises(UnreadableFile):
        READER.read(path)


def test_a_file_that_cant_be_opened_raises_the_systems_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        READER.read(tmp_path / "missing.tla")
    with pytest.raises(OSError):
        READER.read(tmp_path)  # a folder


@pytest.mark.parametrize(
    "name, temporary",
    [
        ("x.tmp.tla", True),
        ("X.TMP.TLA", True),
        ("a.b.tmp.tla", True),
        ("x.tla", False),
        ("tmp.tla", False),
        ("x.tmp", False),
        ("x.tla.tmp", False),
    ],
)
def test_temporary_files(name, temporary):
    assert READER.is_temporary(name) is temporary


# --------------------------------------------------------------------------- #
# Documents from the examples' fixtures
# --------------------------------------------------------------------------- #
ATTRIBUTES = {  # contracts/reader.md, "The attributes the index uses"
    "hierarchy": {"start", "end", "level", "label", "color", "comments"},
    "marker": {"time", "label", "color", "comments"},
    "range": {"start", "end", "row_id", "label", "color", "comments"},
    "harmony": {
        "time",
        "step",
        "accidental",
        "quality",
        "inversion",
        "applied_to",
        "custom_text",
        "comments",
    },
    "mode": {"time", "step", "accidental", "type", "comments"},
    "beat": {"time"},
}


@pytest.mark.parametrize("name", FIXTURES)
def test_a_fixture_gives_a_document_with_the_attributes_the_index_uses(tmp_path, name):
    fixture = FIXTURES[name]
    doc = corpus_docs.document_from_fixture(fixture)
    assert doc.document_id == fixture.get("name", "f1")
    assert doc.media_length == fixture["length"]
    assert [tl.name for tl in doc.timelines] == [
        tl["name"] for tl in fixture["timelines"]
    ]
    assert [tl.ordinal for tl in doc.timelines] == list(
        range(1, len(fixture["timelines"]) + 1)
    )
    for tl in doc.timelines:
        assert tl.id.startswith(doc.document_id + ":t")
        for comp in tl.components:
            assert comp.id.startswith(tl.id + ":")
            assert ATTRIBUTES[comp.kind] <= set(comp.attrs), (tl.name, comp.kind)
        if tl.kind == "range":
            assert all({"id", "name"} <= set(r) for r in tl.attrs["rows"])
        if tl.kind == "beat":
            assert {"beat_pattern", "measure_numbers", "beats_in_measure"} <= set(
                tl.attrs
            )
    path = corpus_docs.write_doc(tmp_path / f"{name}.tla", doc)
    assert READER.read(path) == doc


def test_a_fixtures_roles_and_authors_are_timeline_fields():
    doc = corpus_docs.document_from_fixture(FIXTURES["sonata"])
    by_name = {tl.name: dict(tl.fields) for tl in doc.timelines}
    assert by_name["Form (Caplin)"] == {"role": "form", "author": "Caplin"}
    assert by_name["Cadences"] == {"role": "cadences"}
    assert by_name["Harmony"] == {"role": "harmony"}
    assert by_name["Fermatas"] == {}


def test_a_fixtures_file_fields_are_the_documents():
    doc = corpus_docs.document_from_fixture(FIXTURES["harmony"])
    assert doc.fields == {"composer": "Mozart"}


# --------------------------------------------------------------------------- #
# The settings
# --------------------------------------------------------------------------- #
def test_no_settings_answers():
    settings: CorpusSettings = NoSettings()
    doc = corpus_docs.every_kind()
    tl = doc.timelines[0]
    assert tl.fields["role"] == "form"  # the file's own role is left to it
    assert settings.manifest_paths == ()
    assert settings.role(tl, doc) is None
    grammar = settings.grammar(tl, doc)
    assert isinstance(grammar, labels.WholeLabel)
    assert grammar.categories("Verse 1/Chorus") == ("verse 1/chorus",)
    assert settings.includes("any/path.tla") is True
    assert settings.includes(".hidden/x.tla") is True
