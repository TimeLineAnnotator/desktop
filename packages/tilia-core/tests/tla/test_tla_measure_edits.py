"""The two edits to measure marks FR-081 gives: a deleted downbeat's mark moves
to the next beat, and a measure a person edits gets the source "edited"
(TimeLineAnnotator/project-management#416; the cases of
TimeLineAnnotator/project-management#512 as contracts/layout.md gives them)."""

import copy
import hashlib
import json
import uuid

import pytest

from tilia_core import timemap, tla

BASE_MS = 1_767_225_600_000


def make_id(n):
    bits = int.from_bytes(hashlib.sha256(f"edits:{n}".encode()).digest()[:10], "big")
    rand_a, rand_b = bits >> 68, bits & ((1 << 62) - 1)
    value = (BASE_MS + n) << 80 | 7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


DOCUMENT, BEATS, OTHER = (make_id(n) for n in range(3))
B = [make_id(100 + n) for n in range(20)]

EIGHTHS = {"denominator": 8, "units": "3"}
QUARTERS = {"denominator": 4, "units": "1"}
DEFAULT = {"denominator": 4, "units": "1", "assumed": True}


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


def document(beats, length=None, **keys):
    content = {
        "app_name": "TiLiA",
        "version": tla.FORMAT_VERSION,
        "document_id": DOCUMENT,
        "time_unit": "seconds",
        "media": {"path": "", "length": length},
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


def one_beat_bars(*marks):
    """A bar of one beat for each mark, B[0], B[1], …, at 0.0, 1.0, …"""
    return [(B[n], beat(float(n), measure=mark)) for n, mark in enumerate(marks)]


def components(doc):
    return doc.timelines[BEATS].components


def marks(doc):
    return {
        key: c.attrs["measure"]
        for key, c in components(doc).items()
        if isinstance(c.attrs.get("measure"), dict)
    }


def written(doc, key="measure"):
    """The beats' marks, or another key, as the file writes them: without
    the keys at their default."""
    beats = json.loads(tla.canonical_bytes(doc))["timelines"][BEATS]["components"]
    return {beat_id: c[key] for beat_id, c in beats.items() if key in c}


def units(doc):
    return written(doc, "beat_unit")


def read_back(doc):
    return tla.loads(tla.canonical_bytes(doc))


def written_twice(doc, path):
    """`doc` written, read and written again: the second write's bytes are the
    first's. Gives the document read."""
    tla.write(path, doc)
    first = path.read_bytes()
    again = tla.read(path)
    tla.write(path, again)
    assert path.read_bytes() == first
    return again


def rows(doc):
    return [
        (r.id, r.number, r.label, r.beats, r.source)
        for r in doc.timelines[BEATS].measures.rows
    ]


def numbers(doc):
    return [r.label for r in doc.timelines[BEATS].measures.rows]


def readings(doc):
    """Each bar's time signature, and whether it is assumed, as the time map
    reads them."""
    return {
        r.id: (r.time_signature, r.assumed) for r in timemap.measure_rows(doc, BEATS)
    }


def sources(doc):
    return {key: mark.get("source") for key, mark in marks(doc).items()}


# delete_beat: the mark moves to the next beat


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


# delete_beat: the next beat has a mark of its own


def test_a_next_beat_with_a_mark_keeps_its_own_and_the_deleted_mark_goes():
    deleted = {
        "label": "16a",
        "force_display": True,
        "cadenza": True,
        "next": [B[2]],
        "source": "score",
    }
    doc = document(one_beat_bars({"number": 15}, deleted, {"label": "x"}, {}))
    tla.delete_beat(doc, BEATS, B[1])
    assert written(doc) == {B[0]: {"number": 15}, B[2]: {"label": "x"}, B[3]: {}}


def test_every_next_naming_the_deleted_beat_follows_to_the_next_beats_mark():
    doc = document(one_beat_bars({"next": [B[1], B[2]]}, {}, {"next": [B[1]]}))
    tla.delete_beat(doc, BEATS, B[1])
    assert written(doc) == {B[0]: {"next": [B[2], B[2]]}, B[2]: {"next": [B[2]]}}
    assert marks(read_back(doc)) == marks(doc)


def test_the_measures_after_the_one_that_goes_close_up():
    doc = document(one_beat_bars({"number": 15}, {}, {}, {}))
    assert numbers(doc) == ["15", "16", "17", "18"]
    tla.delete_beat(doc, BEATS, B[1])
    assert numbers(doc) == ["15", "16", "17"]


def test_a_later_measure_that_states_its_number_keeps_it():
    doc = document(one_beat_bars({"number": 15}, {}, {}, {"number": 18}))
    tla.delete_beat(doc, BEATS, B[1])
    assert numbers(doc) == ["15", "16", "18"]


def test_a_first_measure_that_goes_takes_its_number_with_it():
    pickup = document(one_beat_bars({"number": 0}, {}, {}))
    tla.delete_beat(pickup, BEATS, B[0])
    assert numbers(pickup) == ["1", "2"]
    fifteen = document(one_beat_bars({"number": 15}, {}, {}))
    tla.delete_beat(fifteen, BEATS, B[0])
    assert numbers(fifteen) == ["1", "2"]


def test_a_restart_moves_and_the_next_beat_states_the_number_it_read():
    pickup = {"number": 0, "label": "p", "restart": True, "force_display": True}
    doc = document(one_beat_bars({"number": 19}, {}, pickup, {}, {}))
    assert numbers(doc) == ["19", "20", "p", "1", "2"]
    tla.delete_beat(doc, BEATS, B[2])
    assert written(doc)[B[3]] == {"number": 1, "restart": True}
    assert numbers(doc) == ["19", "20", "1", "2"]
    assert [r.restart for r in doc.timelines[BEATS].measures.rows] == [
        False,
        False,
        True,
        False,
    ]
    assert rows(read_back(doc)) == rows(doc)


def test_a_restart_without_a_number_gives_the_number_the_next_beat_read():
    doc = document(one_beat_bars({"number": 20}, {"restart": True}, {}))
    tla.delete_beat(doc, BEATS, B[1])
    assert written(doc)[B[2]] == {"number": 22, "restart": True}
    assert numbers(doc) == ["20", "22"]


def test_a_restart_on_a_next_beat_that_states_its_number_keeps_that_number():
    doc = document(
        one_beat_bars({}, {"number": 0, "restart": True}, {"number": 5, "label": "5a"})
    )
    tla.delete_beat(doc, BEATS, B[1])
    assert written(doc)[B[2]] == {"number": 5, "label": "5a", "restart": True}


# delete_beat: no next beat, or a closing tap or a beat without a time next


def test_a_last_downbeat_goes_and_every_next_drops_it():
    beats = [
        (B[0], beat(0.0, measure={"next": [B[2], B[0]]})),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={"next": [B[0]]})),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[2])
    assert written(doc) == {B[0]: {"next": [B[0]]}}
    assert [r.id for r in doc.timelines[BEATS].measures.rows] == [B[0]]


