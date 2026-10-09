"""T5's first test: a file the core wrote, read and written again without an
edit, keeps its bytes. Also what the reader makes of a file in the current
format, and which versions it reads."""

import json
import math
import re
import unicodedata
import uuid
from pathlib import Path

import pytest

from tilia_core import tla

GOLDEN = Path(__file__).parent / "golden"
GOLDEN_FILES = sorted(GOLDEN.glob("*.tla"))
EVERY_KIND = GOLDEN / "every-kind.tla"
EMPTY = GOLDEN / "empty.tla"
UNKNOWN = GOLDEN / "unknown.tla"


@pytest.fixture(params=GOLDEN_FILES, ids=lambda path: path.name)
def golden(request):
    return request.param


def named(doc, name):
    return next(tl for tl in doc.timelines.values() if tl.name == name)


def nth(timeline, index):
    return list(timeline.components.values())[index]


def test_there_are_golden_files():
    assert [path.name for path in GOLDEN_FILES] == [
        "empty.tla",
        "every-kind.tla",
        "unknown.tla",
    ]


def test_reading_and_writing_gives_the_files_bytes(golden):
    assert tla.canonical_bytes(tla.read(golden)) == golden.read_bytes()


def test_loads_reads_bytes_as_read_reads_the_file(golden):
    data = golden.read_bytes()
    assert tla.canonical_bytes(tla.loads(data)) == data


def test_writing_again_changes_nothing(golden):
    doc = tla.read(golden)
    first = tla.canonical_bytes(doc)
    assert tla.canonical_bytes(doc) == first
    assert tla.canonical_bytes(tla.loads(first)) == first


def _reversed(value, key=None):
    """`value` with every object's keys in reverse order, except metadata's
    entries, whose order is the user's; lists are content and keep theirs."""
    if isinstance(value, dict):
        items = [(k, _reversed(v, k)) for k, v in value.items()]
        return dict(items if key == "metadata" else reversed(items))
    if isinstance(value, list):
        return [_reversed(item) for item in value]
    return value


def test_any_key_order_and_layout_is_written_in_the_one_form():
    content = _reversed(json.loads(EVERY_KIND.read_bytes()))
    data = json.dumps(content, indent="\t", ensure_ascii=True).encode()
    assert tla.canonical_bytes(tla.loads(data)) == EVERY_KIND.read_bytes()


def test_entries_are_written_in_id_order_whatever_the_documents_order():
    doc = tla.read(EVERY_KIND)
    doc.timelines = dict(reversed(doc.timelines.items()))
    for timeline in doc.timelines.values():
        timeline.components = dict(reversed(timeline.components.items()))
    assert tla.canonical_bytes(doc) == EVERY_KIND.read_bytes()


def test_scores_are_written_in_id_order():
    doc = tla.read(EVERY_KIND)
    (score,) = doc.scores.values()
    first = tla.Score(id="00000000-0000-7000-8000-000000000000", format="mei")
    first.source, first.license = {}, "NOASSERTION"
    doc.scores = {score.id: score, first.id: first}
    data = tla.canonical_bytes(doc)
    scores = data[data.index(b'\n  "scores": [') :]
    assert scores.index(first.id.encode()) < scores.index(score.id.encode())


def test_text_in_another_normal_form_is_read_as_nfc_and_written_so():
    golden = EVERY_KIND.read_text("utf-8")
    decomposed = golden.replace(
        "Überleitung", unicodedata.normalize("NFD", "Überleitung")
    )
    assert decomposed != golden
    doc = tla.loads(decomposed.encode())
    assert nth(named(doc, "Form"), 1).attrs["label"] == "Hauptsatz – Überleitung"
    assert tla.canonical_bytes(doc) == EVERY_KIND.read_bytes()


def test_score_lines_are_kept_as_imported():
    doc = tla.read(EVERY_KIND)
    (score,) = doc.scores.values()
    assert "<title>Ständchen</title>" in score.lines[4]
    assert score.lines[-1] == ""
    assert score.lines[12].startswith("\t\t\t<staffGrp>")


def test_numbers_read_back_exactly():
    doc = tla.read(EVERY_KIND)
    nth(named(doc, "Form"), 0).attrs["start"] = 12.345678901
    nth(named(doc, "Cadences"), 0).attrs["time"] = 0.1 + 0.2
    data = tla.canonical_bytes(doc)
    assert b'"start": 12.345678901,' in data
    assert b'"time": 0.30000000000000004,' in data
    again = tla.loads(data)
    start = nth(named(again, "Form"), 0).attrs["start"]
    time = nth(named(again, "Cadences"), 0).attrs["time"]
    assert (type(start), start) == (float, 12.345678901)
    assert (type(time), time) == (float, 0.1 + 0.2)


