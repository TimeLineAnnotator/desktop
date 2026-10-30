"""Metadata at every level: the file's, a timeline's and a component's fields,
each a text or a list of texts, round-trip in the order they were added; a
timeline's `author` is one full name, kept as typed; a `vocabulary` names
one as `id@version` or by a bare id; an empty `metadata` is left out of a
timeline or a component, and written on the file (FR-070–FR-073)."""

import json
import unicodedata

import pytest

from tilia_core import tla
from tilia_core.tla import check, writer

TIMELINE_ID = "019a0000-0000-7000-8000-000000000001"
SECTION_ID = "019a0000-0000-7000-8000-000000000002"
MARKER_TIMELINE_ID = "019a0000-0000-7000-8000-000000000003"
MARKER_ID = "019a0000-0000-7000-8000-000000000004"


def nfd(text):
    return unicodedata.normalize("NFD", text)


def document(file=None, timeline=None, component=None):
    """A document with a hierarchy timeline holding one section, and a marker
    timeline holding one marker, with `file`, `timeline` and `component` as
    the metadata of the file, of the hierarchy timeline and of its section."""
    section = tla.Component(
        id=SECTION_ID,
        kind="hierarchy",
        attrs={"start": 0.0, "end": 10.0, "level": 1, "label": "A"},
        metadata=dict(component or {}),
    )
    form = tla.Timeline(
        id=TIMELINE_ID,
        kind="hierarchy",
        ordinal=1,
        name="Form",
        metadata=dict(timeline or {}),
        attrs={"height": 120},
        components={SECTION_ID: section},
    )
    marker = tla.Component(id=MARKER_ID, kind="marker", attrs={"time": 1.0})
    cadences = tla.Timeline(
        id=MARKER_TIMELINE_ID,
        kind="marker",
        ordinal=2,
        name="Cadences",
        attrs={"height": 30},
        components={MARKER_ID: marker},
    )
    doc = tla.new_document()
    doc.metadata = dict(file or {})
    doc.timelines = {TIMELINE_ID: form, MARKER_TIMELINE_ID: cadences}
    return doc


def written(doc):
    """What the writer writes for `doc`, once the reader's checks let it through."""
    return writer.checked_bytes(doc)


def round_trip(doc):
    return tla.loads(written(doc))


def stored(doc):
    """The file's content, as JSON gives it."""
    return json.loads(written(doc))


def form(doc):
    return doc.timelines[TIMELINE_ID]


def section(doc):
    return form(doc).components[SECTION_ID]


# Fields at every level round-trip, in their order (FR-070, FR-071)

FILE_FIELDS = {
    "title": "Sonata Op. 2 No. 1, I",
    "notes": "",
    "composer": "Beethoven",
    "genres": ["sonata", "piano music"],
    "recording year": "1958",
}
TIMELINE_FIELDS = {
    "role": "form",
    "author": "Anne",
    "source": "LCMA",
    "vocabulary": "lcma-form@0.3.0",
    "editors": ["Felipe", "Anne"],
}
COMPONENT_FIELDS = {
    "tags": ["recheck", "check", "Satz"],
    "generated_by": "group/A",
    "confidence": "low",
}


def test_metadata_on_the_file_a_timeline_and_a_component_round_trips():
    doc = round_trip(document(FILE_FIELDS, TIMELINE_FIELDS, COMPONENT_FIELDS))
    assert doc.metadata == FILE_FIELDS
    assert form(doc).metadata == TIMELINE_FIELDS
    assert section(doc).metadata == COMPONENT_FIELDS
    assert doc.warnings == []


def test_fields_keep_the_order_they_were_added_in_at_every_level():
    # Not sorted: the order of a metadata's fields is the user's (layout.md,
    # *Order*), so TiLiA's metadata window keeps it.
    fields = {"z": "1", "a": "2", "m": ["3"]}
    doc = round_trip(document(fields, fields, fields))
    for metadata in (doc.metadata, form(doc).metadata, section(doc).metadata):
        assert list(metadata.items()) == list(fields.items())
    content = stored(doc)
    assert list(content["metadata"]) == ["z", "a", "m"]
    timeline = content["timelines"][TIMELINE_ID]
    assert list(timeline["metadata"]) == ["z", "a", "m"]
    assert list(timeline["components"][SECTION_ID]["metadata"]) == ["z", "a", "m"]