def test_a_next_list_left_empty_is_left_out():
    beats = [
        (B[0], beat(0.0, measure={"next": [B[2]]})),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={})),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[2])
    assert written(doc) == {B[0]: {}}
    assert doc.timelines[BEATS].measures.rows[0].next is None
    assert b'"next"' not in tla.canonical_bytes(doc)


def test_the_only_beat_goes_with_its_mark():
    doc = document([(B[0], beat(0.0, measure={"number": 3}))])
    tla.delete_beat(doc, BEATS, B[0])
    assert components(doc) == {}
    assert read_back(doc).timelines[BEATS].measures.rows == []


def test_a_closing_tap_next_takes_no_mark_and_the_mark_goes():
    beats = [
        (B[0], beat(0.0, measure={"next": [B[2]]})),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={"label": "x"})),
        (B[3], beat(3.0, closing=True)),
        (B[4], beat(4.0, measure={"restart": True})),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[2])
    assert written(doc) == {B[0]: {}, B[4]: {"restart": True}}
    assert components(doc)[B[3]].attrs == {"time": 3.0, "closing": True}
    assert rows(read_back(doc)) == rows(doc)


def test_a_closing_tap_next_with_a_mark_of_its_own_keeps_it():
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={"label": "x"})),
        (B[2], beat(2.0, measure={"number": 9}, closing=True)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[1])
    assert written(doc) == {B[0]: {}, B[2]: {"number": 9}}


def test_a_next_beat_without_a_time_takes_no_mark_and_the_mark_goes():
    beats = [
        (B[0], beat(0.0, measure={"next": [B[2]]})),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={"label": "x"})),
        (B[3], beat(None)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[2])
    assert written(doc) == {B[0]: {}}
    assert "measure" not in components(doc)[B[3]].attrs


def p1_beats(*more):
    """A closing tap inside the first measure, then a beat without a mark."""
    return [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, closing=True)),
        (B[2], beat(2.0)),
        *more,
    ]