def test_integers_stay_integers():
    doc = tla.read(UNKNOWN)
    beats = next(iter(doc.timelines.values()))
    assert [type(c.attrs["time"]) for c in beats.components.values()] == [int, int]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_a_number_json_cannot_hold_raises_naming_its_place(value):
    doc = tla.read(EVERY_KIND)
    cadences = named(doc, "Cadences")
    marker = nth(cadences, 1)
    marker.attrs["time"] = value
    place = f"/timelines/{cadences.id}/components/{marker.id}/time"
    with pytest.raises(ValueError, match=re.escape(place)):
        tla.canonical_bytes(doc)


@pytest.mark.parametrize(
    "where, place",
    [
        (lambda doc: doc.extra.update(x=[1, math.nan]), "/x/1"),
        (lambda doc: doc.metadata.update(tempo=math.inf), "/metadata/tempo"),
        (lambda doc: setattr(doc, "media_length", math.nan), "/media/length"),
        (lambda doc: doc.metadata.update({"a/b~c": math.nan}), "/metadata/a~1b~0c"),
    ],
)
def test_a_nan_anywhere_raises_naming_its_place(where, place):
    doc = tla.read(EVERY_KIND)
    where(doc)
    with pytest.raises(ValueError, match=re.escape(place)):
        tla.canonical_bytes(doc)


def test_a_value_json_has_no_type_for_raises_naming_its_place():
    doc = tla.read(EVERY_KIND)
    doc.metadata["genre"] = {"Lied", "romantic"}
    with pytest.raises(ValueError, match=re.escape("/metadata/genre")):
        tla.canonical_bytes(doc)


def test_a_downbeat_whose_mark_holds_only_defaults_is_written_as_an_empty_mark():
    doc = tla.read(EVERY_KIND)
    beats = named(doc, "Beats")
    downbeat = nth(beats, 1)  # bar 1, after the pickup: its mark is {}
    downbeat.attrs["measure"] = {
        "number": 1,
        "label": "1",
        "force_display": False,
        "cadenza": False,
        "restart": False,
        "source": "tapped",
        "metadata": {},
    }
    data = tla.canonical_bytes(doc)
    assert (
        f'        "{downbeat.id}": {{\n'
        '          "kind": "BEAT",\n'
        '          "time": 1.0,\n'
        '          "measure": {},\n'
    ) in data.decode()
    assert data == EVERY_KIND.read_bytes()
    again = tla.loads(data).timelines[beats.id].components[downbeat.id]
    assert again.attrs["measure"] == {}


def test_an_empty_mark_is_never_left_out():
    doc = tla.read(EVERY_KIND)
    marks = ["measure" in c.attrs for c in named(doc, "Beats").components.values()]
    # The pickup, bars 1, 2a, 1, 2b, 2c, 3 and 4: three of them are {}.
    assert marks.count(True) == 8


# What the reader gives


def test_a_current_file_is_read_as_it_is():
    doc = tla.read(EVERY_KIND)
    content = json.loads(EVERY_KIND.read_bytes())
    assert doc.format_version == tla.FORMAT_VERSION == "1.0.0-draft.1"
    assert doc.document_id == content["document_id"]
    assert (doc.app_name, doc.time_unit) == ("TiLiA", "seconds")
    assert (doc.media_path, doc.media_length) == ("../audio/Ständchen.flac", 17.5)
    assert doc.metadata == content["metadata"]
    assert list(doc.timelines) == list(content["timelines"])
    assert [tl.ordinal for tl in doc.timelines.values()] == list(range(1, 11))
    assert doc.origin == EVERY_KIND.absolute()
    assert doc.warnings == []
    assert tla.loads(EVERY_KIND.read_bytes()).origin is None


def test_kinds_are_given_in_lower_case():
    doc = tla.read(EVERY_KIND)
    assert [tl.kind for tl in doc.timelines.values()] == [
        "slider",
        "beat",
        "beat",
        "hierarchy",
        "marker",
        "harmony",
        "range",
        "score",
        "pdf",
        "audiowave",
    ]
    kinds = {c.kind for tl in doc.timelines.values() for c in tl.components.values()}
    assert kinds == {
        "beat",
        "hierarchy",
        "marker",
        "mode",
        "harmony",
        "range",
        "pdf_marker",
    }


def test_attributes_at_their_default_are_filled_in():
    doc = tla.read(EVERY_KIND)
    form = named(doc, "Form")
    assert form.attrs == {"height": 60, "is_visible": True, "measure_table": None}
    assert nth(form, 0).attrs == {
        "start": 1.0,
        "pre_start": 1.0,
        "end": 17.5,
        "post_end": 17.5,
        "level": 3,
        "label": "Exposição",
        "color": "#5c6bc0",
        "comments": "",
    }
    assert nth(named(doc, "Cadences"), 2).attrs == {
        "time": 16.0,
        "comments": "",
        "label": "",
        "color": None,
    }
    assert named(doc, "Beats").attrs["measure_source"] == "tapped"
    assert named(doc, "Harmony").attrs["level_height"] == 35
    assert named(doc, "Score").attrs["is_visible"] is True


