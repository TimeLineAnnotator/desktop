"""The two edits to measure marks FR-081 gives: a deleted downbeat's mark moves
to the next beat, and a measure a person edits gets the source "edited"
(TimeLineAnnotator/project-management#416)."""

import copy
import hashlib
import json
import uuid

import pytest

from tilia_core import tla

BASE_MS = 1_767_225_600_000


def make_id(n):
    bits = int.from_bytes(hashlib.sha256(f"edits:{n}".encode()).digest()[:10], "big")
    rand_a, rand_b = bits >> 68, bits & ((1 << 62) - 1)
    value = (BASE_MS + n) << 80 | 7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


DOCUMENT, BEATS, OTHER = (make_id(n) for n in range(3))
B = [make_id(100 + n) for n in range(20)]


def beat(time, measure=None, beat_unit=None, closing=None):
    value = {"kind": "BEAT"}
    if time is not None:
        value["time"] = time
    for key, item in (
        ("measure", measure),
        ("beat_unit", beat_unit),
        ("closing", closing),
    ):
        if item is not None:
            value[key] = item
    return value


def timeline(beats, **keys):
    return {
        "kind": "Beat",
        "name": "Beats",
        "ordinal": 1,
        "height": 35,
        **keys,
        "components": dict(beats),
    }


def document(beats, **keys):
    content = {
        "app_name": "TiLiA",
        "version": tla.FORMAT_VERSION,
        "document_id": DOCUMENT,
        "time_unit": "seconds",
        "media": {"path": "", "length": None},
        "metadata": {},
        "timelines": {BEATS: timeline(beats, **keys)},
        "scores": [],
    }
    return tla.loads((json.dumps(content, indent=2) + "\n").encode())


def bars():
    """Three bars of two beats: downbeats B[0], B[2], B[4]."""
    return [
        (B[0], beat(0.0, measure={"number": 0, "label": "p", "restart": True})),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={"next": [B[0]]})),
        (B[3], beat(3.0)),
        (B[4], beat(4.0, measure={"next": [B[2], B[4]]})),
        (B[5], beat(5.0)),
    ]


def components(doc):
    return doc.timelines[BEATS].components


def marks(doc):
    return {
        key: c.attrs["measure"]
        for key, c in components(doc).items()
        if isinstance(c.attrs.get("measure"), dict)
    }


def read_back(doc):
    return tla.loads(tla.canonical_bytes(doc))


def rows(doc):
    return [
        (r.id, r.number, r.label, r.beats, r.source)
        for r in doc.timelines[BEATS].measures.rows
    ]


# delete_beat


def test_a_deleted_downbeats_mark_moves_to_the_next_beat_with_its_keys():
    doc = document(bars())
    mark = copy.deepcopy(marks(doc)[B[0]])
    assert mark["number"] == 0 and mark["label"] == "p" and mark["restart"] is True
    tla.delete_beat(doc, BEATS, B[0])
    assert B[0] not in components(doc)
    assert marks(doc)[B[1]] == mark
    assert B[0] not in marks(doc)


def test_a_next_that_named_the_deleted_downbeat_follows():
    doc = document(bars())
    mark = copy.deepcopy(marks(doc)[B[2]])
    tla.delete_beat(doc, BEATS, B[2])
    assert marks(doc)[B[3]] == mark
    assert mark["next"] == [B[0]]
    assert marks(doc)[B[0]]["restart"] is True
    assert marks(doc)[B[4]]["next"] == [B[3], B[4]]


def test_a_next_in_the_moved_mark_itself_follows():
    beats = bars()
    beats[2] = (B[2], beat(2.0, measure={"next": [B[2], B[4]]}))
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[2])
    assert marks(doc)[B[3]]["next"] == [B[3], B[4]]


def test_the_table_after_a_deleted_downbeat_has_the_measure_on_the_next_beat():
    doc = document(bars())
    tla.delete_beat(doc, BEATS, B[2])
    assert [r.id for r in doc.timelines[BEATS].measures.rows] == [B[0], B[3], B[4]]
    assert doc.timelines[BEATS].measures.rows[0].beats == [B[0], B[1]]


def test_the_table_read_back_from_the_written_file_agrees():
    doc = document(bars())
    tla.delete_beat(doc, BEATS, B[2])
    assert rows(read_back(doc)) == rows(doc)
    assert marks(read_back(doc)) == marks(doc)


def test_an_ordinary_beat_is_deleted_and_no_mark_or_next_changes():
    doc = document(bars())
    before = copy.deepcopy(marks(doc))
    tla.delete_beat(doc, BEATS, B[1])
    assert B[1] not in components(doc)
    assert marks(doc) == before


def test_the_next_beat_is_the_next_in_time_not_in_id_order():
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[5], beat(1.0)),
        (B[1], beat(2.0)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[0])
    assert B[5] in marks(doc)


def test_a_deleted_last_beat_that_is_a_downbeat_is_refused_and_nothing_changes():
    doc = document([(B[0], beat(0.0, measure={})), (B[1], beat(1.0, measure={}))])
    before = copy.deepcopy(components(doc))
    with pytest.raises(tla.CantMoveMark):
        tla.delete_beat(doc, BEATS, B[1])
    assert components(doc) == before


def test_a_next_beat_that_has_a_mark_is_refused_and_nothing_changes():
    doc = document(
        [(B[0], beat(0.0, measure={})), (B[1], beat(1.0, measure={"number": 5}))]
    )
    before = copy.deepcopy(components(doc))
    with pytest.raises(tla.CantMoveMark):
        tla.delete_beat(doc, BEATS, B[0])
    assert components(doc) == before