def test_a_first_downbeat_a_closing_tap_follows_is_refused_and_nothing_changes():
    doc = document(p1_beats((B[3], beat(3.0, measure={}))))
    before = copy.deepcopy(components(doc))
    rows_before = rows(doc)
    with pytest.raises(
        tla.CantDeleteDownbeat, match="Delete the closing tap first"
    ) as error:
        tla.delete_beat(doc, BEATS, B[0])
    assert (error.value.beat_id, error.value.closing_tap_id) == (B[0], B[1])
    assert components(doc) == before
    assert rows(doc) == rows_before


def test_once_the_closing_tap_is_deleted_the_mark_moves_on(tmp_path):
    doc = document(p1_beats((B[3], beat(3.0, measure={}))))
    tla.delete_beat(doc, BEATS, B[1])
    tla.delete_beat(doc, BEATS, B[0])
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again) == {B[2]: {}, B[3]: {}}


def test_a_first_downbeat_with_no_measure_after_it_goes_with_its_mark(tmp_path):
    doc = document(p1_beats())
    tla.delete_beat(doc, BEATS, B[0])
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again) == {}


def test_a_unit_left_on_a_timeline_with_no_mark_is_kept_with_a_warning(tmp_path):
    doc = document(p1_beats()[:2] + [(B[2], beat(2.0, beat_unit=QUARTERS))])
    tla.delete_beat(doc, BEATS, B[0])
    again = written_twice(doc, tmp_path / "f.tla")
    assert units(again) == {B[2]: QUARTERS}
    assert timemap.find_time_map(again).warnings == (
        f"Timeline {BEATS}: beat {B[2]} (2.0) has a beat unit, which starts "
        "nothing: the timeline has no measure marks",
    )


def test_while_a_beat_has_no_time_the_deletion_goes_on(tmp_path):
    doc = document(p1_beats((B[3], beat(3.0, measure={})), (B[4], beat(None))))
    tla.delete_beat(doc, BEATS, B[0])
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again) == {B[3]: {}}


def test_a_later_downbeat_a_closing_tap_follows_goes_with_its_mark(tmp_path):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={})),
        (B[3], beat(3.0, closing=True)),
        (B[4], beat(4.0)),
        (B[5], beat(5.0, measure={})),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[2])
    assert doc.timelines[BEATS].measures.rows[0].beats == [B[0], B[1], B[4]]
    written_twice(doc, tmp_path / "f.tla")


# delete_beat: the downbeat's beat unit


def test_a_downbeats_beat_unit_moves_with_its_mark_and_the_bars_read_as_before():
    beats = [
        (B[0], beat(0.0, measure={}, beat_unit=EIGHTHS)),
        (B[1], beat(1.0)),
        (B[2], beat(2.0)),
        (B[3], beat(3.0, measure={})),
        (B[4], beat(4.0)),
    ]
    doc = document(beats)
    assert readings(doc)[B[3]] == ("6/8", False)
    tla.delete_beat(doc, BEATS, B[0])
    assert units(doc) == {B[1]: EIGHTHS}
    assert readings(doc) == {B[1]: ("6/8", False), B[3]: ("6/8", False)}
    assert readings(read_back(doc)) == readings(doc)


def test_the_unit_moves_to_a_next_beat_with_its_own_mark():
    beats = [
        (B[0], beat(0.0, measure={"number": 0}, beat_unit=EIGHTHS)),
        (B[1], beat(1.0, measure={})),
        (B[2], beat(2.0)),
        (B[3], beat(3.0, measure={})),
        (B[4], beat(4.0)),
    ]
    doc = document(beats)
    before = readings(doc)
    tla.delete_beat(doc, BEATS, B[0])
    assert units(doc) == {B[1]: EIGHTHS}
    assert readings(doc) == {B[1]: before[B[1]], B[3]: before[B[3]]}
    assert readings(doc)[B[1]] == ("6/8", False)


@pytest.mark.parametrize("own_mark", [None, {}], ids=["no mark", "a mark"])
def test_the_unit_is_dropped_when_the_next_beat_states_its_own(own_mark):
    beats = [
        (B[0], beat(0.0, measure={}, beat_unit=EIGHTHS)),
        (B[1], beat(1.0, measure=own_mark, beat_unit=QUARTERS)),
        (B[2], beat(2.0)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[0])
    assert units(doc) == {B[1]: QUARTERS}
    assert readings(doc) == {B[1]: ("2/4", False)}


@pytest.mark.parametrize("after", ["none", "closing tap"])
def test_the_unit_is_dropped_when_the_mark_goes(after):
    beats = [
        (B[0], beat(0.0, measure={}, beat_unit=QUARTERS)),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={}, beat_unit=EIGHTHS)),
    ]
    if after == "closing tap":
        beats.append((B[3], beat(3.0, closing=True)))
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[2])
    assert units(doc) == {B[0]: QUARTERS}