def test_a_beats_mark_and_unit_are_kept_as_stored():
    # The measure table, which resolves a mark's number, label and source, is
    # built from them.
    beats = named(tla.read(EVERY_KIND), "Beats")
    assert nth(beats, 0).attrs == {
        "time": 0.0,
        "measure": {"number": 0},
        "beat_unit": {"denominator": 4, "units": "1"},
    }
    assert nth(beats, 1).attrs == {"time": 1.0, "measure": {}}
    assert nth(beats, 1).metadata == {"tags": ["check"]}
    assert nth(beats, 2).attrs == {"time": 2.0}


def test_unknown_kinds_and_keys_are_kept():
    doc = tla.read(UNKNOWN)
    beats, markers, rows, lyrics = doc.timelines.values()
    assert doc.extra == {
        "Alpha": 1,
        "zeta": {"b": 1, "a": [1, {"d": 2, "c": 3}]},
        "ärger": "kept",
    }
    assert list(doc.extra["zeta"]) == ["b", "a"]
    assert doc.media_extra == {"x_media": "kept"}
    assert beats.extra == {"x_timeline": "kept"}
    assert nth(beats, 0).extra == {"x_beat": "kept"}
    assert nth(beats, 0).attrs["measure"] == {"number": 1, "x_mark": "kept"}
    marker, other = markers.components.values()
    assert marker.extra == {
        "Y": True,
        "x_component": {"b": 1, "a": [2, {"d": 3, "c": 4}]},
    }
    assert other.kind == tla.UnknownKind("marker")
    assert (other.attrs, other.extra) == ({}, {"label": "spelled otherwise", "time": 2})
    assert rows.attrs["rows"] == [{"id": "aZ3k9P", "name": "Row", "x_row": "kept"}]
    assert lyrics.kind == tla.UnknownKind("Lyrics")
    assert (lyrics.name, lyrics.ordinal, lyrics.metadata) == (
        "Lyrics",
        4,
        {"role": "lyrics"},
    )
    assert lyrics.raw == json.loads(UNKNOWN.read_bytes())["timelines"][lyrics.id]
    (score,) = doc.scores.values()
    assert score.extra == {"x_score": "kept"}
    assert score.source == {"file": "a.mei", "x_source": "kept"}


def test_an_unknown_kind_is_written_from_raw():
    doc = tla.read(UNKNOWN)
    lyrics = list(doc.timelines.values())[3]
    lyrics.raw["font"] = "sans-serif"
    assert b'"font": "sans-serif"' in tla.canonical_bytes(doc)


# Versions


def with_version(version):
    content = json.loads(EMPTY.read_bytes())
    if version is None:
        del content["version"]
    else:
        content["version"] = version
    return json.dumps(content).encode()


@pytest.mark.parametrize("version", ["1.0.0-draft.2", "1.0.0-draft.0", "1.0.0-alpha"])
def test_another_draft_is_refused(version):
    with pytest.raises(tla.UnreadableFile) as error:
        tla.loads(with_version(version))
    assert error.value.message == (
        f"a draft of the format ({version}): convert it again from its sources"
    )
    assert error.value.place == "/version"


@pytest.mark.parametrize("version", ["1.0.0", "1.0.1", "1.1.0-draft.1", "2.0.0", "1.2"])
def test_a_newer_format_is_refused_naming_its_version(version):
    with pytest.raises(tla.UnreadableFile) as error:
        tla.loads(with_version(version))
    assert error.value.message == f"written by a newer TiLiA (format {version})"


@pytest.mark.parametrize("version", ["0.7.0", "0.5.15", "0.7.0rc1", "", None])
def test_older_files_wait_for_the_migration(version):
    with pytest.raises(NotImplementedError):
        tla.loads(with_version(version))


def test_a_version_must_be_text():
    with pytest.raises(tla.UnreadableFile) as error:
        tla.loads(with_version(1.0))
    assert error.value.place == "/version"


# New documents


def test_a_new_document_is_written_as_empty_tla():
    doc = tla.new_document()
    golden = EMPTY.read_bytes()
    golden_id = json.loads(golden)["document_id"]
    expected = golden.replace(golden_id.encode(), doc.document_id.encode())
    assert tla.canonical_bytes(doc) == expected
    assert doc.format_version == tla.FORMAT_VERSION


def test_a_new_document_gets_a_new_id():
    first, second = tla.new_document(), tla.new_document()
    assert first.document_id != second.document_id
    assert uuid.UUID(first.document_id).version == 7


def test_a_new_document_in_quarters():
    assert tla.new_document(time_unit="quarters").time_unit == "quarters"
    with pytest.raises(ValueError, match="minutes"):
        tla.new_document(time_unit="minutes")
