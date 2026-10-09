"""T5's first test: a file the core wrote, read and written again without an
edit, keeps its bytes. Also what the reader makes of a file in the current
format, and which versions it reads."""

import json
import math
import re
import sys
import types
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
    assert again.attrs["measure"] == {
        "force_display": False,
        "cadenza": False,
        "restart": False,
    }


def test_an_empty_mark_is_never_left_out():
    doc = tla.read(EVERY_KIND)
    marks = ["measure" in c.attrs for c in named(doc, "Beats").components.values()]
    # The pickup, bars 1, 2a, 1, 2b, 2c, 3 and 4: three of them are {}.
    assert marks.count(True) == 8


def beat_timeline(*beats):
    """A document with one beat timeline, its beats given as (id, time, mark)."""
    doc = tla.new_document()
    timeline = tla.Timeline(
        id=tla.new_id(), kind="beat", ordinal=1, attrs={"height": 35}
    )
    for beat_id, time, mark in beats:
        timeline.components[beat_id] = tla.Component(
            id=beat_id, kind="beat", attrs={"time": time, "measure": mark}
        )
    doc.timelines[timeline.id] = timeline
    return doc, timeline


def written_marks(doc, timeline):
    """The marks as the file holds them, in id order."""
    content = json.loads(tla.canonical_bytes(doc))
    components = content["timelines"][timeline.id]["components"]
    return [component["measure"] for component in components.values()]


def test_the_first_measures_number_is_always_written():
    doc, timeline = beat_timeline(
        ("b1", 0.0, {"number": 1}), ("b2", 1.0, {"number": 2})
    )
    assert written_marks(doc, timeline) == [{"number": 1}, {}]


def test_marks_follow_each_other_in_time_order_whatever_their_ids():
    doc, timeline = beat_timeline(
        ("b1", 1.0, {"number": 2}), ("b2", 0.0, {"number": 1})
    )
    assert written_marks(doc, timeline) == [{}, {"number": 1}]


def test_marks_at_one_time_follow_each_other_in_id_order():
    # Given in the other order: the document's order doesn't count.
    doc, timeline = beat_timeline(
        ("b2", 0.0, {"number": 6}), ("b1", 0.0, {"number": 5})
    )
    assert written_marks(doc, timeline) == [{"number": 5}, {}]


def test_a_mark_after_one_without_a_number_keeps_its_number():
    # With no number to follow, a later number has no default.
    doc, timeline = beat_timeline(("b1", 0.0, {}), ("b2", 1.0, {"number": 1}))
    assert written_marks(doc, timeline) == [{}, {"number": 1}]


def test_a_marks_label_and_source_are_left_out_at_their_default():
    doc, timeline = beat_timeline(
        ("b1", 0.0, {"number": 3, "label": "3", "source": "score"}),
        ("b2", 1.0, {"label": "4", "source": "tapped"}),
    )
    timeline.attrs["measure_source"] = "score"
    assert written_marks(doc, timeline) == [{"number": 3}, {"source": "tapped"}]


def test_none_for_a_derived_default_means_unset():
    # A mark's number is never null: None is the default, and is left out.
    doc, timeline = beat_timeline(
        ("b1", 0.0, {"number": 1}), ("b2", 1.0, {"number": None, "label": None})
    )
    assert written_marks(doc, timeline) == [{"number": 1}, {}]
    doc = tla.read(EVERY_KIND)
    form = named(doc, "Form")
    nth(form, 0).attrs["pre_start"] = None
    assert tla.canonical_bytes(doc) == EVERY_KIND.read_bytes()


def test_score_lines_given_as_a_tuple_are_written_as_they_are():
    doc = tla.read(EVERY_KIND)
    (score,) = doc.scores.values()
    score.lines = tuple(score.lines)  # its decomposed line stays decomposed
    assert tla.canonical_bytes(doc) == EVERY_KIND.read_bytes()


def test_a_surrogate_pair_given_as_two_characters_is_written_as_one():
    # As JSON reads the pair back: writing again then changes nothing.
    doc = tla.read(EVERY_KIND)
    doc.metadata["title"] = "cut \ud83c" + "\udfb5"
    data = tla.canonical_bytes(doc)
    again = tla.loads(data)
    assert again.metadata["title"] == "cut 🎵"
    assert tla.canonical_bytes(again) == data