def test_a_list_keeps_its_order_and_its_repeats():
    values = ["recheck", "check", "Satz", "check"]
    doc = round_trip(document({"genres": values}, {"x": values}, {"tags": values}))
    assert doc.metadata["genres"] == values
    assert form(doc).metadata["x"] == values
    assert section(doc).metadata["tags"] == values


def test_metadata_is_written_after_the_attributes():
    content = stored(document({}, {"role": "form"}, {"tags": ["check"]}))
    timeline = content["timelines"][TIMELINE_ID]
    assert list(timeline) == [
        "kind",
        "name",
        "ordinal",
        "height",
        "metadata",
        "components",
    ]
    assert list(timeline["components"][SECTION_ID]) == [
        "kind",
        "start",
        "end",
        "level",
        "label",
        "metadata",
    ]


def test_a_field_a_user_added_round_trips_at_every_level():
    fields = {"analysis license": "CC BY 4.0", "Tonart": ["C-Dur"]}
    doc = round_trip(document(fields, fields, fields))
    assert doc.metadata == form(doc).metadata == section(doc).metadata == fields


def test_field_names_that_differ_only_in_letter_case_stay_apart():
    # Folding them is the index's (WP12).
    fields = {"Composer": "Beethoven", "composer": "L. v. Beethoven"}
    doc = round_trip(document(fields, fields, fields))
    assert doc.metadata == form(doc).metadata == section(doc).metadata == fields


# A timeline's author (FR-071a)


def test_an_author_typed_in_decomposed_form_is_one_text_in_nfc():
    # US7, scenario 6: "Maria João Costa", typed in decomposed form.
    typed = nfd("Maria João Costa")
    assert typed != "Maria João Costa"
    doc = round_trip(document(timeline={"author": typed}))
    assert form(doc).metadata == {"author": "Maria João Costa"}
    assert stored(doc)["timelines"][TIMELINE_ID]["metadata"] == {
        "author": "Maria João Costa"
    }


@pytest.mark.parametrize(
    "author",
    [
        "Maria João Costa",
        "costa, maria joão",
        "  Maria  João Costa ",
        "M. J. Costa",
        "MARIA JOÃO COSTA",
        "Ἀριστόξενος",
        "李四",
    ],
)
def test_an_author_is_stored_as_typed(author):
    # NFC is its only change: no case folding, no trimming, no splitting
    # into names, so that TQL matches it exactly, as a full name.
    doc = round_trip(document(timeline={"author": nfd(author)}))
    assert form(doc).metadata["author"] == unicodedata.normalize("NFC", author)
    again = round_trip(doc)
    assert form(again).metadata["author"] == form(doc).metadata["author"]


def test_an_author_reads_back_as_the_file_stores_it():
    data = written(document(timeline={"author": "Maria João Costa"}))
    assert '"author": "Maria João Costa"' in data.decode("utf-8")
    assert tla.canonical_bytes(tla.loads(data)) == data


# A timeline's vocabulary (FR-072, #31)


@pytest.mark.parametrize("vocabulary", ["lcma-form@0.3.0", "cadences"])
def test_a_vocabulary_reference_is_written_and_read_without_a_warning(vocabulary):
    # US7, scenario 2: an id with its version, or the bare id of a vocabulary
    # defined in the corpus's manifest.
    doc = round_trip(document(timeline={"vocabulary": vocabulary}))
    assert form(doc).metadata == {"vocabulary": vocabulary}
    assert doc.warnings == []


def test_an_invalid_vocabulary_is_written_and_read_with_a_warning():
    # US7, scenario 3: kept as it is, with a warning that names the timeline.
    doc = round_trip(document(timeline={"vocabulary": "LCMA/Form@0.3"}))
    assert form(doc).metadata == {"vocabulary": "LCMA/Form@0.3"}
    assert [(w.place, w.message) for w in doc.warnings] == [
        (
            f"/timelines/{TIMELINE_ID}/metadata/vocabulary",
            'the vocabulary "LCMA/Form@0.3" of the timeline "Form" isn\'t a'
            " valid reference",
        )
    ]