def test_a_closing_tap_as_the_next_beat_is_refused_and_nothing_changes():
    doc = document([(B[0], beat(0.0, measure={})), (B[1], beat(1.0, closing=True))])
    before = copy.deepcopy(components(doc))
    with pytest.raises(tla.CantMoveMark):
        tla.delete_beat(doc, BEATS, B[0])
    assert components(doc) == before


def test_a_next_beat_without_a_time_is_refused():
    doc = document([(B[0], beat(0.0, measure={})), (B[1], beat(None))])
    with pytest.raises(tla.CantMoveMark):
        tla.delete_beat(doc, BEATS, B[0])


def test_a_downbeat_with_a_stated_beat_unit_is_refused():
    unit = {"denominator": 8, "units": "3"}
    doc = document([(B[0], beat(0.0, measure={}, beat_unit=unit)), (B[1], beat(1.0))])
    with pytest.raises(tla.CantMoveMark):
        tla.delete_beat(doc, BEATS, B[0])


def test_the_first_beats_assumed_default_unit_does_not_stop_its_deletion():
    unit = {"denominator": 4, "units": "1", "assumed": True}
    doc = document([(B[0], beat(0.0, measure={}, beat_unit=unit)), (B[1], beat(1.0))])
    tla.delete_beat(doc, BEATS, B[0])
    assert B[1] in marks(doc)


def test_a_closing_tap_with_a_mark_is_deleted_like_any_beat():
    doc = document(
        [(B[0], beat(0.0, measure={})), (B[1], beat(1.0, measure={}, closing=True))]
    )
    tla.delete_beat(doc, BEATS, B[1])
    assert B[1] not in components(doc)


def test_an_unknown_beat_or_timeline_raises_a_key_error():
    doc = document(bars())
    with pytest.raises(KeyError):
        tla.delete_beat(doc, BEATS, make_id(999))
    with pytest.raises(KeyError):
        tla.delete_beat(doc, make_id(998), B[0])


# mark_edited and mark_moved


def test_mark_edited_sets_edited_on_a_measure_of_another_source():
    doc = document(bars(), measure_source="import")
    tla.mark_edited(doc, BEATS, [B[2]])
    assert marks(doc)[B[2]]["source"] == "edited"
    assert "source" not in marks(doc)[B[4]]
    assert {r.id: r.source for r in doc.timelines[BEATS].measures.rows}[
        B[2]
    ] == "edited"


def test_mark_edited_leaves_a_tapped_measure():
    doc = document(bars(), measure_source="tapped")
    tla.mark_edited(doc, BEATS, [B[2]])
    assert "source" not in marks(doc)[B[2]]


def test_mark_edited_leaves_a_mark_whose_own_source_is_tapped():
    beats = bars()
    beats[2] = (B[2], beat(2.0, measure={"source": "tapped"}))
    doc = document(beats, measure_source="import")
    tla.mark_edited(doc, BEATS, [B[2]])
    assert marks(doc)[B[2]]["source"] == "tapped"


def test_mark_edited_overrides_a_marks_own_source_that_is_not_tapped():
    beats = bars()
    beats[2] = (B[2], beat(2.0, measure={"source": "score"}))
    doc = document(beats, measure_source="tapped")
    tla.mark_edited(doc, BEATS, [B[2]])
    assert marks(doc)[B[2]]["source"] == "edited"


def test_mark_edited_writes_nothing_when_the_table_already_says_edited():
    doc = document(bars(), measure_source="edited")
    tla.mark_edited(doc, BEATS, [B[2]])
    assert "source" not in marks(doc)[B[2]]


def test_mark_edited_twice_changes_nothing_more():
    doc = document(bars(), measure_source="unknown")
    tla.mark_edited(doc, BEATS, [B[2]])
    once = copy.deepcopy(marks(doc))
    tla.mark_edited(doc, BEATS, [B[2]])
    assert marks(doc) == once


def test_mark_edited_refuses_an_id_that_starts_no_measure_and_changes_nothing():
    doc = document(bars(), measure_source="import")
    with pytest.raises(ValueError):
        tla.mark_edited(doc, BEATS, [B[2], B[3]])
    assert "source" not in marks(doc)[B[2]]


def test_mark_moved_marks_the_measure_and_the_one_before():
    doc = document(bars(), measure_source="import")
    tla.mark_moved(doc, BEATS, B[2])
    assert marks(doc)[B[0]]["source"] == "edited"
    assert marks(doc)[B[2]]["source"] == "edited"
    assert "source" not in marks(doc)[B[4]]


def test_mark_moved_on_the_first_measure_marks_only_it():
    doc = document(bars(), measure_source="import")
    tla.mark_moved(doc, BEATS, B[0])
    assert marks(doc)[B[0]]["source"] == "edited"
    assert "source" not in marks(doc)[B[2]]


def test_mark_moved_leaves_a_tapped_neighbour():
    beats = bars()
    beats[0] = (B[0], beat(0.0, measure={"source": "tapped"}))
    doc = document(beats, measure_source="import")
    tla.mark_moved(doc, BEATS, B[2])
    assert marks(doc)[B[0]]["source"] == "tapped"
    assert marks(doc)[B[2]]["source"] == "edited"


def test_the_edited_source_is_written_and_read_back():
    doc = document(bars(), measure_source="import")
    tla.mark_moved(doc, BEATS, B[2])
    again = read_back(doc)
    assert marks(again) == marks(doc)
    assert rows(again) == rows(doc)
    assert [r[4] for r in rows(again)] == ["edited", "edited", "import"]