def test_edits_to_a_timeline_of_an_unknown_kind_are_written():
    doc = tla.read(UNKNOWN)
    lyrics = list(doc.timelines.values())[3]
    assert lyrics.metadata is not lyrics.raw["metadata"]
    lyrics.name, lyrics.ordinal = "Words", 9
    lyrics.metadata["tags"] = ["sung"]
    lyrics.extra["font_size"] = 12
    again = tla.loads(tla.canonical_bytes(doc)).timelines[lyrics.id]
    assert (again.name, again.ordinal) == ("Words", 9)
    assert again.metadata == {"role": "lyrics", "tags": ["sung"]}
    assert (again.raw["font"], again.raw["font_size"]) == ("serif", 12)


def test_a_timeline_of_an_unknown_kind_gains_no_key_it_didnt_have():
    content = json.loads(UNKNOWN.read_bytes())
    lyrics = list(content["timelines"])[3]
    for key in ("name", "ordinal", "metadata"):
        del content["timelines"][lyrics][key]
    data = (json.dumps(content, indent=2, ensure_ascii=False) + "\n").encode()
    doc = tla.loads(data)
    timeline = doc.timelines[lyrics]
    assert (timeline.name, timeline.ordinal, timeline.metadata) == ("", 0, {})
    assert tla.canonical_bytes(doc) == data


def test_a_timeline_of_an_unknown_kind_keeps_its_components_in_raw():
    doc = tla.read(UNKNOWN)
    lyrics = list(doc.timelines.values())[3]
    marker = tla.Component(id=tla.new_id(), kind="marker", attrs={"time": 1.0})
    lyrics.components[marker.id] = marker
    with pytest.raises(ValueError, match="keeps its components in `raw`"):
        tla.canonical_bytes(doc)


@pytest.mark.parametrize("format", ["mei", "musicxml"])
def test_a_null_source_or_licence_is_kept(format):
    content = json.loads(UNKNOWN.read_bytes())
    content["scores"][0].update(format=format, source=None, license=None)
    doc = tla.loads(json.dumps(content).encode())
    (score,) = doc.scores.values()
    assert (score.source, score.license) == (None, None)
    (written,) = json.loads(tla.canonical_bytes(doc))["scores"]
    assert (written["source"], written["license"]) == (None, None)


# What the writer refuses


def test_a_key_set_both_as_an_attribute_and_as_an_unknown_key_is_refused():
    doc = tla.read(EVERY_KIND)
    cadences = named(doc, "Cadences")
    marker = nth(cadences, 0)
    marker.extra["label"] = "twice"
    place = f"/timelines/{cadences.id}/components/{marker.id}/label"
    with pytest.raises(ValueError, match=re.escape(place)):
        tla.canonical_bytes(doc)


def test_an_entry_under_another_id_is_refused():
    doc = tla.read(EVERY_KIND)
    cadences = named(doc, "Cadences")
    doc.timelines["another"] = doc.timelines.pop(cadences.id)
    with pytest.raises(ValueError, match="/timelines/another: holds the id"):
        tla.canonical_bytes(doc)


def test_a_kind_given_as_text_must_be_known():
    doc = tla.read(EVERY_KIND)
    cadences = named(doc, "Cadences")
    cadences.kind = "lyrics"
    with pytest.raises(ValueError, match=re.escape(f"/timelines/{cadences.id}/kind")):
        tla.canonical_bytes(doc)


def test_an_integer_too_long_to_read_back_is_refused():
    doc = tla.read(EVERY_KIND)
    doc.extra["n"] = 10**4300
    with pytest.raises(ValueError, match="/n: an integer too long"):
        tla.canonical_bytes(doc)
    doc.extra["n"] = 10**4300 - 1  # 4300 digits: Python reads it
    assert tla.loads(tla.canonical_bytes(doc)).extra["n"] == 10**4300 - 1


def test_a_measure_number_too_long_to_read_back_is_refused_naming_its_place():
    doc, timeline = beat_timeline(("b1", 0.0, {"number": 10**5000}))
    place = f"/timelines/{timeline.id}/components/b1/measure/number"
    with pytest.raises(ValueError, match=re.escape(place)):
        tla.canonical_bytes(doc)


@pytest.mark.skipif(
    not hasattr(sys, "set_int_max_str_digits"), reason="no limit to set"
)
def test_the_limit_on_integers_is_the_running_pythons():
    doc = tla.read(EVERY_KIND)
    doc.extra["n"] = 10**700  # 701 digits
    limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        with pytest.raises(ValueError, match="/n: an integer too long"):
            tla.canonical_bytes(doc)
    finally:
        sys.set_int_max_str_digits(limit)
    assert b'"n": 1000' in tla.canonical_bytes(doc)