# An empty metadata (#161, points 6 and 15)


def test_an_empty_metadata_is_left_out_of_timelines_and_components():
    content = stored(document({}, {}, {}))
    timeline = content["timelines"][TIMELINE_ID]
    assert "metadata" not in timeline
    assert "metadata" not in timeline["components"][SECTION_ID]
    other = content["timelines"][MARKER_TIMELINE_ID]
    assert "metadata" not in other
    assert "metadata" not in other["components"][MARKER_ID]


def test_an_empty_metadata_is_written_on_the_file():
    content = stored(document())
    assert content["metadata"] == {}
    assert list(content).index("metadata") == list(content).index("media") + 1


def test_an_empty_metadata_left_out_reads_as_empty():
    doc = round_trip(document({}, {}, {}))
    assert (doc.metadata, form(doc).metadata, section(doc).metadata) == ({}, {}, {})


def test_the_files_empty_fields_are_kept():
    # TiLiA's default entries stay, even when empty (point 15).
    fields = {"title": "", "notes": "", "composer": "", "genres": []}
    doc = round_trip(document(file=fields))
    assert list(doc.metadata.items()) == list(fields.items())
    assert stored(doc)["metadata"] == fields


def test_a_timelines_and_a_components_empty_fields_are_kept():
    # An empty field is a field: only an empty metadata is left out.
    fields = {"role": "", "tags": []}
    doc = round_trip(document(timeline=fields, component=fields))
    assert form(doc).metadata == section(doc).metadata == fields


# Each value is a text or a list of texts (FR-070)

PLACES = {
    "the file": (lambda doc: doc, "/metadata"),
    "a timeline": (form, f"/timelines/{TIMELINE_ID}/metadata"),
    "a component": (
        section,
        f"/timelines/{TIMELINE_ID}/components/{SECTION_ID}/metadata",
    ),
}
NOT_TEXT = {
    "a number": (5, ""),
    "true": (True, ""),
    "an object": ({"a": "b"}, ""),
    "a list holding a number": (["a", 2], "/1"),
    "a list holding a list": (["a", ["b"]], "/1"),
    "a list holding null": (["a", None], "/1"),
}


@pytest.mark.parametrize("level", PLACES)
@pytest.mark.parametrize("value", NOT_TEXT)
def test_a_field_that_isnt_text_or_a_list_of_texts_isnt_written(level, value):
    entry, place = PLACES[level]
    given, under = NOT_TEXT[value]
    doc = document()
    entry(doc).metadata = {"x": given}
    with pytest.raises(tla.UnreadableFile) as raised:
        written(doc)
    assert raised.value.place == f"{place}/x{under}"


@pytest.mark.parametrize("level", PLACES)
@pytest.mark.parametrize("value", NOT_TEXT)
def test_a_field_that_isnt_text_or_a_list_of_texts_is_refused_on_reading(level, value):
    entry, place = PLACES[level]
    given, under = NOT_TEXT[value]
    content = stored(document())
    parent = content
    for step in place.strip("/").split("/")[:-1]:
        parent = parent[step]
    parent["metadata"] = {"x": given}
    with pytest.raises(tla.UnreadableFile) as raised:
        tla.loads(json.dumps(content).encode())
    assert raised.value.place == f"{place}/x{under}"


# The rule as the migration calls it (`check.is_field_value`)

FIELD_VALUES = ["", "Beethoven", [], ["sonata", "piano music"], ["", ""]]
NOT_FIELD_VALUES = [given for given, _ in NOT_TEXT.values()] + [None, 1.0]


@pytest.mark.parametrize("value", FIELD_VALUES)
def test_a_text_or_a_list_of_texts_is_a_field_value(value):
    assert check.is_field_value(value)


@pytest.mark.parametrize("value", NOT_FIELD_VALUES)
def test_anything_else_isnt_a_field_value(value):
    assert not check.is_field_value(value)


@pytest.mark.parametrize("value", FIELD_VALUES + NOT_FIELD_VALUES)
def test_is_field_value_gives_the_checks_verdict(value):
    doc = document(component={"x": value})
    try:
        written(doc)
    except tla.UnreadableFile:
        accepted = False
    else:
        accepted = True
    assert check.is_field_value(value) is accepted