def test_the_first_beats_assumed_default_moves_and_stays_assumed():
    beats = [
        (B[0], beat(0.0, measure={}, beat_unit=DEFAULT)),
        (B[1], beat(1.0)),
        (B[2], beat(2.0)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[0])
    assert units(doc) == {B[1]: DEFAULT}
    assert readings(doc) == {B[1]: ("2/4", True)}
    assert units(read_back(doc)) == units(doc)


@pytest.mark.parametrize("unit", [EIGHTHS, DEFAULT], ids=["stated", "assumed"])
def test_a_dropped_unit_leaves_no_default_and_the_bars_read_it_assumed(unit):
    beats = [
        (B[0], beat(0.0, measure={}, beat_unit=unit)),
        (B[1], beat(1.0, closing=True)),
        (B[2], beat(2.0, measure={"restart": True})),
        (B[3], beat(3.0)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[0])
    assert units(doc) == {}
    assert readings(doc) == {B[2]: ("2/4", True)}
    assert readings(read_back(doc)) == readings(doc)


def test_a_moved_unit_is_dropped_when_the_measure_it_moves_into_states_one():
    beats = [
        (B[0], beat(0.0, measure={"number": 0}, beat_unit=EIGHTHS)),
        (B[1], beat(1.0, measure={})),
        (B[2], beat(2.0, beat_unit=QUARTERS)),
        (B[3], beat(3.0, measure={})),
        (B[4], beat(4.0)),
    ]
    doc = document(beats)
    before = readings(doc)
    tla.delete_beat(doc, BEATS, B[0])
    assert units(doc) == {B[2]: QUARTERS}
    assert readings(doc) == {B[1]: before[B[1]], B[3]: before[B[3]]}
    assert readings(doc)[B[1]] == ("2/4", False)


def test_a_moved_unit_is_dropped_when_the_rest_of_its_measure_states_one():
    beats = [
        (B[0], beat(0.0, measure={}, beat_unit=EIGHTHS)),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, beat_unit=QUARTERS)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[0])
    assert units(doc) == {B[2]: QUARTERS}


def test_an_ordinary_beats_unit_moves_to_its_measures_first_beat():
    beats = [
        (B[0], beat(0.0, measure={}, beat_unit=QUARTERS)),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={})),
        (B[3], beat(3.0, beat_unit=EIGHTHS)),
        (B[4], beat(4.0, measure={})),
        (B[5], beat(5.0)),
    ]
    doc = document(beats)
    assert readings(doc)[B[4]] == ("6/8", False)
    tla.delete_beat(doc, BEATS, B[3])
    assert units(doc) == {B[0]: QUARTERS, B[2]: EIGHTHS}
    assert readings(doc) == {
        B[0]: ("2/4", False),
        B[2]: ("3/8", False),
        B[4]: ("6/8", False),
    }


def test_an_ordinary_beats_unit_is_dropped_when_its_measures_first_beat_has_one():
    beats = [
        (B[0], beat(0.0, measure={}, beat_unit=QUARTERS)),
        (B[1], beat(1.0, beat_unit=EIGHTHS)),
        (B[2], beat(2.0)),
        (B[3], beat(3.0, measure={})),
        (B[4], beat(4.0)),
    ]
    doc = document(beats)
    before = readings(doc)[B[3]]
    tla.delete_beat(doc, BEATS, B[1])
    assert units(doc) == {B[0]: QUARTERS}
    assert readings(doc)[B[3]] == before == ("2/4", False)


# delete_beat: a timeline left with no mark


def test_a_timeline_with_no_mark_at_all_is_read_and_written(tmp_path):
    doc = document([(B[0], beat(0.0)), (B[1], beat(1.0))])
    assert doc.timelines[BEATS].measures.rows == []
    assert timemap.time_map_for(doc, BEATS) is None
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again) == {}


def test_while_a_beat_has_a_mark_the_first_beat_must_have_one():
    with pytest.raises(tla.UnreadableFile, match="has no measure mark"):
        document([(B[0], beat(0.0)), (B[1], beat(1.0, measure={}))])