def test_a_key_set_twice_is_named_with_where_it_was_set():
    doc = tla.read(EVERY_KIND)
    doc.media_extra["path"] = "elsewhere.flac"
    message = "/media/path: set both in media_path and media_length and in media_extra"
    with pytest.raises(ValueError, match=re.escape(message)):
        tla.canonical_bytes(doc)


FIELDS = "set both in the timeline's fields"
IN_RAW = "a timeline of a kind the core doesn't know keeps its components in `raw`"


@pytest.mark.parametrize(
    "attrs, extra, key, message",
    [
        ({"name": "a"}, {"name": "e"}, "name", f"{FIELDS} and in attrs"),
        ({"name": "a"}, {}, "name", f"{FIELDS} and in attrs"),
        ({"kind": "Marker"}, {}, "kind", f"{FIELDS} and in attrs"),
        ({}, {"ordinal": 2}, "ordinal", f"{FIELDS} and in extra"),
        ({"font": "a"}, {"font": "e"}, "font", "set both in attrs and in extra"),
        ({}, {"components": {}}, "components", IN_RAW),
        ({"components": {}}, {}, "components", IN_RAW),
    ],
)
def test_a_key_set_twice_on_a_timeline_of_an_unknown_kind_is_refused(
    attrs, extra, key, message
):
    # As on a timeline of a known kind, rather than the last one set winning.
    doc = tla.read(UNKNOWN)
    lyrics = list(doc.timelines.values())[3]
    lyrics.attrs.update(attrs)
    lyrics.extra.update(extra)
    place = f"/timelines/{lyrics.id}/{key}"
    with pytest.raises(ValueError, match=re.escape(f"{place}: {message}")):
        tla.canonical_bytes(doc)


def test_a_key_that_isnt_text_is_refused():
    doc = tla.read(EVERY_KIND)
    doc.metadata[1787] = "year"
    with pytest.raises(ValueError, match="/metadata: a key must be text"):
        tla.canonical_bytes(doc)


def test_keys_are_written_in_nfc_unless_nfc_would_merge_two():
    doc = tla.read(EMPTY)
    composed, decomposed = "Stück", unicodedata.normalize("NFD", "Stück")
    doc.metadata = {decomposed: "1"}
    assert list(tla.loads(tla.canonical_bytes(doc)).metadata) == [composed]
    doc.metadata = {composed: "1", decomposed: "2"}
    again = tla.loads(tla.canonical_bytes(doc))
    assert again.metadata == {composed: "1", decomposed: "2"}


def test_a_timeline_of_an_unknown_kind_without_raw_is_written_whole():
    doc = tla.read(EMPTY)
    timeline = tla.Timeline(id=tla.new_id(), kind=tla.UnknownKind("Lyrics"), ordinal=1)
    doc.timelines[timeline.id] = timeline
    again = tla.loads(tla.canonical_bytes(doc)).timelines[timeline.id]
    assert again.raw == {
        "kind": "Lyrics",
        "name": "",
        "ordinal": 1,
        "metadata": {},
        "components": {},
    }


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


def test_entries_are_read_in_id_order():
    content = json.loads(EVERY_KIND.read_bytes())
    content["timelines"] = dict(reversed(content["timelines"].items()))
    for timeline in content["timelines"].values():
        timeline["components"] = dict(reversed(timeline["components"].items()))
    doc = tla.loads(json.dumps(content).encode())
    assert list(doc.timelines) == sorted(doc.timelines)
    for timeline in doc.timelines.values():
        assert list(timeline.components) == sorted(timeline.components)


def edited(change):
    content = json.loads(UNKNOWN.read_bytes())
    change(content)
    return json.dumps(content).encode()


def first(content, key):
    return next(iter(content[key].values()))