def test_dropping_the_beat_without_a_time_that_held_the_only_mark(tmp_path):
    # As `tilia migrate --apply` drops beats without a time.
    beats = [(B[0], beat(0.0)), (B[1], beat(1.0)), (B[2], beat(None, measure={}))]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[2], by_person=False)
    again = written_twice(doc, tmp_path / "f.tla")
    assert set(components(again)) == {B[0], B[1]}
    assert written(again) == {}


# delete_beat: the measures it marks "edited"


def test_deleting_an_ordinary_beat_marks_its_measure_edited():
    doc = document(bars(), measure_source="import")
    tla.delete_beat(doc, BEATS, B[3])
    assert sources(doc) == {B[0]: None, B[2]: "edited", B[4]: None}


def test_deleting_a_downbeat_marks_its_moved_measure_and_the_one_before():
    doc = document(bars(), measure_source="import")
    tla.delete_beat(doc, BEATS, B[2])
    assert sources(doc) == {B[0]: "edited", B[3]: "edited", B[4]: None}


def test_when_the_downbeats_measure_is_gone_the_one_before_is_marked():
    beats = one_beat_bars({}, {}, {}, {})
    one_mark = document(beats, measure_source="import")
    tla.delete_beat(one_mark, BEATS, B[2])
    assert sources(one_mark) == {B[0]: None, B[1]: "edited", B[3]: None}
    last = document(beats, measure_source="import")
    tla.delete_beat(last, BEATS, B[3])
    assert sources(last) == {B[0]: None, B[1]: None, B[2]: "edited"}


def test_deleting_a_first_downbeat_whose_next_beat_has_a_mark_marks_none():
    doc = document(one_beat_bars({}, {}), measure_source="import")
    tla.delete_beat(doc, BEATS, B[0])
    assert sources(doc) == {B[1]: None}


def test_a_deletion_leaves_a_tapped_measure_and_an_edited_one():
    beats = bars()
    beats[0] = (B[0], beat(0.0, measure={"source": "tapped"}))
    doc = document(beats, measure_source="import")
    tla.delete_beat(doc, BEATS, B[2])
    assert sources(doc) == {B[0]: "tapped", B[3]: "edited", B[4]: None}
    tapped = document(bars(), measure_source="tapped")
    tla.delete_beat(tapped, BEATS, B[2])
    assert set(sources(tapped).values()) == {None}


@pytest.mark.parametrize("deleted", [1, 2, 4], ids=["beat", "downbeat", "last"])
def test_a_deletion_not_by_a_person_marks_nothing(deleted):
    beats = bars()[:5]
    doc = document(beats, measure_source="import")
    tla.delete_beat(doc, BEATS, B[deleted], by_person=False)
    assert set(sources(doc).values()) == {None}
    assert B[deleted] not in components(doc)
    if deleted == 2:
        assert B[3] in marks(doc)


@pytest.mark.parametrize("by_person", [True, False])
def test_a_beat_without_a_time_is_in_no_measure_and_marks_none(by_person):
    beats = [
        (B[0], beat(0.0, measure={"next": [B[2]]})),
        (B[1], beat(1.0)),
        (B[2], beat(None, measure={})),
    ]
    doc = document(beats, measure_source="import")
    tla.delete_beat(doc, BEATS, B[2], by_person=by_person)
    assert written(doc) == {B[0]: {}}


def test_a_closing_tap_is_no_beat_of_a_measure_and_marks_none():
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, closing=True)),
    ]
    doc = document(beats, measure_source="import")
    tla.delete_beat(doc, BEATS, B[2])
    assert sources(doc) == {B[0]: None}


def test_the_source_a_deletion_sets_is_written_and_read_back():
    doc = document(bars(), measure_source="import")
    tla.delete_beat(doc, BEATS, B[2])
    again = read_back(doc)
    assert marks(again) == marks(doc)
    assert [r[4] for r in rows(again)] == ["edited", "edited", "import"]


# delete_beat and mark_edited: problems the file was read with stay old


@pytest.mark.parametrize("by_person", [True, False])
def test_a_problem_that_moves_with_a_mark_stays_old(tmp_path, by_person):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={"number": -1})),
        (B[2], beat(2.0)),
    ]
    doc = document(beats, measure_source="import")
    assert any("below 0" in w.message for w in doc.warnings)
    tla.delete_beat(doc, BEATS, B[1], by_person=by_person)
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again)[B[2]]["number"] == -1


def test_a_problem_of_the_beat_a_mark_moves_onto_stays_old(tmp_path):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={})),
        (B[2], beat(5.0)),
    ]
    doc = document(beats, length=1.5, measure_source="import")
    tla.delete_beat(doc, BEATS, B[1])
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again) == {B[0]: {"source": "edited"}, B[2]: {"source": "edited"}}


def test_a_problem_between_beats_stays_old_when_a_mark_moves_onto_one(tmp_path):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={})),
        (B[2], beat(2.0)),
        (B[3], beat(2.0)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[1])
    written_twice(doc, tmp_path / "f.tla")


def test_a_beat_a_mark_moves_onto_keeps_its_time_uncompared(tmp_path):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={})),
        (B[2], beat(150.0)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[1])
    doc.media_length = 100.0
    written_twice(doc, tmp_path / "f.tla")


def test_a_problem_on_a_measure_marked_edited_stays_old(tmp_path):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0)),
        (B[2], beat(5.0, measure={})),
        (B[3], beat(6.0)),
    ]
    doc = document(beats, length=1.5, measure_source="import")
    tla.mark_edited(doc, BEATS, [B[2]])
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again)[B[2]] == {"source": "edited"}


def test_a_problem_made_after_the_deletion_is_refused(tmp_path):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={"number": -1})),
        (B[2], beat(2.0)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[1])
    components(doc)[B[2]].attrs["measure"]["number"] = -2
    with pytest.raises(tla.BrokenRules):
        tla.write(tmp_path / "f.tla", doc)


def test_a_problem_the_file_wasnt_read_with_is_refused_where_the_mark_moves(
    tmp_path,
):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={})),
        (B[2], beat(2.0)),
    ]
    doc = document(beats)
    components(doc)[B[1]].attrs["measure"]["number"] = -1
    tla.delete_beat(doc, BEATS, B[1])
    with pytest.raises(tla.BrokenRules):
        tla.write(tmp_path / "f.tla", doc)


def test_a_problem_on_the_measure_before_a_deleted_downbeat_stays_old(tmp_path):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(5.0, measure={})),
        (B[2], beat(6.0)),
        (B[3], beat(7.0, measure={})),
        (B[4], beat(8.0)),
    ]
    doc = document(beats, length=1.5, measure_source="import")
    tla.delete_beat(doc, BEATS, B[3])
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again)[B[1]] == {"source": "edited"}


def test_a_problem_on_a_mark_whose_next_follows_stays_old(tmp_path):
    # The mark naming the deleted downbeat isn't the measure before it.
    beats = [
        (B[0], beat(0.0, measure={"number": -1, "next": [B[4]]})),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={})),
        (B[3], beat(3.0)),
        (B[4], beat(4.0, measure={})),
        (B[5], beat(5.0)),
    ]
    doc = document(beats)
    tla.delete_beat(doc, BEATS, B[4], by_person=False)
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again)[B[0]] == {"number": -1, "next": [B[5]]}


def test_a_problem_naming_a_beat_marked_edited_stays_old(tmp_path):
    # B[1] and B[2] are at one time: the problem is on B[1], and names B[2],
    # the measure before the deleted downbeat, which gets the source "edited".
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0)),
        (B[2], beat(1.0, measure={})),
        (B[3], beat(2.0)),
        (B[4], beat(3.0, measure={})),
        (B[5], beat(4.0)),
    ]
    doc = document(beats, measure_source="import")
    tla.delete_beat(doc, BEATS, B[4])
    again = written_twice(doc, tmp_path / "f.tla")
    assert written(again)[B[2]] == {"source": "edited"}


def test_a_problem_changed_since_reading_is_refused_where_the_mark_moves(tmp_path):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={"number": -1})),
        (B[2], beat(2.0)),
    ]
    doc = document(beats)
    components(doc)[B[1]].attrs["measure"]["number"] = -3
    tla.delete_beat(doc, BEATS, B[1])
    with pytest.raises(tla.BrokenRules):
        tla.write(tmp_path / "f.tla", doc)


def test_a_beat_changed_since_reading_keeps_its_problem_new(tmp_path):
    beats = [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={})),
        (B[2], beat(5.0)),
    ]
    doc = document(beats, length=1.5)
    components(doc)[B[2]].attrs["time"] = 6.0
    tla.delete_beat(doc, BEATS, B[1], by_person=False)
    with pytest.raises(tla.BrokenRules):
        tla.write(tmp_path / "f.tla", doc)


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