@pytest.mark.parametrize(
    "change, place",
    [
        (lambda c: c.pop("document_id"), "/document_id"),
        (lambda c: c.update(media=[]), "/media"),
        (lambda c: c["media"].pop("length"), "/media/length"),
        (lambda c: c.update(metadata=["title"]), "/metadata"),
        (lambda c: c.update(timelines=[]), "/timelines"),
        (lambda c: c.update(scores={}), "/scores"),
        (lambda c: first(c, "timelines").update(kind=1), "/timelines/{t}/kind"),
        (lambda c: first(c, "timelines").pop("ordinal"), "/timelines/{t}/ordinal"),
        (
            lambda c: first(c, "timelines").update(components=[]),
            "/timelines/{t}/components",
        ),
        (
            lambda c: first(c, "timelines").update(metadata=""),
            "/timelines/{t}/metadata",
        ),
        (
            lambda c: first(first(c, "timelines"), "components").pop("kind"),
            "/timelines/{t}/components/{c}/kind",
        ),
        (
            lambda c: first(first(c, "timelines"), "components").update(metadata=[]),
            "/timelines/{t}/components/{c}/metadata",
        ),
        (lambda c: c["scores"][0].pop("id"), "/scores/0/id"),
        (lambda c: c["scores"][0].update(format=None), "/scores/0/format"),
        (lambda c: c["scores"][0].update(content="<mei/>"), "/scores/0/content"),
        (lambda c: c["scores"][0]["content"].append(1), "/scores/0/content/2"),
    ],
)
def test_structure_the_reader_needs_is_refused_with_its_place(change, place):
    content = json.loads(UNKNOWN.read_bytes())
    timeline_id = next(iter(content["timelines"]))
    component_id = next(iter(content["timelines"][timeline_id]["components"]))
    with pytest.raises(tla.UnreadableFile) as error:
        tla.loads(edited(change))
    assert error.value.place == place.format(t=timeline_id, c=component_id)


def test_two_scores_with_one_id_are_refused():
    # Rather than keeping one, and losing the other on the next save.
    content = json.loads(UNKNOWN.read_bytes())
    content["scores"].append({**content["scores"][0], "content": ["<other/>", ""]})
    with pytest.raises(tla.UnreadableFile) as error:
        tla.loads(json.dumps(content).encode())
    assert error.value.place == "/scores/1/id"
    assert "two scores have the id" in error.value.message


def test_a_marks_defaults_are_filled_in_except_those_from_other_marks():
    # A mark's number, label and source depend on the marks before it: the
    # measure table resolves them.
    beats = named(tla.read(EVERY_KIND), "Beats")
    flags = {"force_display": False, "cadenza": False, "restart": False}
    assert nth(beats, 0).attrs == {
        "time": 0.0,
        "measure": {"number": 0, **flags},
        "beat_unit": {"denominator": 4, "units": "1", "assumed": False},
    }
    assert nth(beats, 1).attrs == {"time": 1.0, "measure": flags}
    assert nth(beats, 1).metadata == {"tags": ["check"]}
    assert nth(beats, 2).attrs == {"time": 2.0}
    assert nth(beats, 4).attrs["measure"] == {
        **flags,
        "label": "2a",
        "force_display": True,
    }


def test_a_range_rows_defaults_are_filled_in():
    texture = named(tla.read(EVERY_KIND), "Texture")
    assert texture.attrs["rows"] == [
        {"id": "aZ3k9P", "name": "Mão direita", "color": None, "height": None},
        {"id": "Qm7x2L", "name": "Linke Hand", "color": "#e57373", "height": 40},
    ]


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
    assert nth(beats, 0).attrs["measure"] == {
        "number": 1,
        "x_mark": "kept",
        "force_display": False,
        "cadenza": False,
        "restart": False,
    }
    assert nth(beats, 0).attrs["beat_unit"] == {
        "denominator": 4,
        "units": "1",
        "x_unit": 0,
        "assumed": False,
    }
    marker, other = markers.components.values()
    assert marker.extra == {
        "Y": True,
        "x_component": {"b": 1, "a": [2, {"d": 3, "c": 4}]},
    }
    assert other.kind == tla.UnknownKind("marker")
    assert (other.attrs, other.extra) == ({}, {"label": "spelled otherwise", "time": 2})
    assert rows.attrs["rows"] == [
        {"id": "aZ3k9P", "name": "Row", "x_row": "kept", "color": None, "height": None}
    ]
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


# The modules


def test_the_functions_dont_hide_the_modules_they_come_from():
    # `import tilia_core.tla.reader as m` gets the package's attribute, which
    # a function of the same name would replace.
    import tilia_core.tla.reader as reader
    import tilia_core.tla.writer as writer

    assert isinstance(reader, types.ModuleType)
    assert isinstance(writer, types.ModuleType)
    assert (reader.read, reader.loads) == (tla.read, tla.loads)
    assert writer.canonical_bytes is tla.canonical_bytes
