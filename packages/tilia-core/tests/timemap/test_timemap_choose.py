import dataclasses
import logging

import pytest

import tilia_core.timemap as timemap
from docs import beat_timeline, document, pickup_piece
from tilia_core import tla
from tilia_core.timemap import (
    TimeMapFound,
    find_time_map,
    measure_rows,
    time_map_for,
    time_map_of,
)
from tilia_core.timemap.timemap import FOLDED


def _beats(
    ordinal: int, role: str | None = None, *, last: int = 3, id: str | None = None
) -> tla.Timeline:
    """2/4, a beat every second from 0 to `last`."""
    return beat_timeline(
        [
            {"time": float(t), "measure": {} if t % 2 == 0 else None}
            for t in range(last + 1)
        ],
        id=id,
        ordinal=ordinal,
        role=role,
    )


def _other(kind: str, ordinal: int, **kwargs) -> tla.Timeline:
    return tla.Timeline(id=tla.new_id(), kind=kind, ordinal=ordinal, **kwargs)


def _folded(ordinal: int = 1, role: str | None = None) -> tla.Timeline:
    timeline = _beats(ordinal, role)
    timeline.measures.rows[1].next = [timeline.measures.rows[0].id]
    return timeline


def test_the_timeline_with_the_role_is_the_time_map():
    # Spec, US4 scenario 1.
    first, second = _beats(1), _beats(2, role="time_map")

    found = find_time_map(document(first, second))

    assert found.timeline_id == second.id
    assert found.time_map is not None
    assert found.time_map.timeline_id == second.id
    assert not found.guessed and not found.time_map.guessed
    assert found.reason is None and found.warnings == ()


def test_without_the_role_the_first_beat_timeline_by_ordinal_is_guessed():
    # Spec, US4 scenario 2: by ordinal, not by the order of the file; other
    # kinds don't count.
    markers = _other("marker", 1)
    later, earlier = _beats(5), _beats(3)

    found = find_time_map(document(markers, later, earlier))

    assert found.timeline_id == earlier.id
    assert found.time_map.timeline_id == earlier.id
    assert found.guessed and found.time_map.guessed
    assert found.reason is None and found.warnings == ()


@pytest.mark.parametrize(
    "claimants, warning",
    [
        (
            2,
            "timelines B and C claim the role time_map; "
            "B, the first by ordinal, is used",
        ),
        (
            3,
            "timelines A, B and C claim the role time_map; "
            "A, the first by ordinal, is used",
        ),
    ],
)
def test_when_several_claim_the_role_the_first_by_ordinal_wins(
    claimants, warning, caplog
):
    # Spec, US4 scenario 3: one warning, however many claim it, naming them in
    # ordinal order; returned and logged (TimeLineAnnotator/project-management#13
    # (the measure table)).
    unclaimed = _beats(1)
    claiming = [_beats(10 - j, role="time_map", id="CBA"[j]) for j in range(claimants)]

    with caplog.at_level(logging.WARNING):
        found = find_time_map(document(unclaimed, *claiming))

    assert found.timeline_id == claiming[-1].id
    assert found.time_map.timeline_id == claiming[-1].id
    assert not found.guessed
    assert found.warnings == (warning,)
    (record,) = caplog.records
    assert record.name == "tilia_core.timemap"
    assert record.getMessage() == f"{found.warnings[0]}."


def test_the_callers_roles_count_not_only_the_files():
    # Spec, US4 scenario 4: the roles WP12 resolved from the file and the manifest.
    in_file, in_manifest = _beats(1, role="time_map"), _beats(2)
    doc = document(in_file, in_manifest)
    roles = {in_file.id: None, in_manifest.id: "time_map"}

    found = find_time_map(doc, roles)

    assert found.timeline_id == in_manifest.id and not found.guessed
    assert found.warnings == ()
    assert time_map_of(doc, roles).timeline_id == in_manifest.id
    assert time_map_of(doc).timeline_id == in_file.id


@pytest.mark.parametrize("roles", [{}, "none for each"])
def test_the_callers_roles_replace_the_files(roles):
    first, second = _beats(1), _beats(2, role="time_map")
    if roles == "none for each":
        roles = {first.id: None, second.id: None}

    found = find_time_map(document(first, second), roles)

    assert found.timeline_id == first.id and found.guessed


def test_only_a_beat_timeline_can_have_the_role():
    markers = _other("marker", 1, metadata={"role": "time_map"})
    beats = _beats(2)

    for roles in (None, {markers.id: "time_map"}):
        found = find_time_map(document(markers, beats), roles)

        assert found.timeline_id == beats.id and found.guessed


@pytest.mark.parametrize(
    "role, claims",
    [(["time_map"], True), (["analysis", "time_map"], True), (["analysis"], False)],
)
def test_a_role_list_that_holds_time_map_claims_it(role, claims):
    # Metadata values may be lists (TimeLineAnnotator/project-management#13
    # (the measure table)).
    first, listed = _beats(1), _beats(2)
    listed.metadata["role"] = role

    found = find_time_map(document(first, listed))

    assert found.timeline_id == (listed.id if claims else first.id)
    assert found.guessed is not claims


@pytest.mark.parametrize("ordinal", [None, "1", 1.5, float("nan"), True, [1]])
def test_an_ordinal_that_isnt_a_whole_number_sorts_after_the_others(ordinal):
    # Nothing raises while the reader lets one through
    # (TimeLineAnnotator/project-management#7 (format in the core)).
    odd, other = _beats(1), _beats(3)
    odd.ordinal = ordinal

    found = find_time_map(document(odd, other))

    assert found.timeline_id == other.id and found.guessed


def test_a_whole_ordinal_written_as_a_float_sorts_by_its_value():
    two, three = _beats(1), _beats(3)
    two.ordinal = 2.0

    assert find_time_map(document(three, two)).timeline_id == two.id


def test_a_timeline_that_names_a_beat_timeline_gets_its_table_and_time_map():
    # Spec, US4 scenario 5: a score timeline names its table (WP3's FR-133).
    default, named = _beats(1, role="time_map"), _beats(2, last=7)
    score = _other("score", 3, attrs={"measure_table": named.id})
    doc = document(default, named, score)

    time_map = time_map_for(doc, score.attrs["measure_table"])
    rows = measure_rows(doc, score.attrs["measure_table"])

    assert time_map.timeline_id == named.id and not time_map.guessed
    assert [row.number for row in rows] == [1, 2, 3, 4]
    assert rows == time_map.measure_rows()
    assert find_time_map(doc).timeline_id == default.id


def _one_beat(**kwargs) -> tla.Timeline:
    return beat_timeline([{"time": 0.0, "measure": {}}], **kwargs)


def _same_time(**kwargs) -> tla.Timeline:
    return beat_timeline(
        [{"time": 0.0, "measure": {}}, {"time": 0.0}, {"time": 1.0}], **kwargs
    )


def _out_of_order(**kwargs) -> tla.Timeline:
    return beat_timeline(
        [{"time": 0.0, "measure": {}}, {"time": 2.0, "measure": {}}, {"time": 1.0}],
        **kwargs,
    )


@pytest.mark.parametrize(
    "make, reason",
    [
        (_one_beat, "fewer than two beats"),
        (_same_time, "two beats at the same time (0.0)"),
        (_folded, FOLDED),
    ],
)
@pytest.mark.parametrize("role", ["time_map", None])
def test_no_other_timeline_stands_in_for_one_without_a_time_map(make, reason, role):
    # Spec, US4 scenario 6, and FR-003: the file has no bars, and says why.
    chosen, other = make(ordinal=1, role=role), _beats(2)
    doc = document(chosen, other)

    found = find_time_map(doc)

    assert found.time_map is None
    assert found.timeline_id == chosen.id
    assert found.guessed is (role is None)
    assert found.reason == reason
    assert found.warnings == ()
    assert time_map_of(doc) is None


def test_a_document_without_beat_timelines_has_no_time_map(caplog):
    for doc in (document(), document(_other("marker", 1), _other("hierarchy", 2))):
        found = find_time_map(doc)

        assert found == TimeMapFound(
            time_map=None, timeline_id=None, guessed=False, reason=None, warnings=()
        )
        assert time_map_of(doc) is None
    assert not caplog.records


def test_found_is_frozen_and_hashes():
    found = find_time_map(document(*(_beats(j, role="time_map") for j in (1, 2))))

    with pytest.raises(dataclasses.FrozenInstanceError):
        found.guessed = False  # type: ignore[misc]
    assert isinstance(found.warnings, tuple)
    hash(found)


@pytest.mark.parametrize("media_length", [19.5, 20.0])
def test_the_last_beat_at_or_after_the_end_of_the_media_is_returned_and_logged(
    media_length, caplog
):
    # FR-082: returned, and logged once with the timeline's id. The index calls
    # find_time_map once when it reads a file.
    timeline = pickup_piece()  # the last beat at 20 s
    doc = document(timeline, media_length=media_length)

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.time_map.end == 21.0
    (warning,) = found.warnings
    assert warning == (
        f"Timeline {timeline.id}: the last beat (20.0) is at or after the end of "
        f"the media ({media_length}); the last measure ends one beat after it"
    )
    (record,) = caplog.records
    assert record.name == "tilia_core.timemap"
    assert record.levelno == logging.WARNING
    assert timeline.id in record.getMessage()
    assert warning in record.getMessage()


def test_the_warnings_come_in_the_order_they_were_found():
    # The claim first, then each timeline past the media, by ordinal.
    later = _beats(2, role="time_map", id="late")
    earlier = _beats(1, role="time_map", id="early")

    found = find_time_map(document(later, earlier, media_length=2.0))

    assert len(found.warnings) == 3
    assert found.warnings[0] == (
        "timelines early and late claim the role time_map; "
        "early, the first by ordinal, is used"
    )
    assert found.warnings[1].startswith(f"Timeline {earlier.id}: the last beat (3.0)")
    assert found.warnings[2].startswith(f"Timeline {later.id}: the last beat (3.0)")


def test_every_beat_timeline_past_the_media_is_warned_about(caplog):
    # The tables a score or an import names too, once for each call of
    # find_time_map (TimeLineAnnotator/project-management#13 (the measure
    # table)). A table without rows has no closing barline.
    default, named = _beats(1, role="time_map"), _beats(2, last=7)
    timeless = _beats(3, last=7)
    timeless.components[timeless.measures.rows[0].beats[1]].attrs["time"] = None
    doc = document(default, named, timeless, media_length=5.0)

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.timeline_id == default.id
    (warning,) = found.warnings
    assert warning.startswith(f"Timeline {named.id}: the last beat (7.0)")
    (record,) = caplog.records
    assert record.getMessage() == f"{warning}."


@pytest.mark.parametrize(
    "media_length, time_unit",
    [(None, "seconds"), (20.4, "seconds"), (30.0, "seconds"), (19.5, "quarters")],
)
def test_no_media_warning_when_the_media_lasts_past_the_last_beat(
    media_length, time_unit, caplog
):
    # A quarters file's times aren't in the media's seconds.
    doc = document(pickup_piece(), media_length=media_length, time_unit=time_unit)

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.time_map is not None and found.warnings == ()
    assert not caplog.records


@pytest.mark.parametrize(
    "media_length",
    [
        "20",
        True,
        float("nan"),
        float("inf"),
        pytest.param(10**400, id="10**400"),
        0,
        0.0,
        -5.0,
        [19.5],
    ],
)
def test_a_media_length_the_format_doesnt_allow_is_no_length(media_length, caplog):
    # The schema allows a number above zero, or null; the reader doesn't check.
    # No cap on the closing barline, no warning, and nothing raises. 10**400
    # is a whole number too large for a float.
    timeline = pickup_piece()
    doc = document(timeline, media_length=media_length)

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)
        rows = measure_rows(doc, timeline.id)

    assert found.time_map.end == 21.0 and rows[-1].end == 21.0
    assert found.warnings == ()
    assert not caplog.records


def test_a_media_length_too_large_for_a_float_read_from_a_file_is_no_length(caplog):
    # JSON reads a whole number of any size as an int, and the reader keeps
    # it, while it refuses 1e999, which JSON reads as a float.
    data = tla.canonical_bytes(document(pickup_piece(), media_length=20.4))
    assert data.count(b'"length": 20.4') == 1
    doc = tla.loads(data.replace(b'"length": 20.4', b'"length": 1' + b"0" * 400))
    assert doc.media_length == 10**400

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.warnings == ()
    assert not caplog.records


def test_a_whole_number_media_length_caps_and_warns():
    # JSON reads "length": 7 as an int, which the format allows. One measure of
    # four beats, every 2 s: its closing barline is at 8.
    timeline = beat_timeline(
        [{"time": t, "measure": {} if t == 0.0 else None} for t in (0.0, 2.0, 4.0, 6.0)]
    )

    capped = find_time_map(document(timeline, media_length=7))
    past = find_time_map(document(timeline, media_length=6))

    assert capped.time_map.end == 7 and capped.warnings == ()
    assert past.time_map.end == 8.0
    assert past.warnings == (
        f"Timeline {timeline.id}: the last beat (6.0) is at or after the end of the "
        "media (6); the last measure ends one beat after it",
    )


def test_one_beat_past_the_media_is_warned_about_without_a_gap():
    # Its only measure ends on the beat: there is no gap after it.
    one = beat_timeline([{"time": 5.0, "measure": {}}])

    found = find_time_map(document(one, media_length=4.0))

    assert found.reason == "fewer than two beats"
    assert found.warnings == (
        f"Timeline {one.id}: the last beat (5.0) is at or after the end of the "
        "media (4.0)",
    )


@pytest.mark.parametrize("make", [_same_time, _out_of_order])
def test_a_table_out_of_time_order_gets_no_media_warning(make, caplog):
    # It has no rows, so no closing barline.
    timeline = make()
    doc = document(timeline, media_length=0.5)

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.time_map is None and found.warnings == ()
    assert not caplog.records


def test_a_folded_table_past_the_media_is_warned_about(caplog):
    # It has no time map, but its rows have a closing barline (FR-013).
    folded = _folded()
    doc = document(folded, media_length=2.0)

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.time_map is None and found.reason == FOLDED
    (warning,) = found.warnings
    assert warning.startswith(f"Timeline {folded.id}: the last beat (3.0)")
    assert len(caplog.records) == 1


def test_tables_and_named_time_maps_log_nothing_about_the_media(caplog):
    # FR-082: only find_time_map logs it, so a table built many times doesn't.
    timeline = pickup_piece()
    doc = document(timeline, media_length=19.5)

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert time_map_for(doc, timeline.id) is not None
            assert measure_rows(doc, timeline.id)

    assert not caplog.records


def test_measure_rows_of_a_folded_table():
    # FR-013: no time map, but the rows are computed, in the timeline's order.
    timeline = _folded()
    doc = document(timeline)

    rows = measure_rows(doc, timeline.id)

    assert time_map_for(doc, timeline.id) is None
    assert [(row.number, row.start, row.end, row.folded) for row in rows] == [
        (1, 0.0, 2.0, True),
        (2, 2.0, 4.0, True),
    ]


def test_measure_rows_give_none_while_a_beat_has_no_usable_time():
    timeline = _beats(1)
    beat = timeline.components[timeline.measures.rows[1].beats[1]]
    beat.attrs["time"] = float("nan")

    assert measure_rows(document(timeline), timeline.id) == []


def test_a_beat_time_too_large_for_a_float_is_no_time(caplog):
    # TimeLineAnnotator/project-management#319 (a beat time too large for a
    # float): JSON reads a whole number of any size as an int, which a float
    # can't hold. In a timeline that isn't the time map, it doesn't stop the
    # document's: that timeline alone has no rows and no time map.
    chosen, other = _beats(1, role="time_map"), _beats(2)
    last = other.measures.rows[-1].beats[-1]
    other.components[last].attrs["time"] = 10**400
    doc = document(chosen, other, media_length=2.0)

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.timeline_id == chosen.id and found.time_map is not None
    (warning,) = found.warnings
    assert warning.startswith(f"Timeline {chosen.id}: the last beat (3.0)")
    assert len(caplog.records) == 1
    assert measure_rows(doc, other.id) == []
    assert time_map_for(doc, other.id) is None
    assert find_time_map(document(other)).reason == "a beat without a time (measure 2)"


@pytest.mark.parametrize("make", [_same_time, _out_of_order])
def test_measure_rows_give_none_while_beats_are_out_of_order_or_share_a_time(make):
    # No measure that ends before it starts
    # (TimeLineAnnotator/project-management#13 (the measure table)).
    timeline = make()

    assert measure_rows(document(timeline), timeline.id) == []


def test_measure_rows_of_a_timeline_that_is_not_a_beat_timeline():
    # Even one that carries a table, as only a beat timeline should.
    beats, markers = _beats(1), _other("marker", 2)
    with_table = dataclasses.replace(_beats(3), kind="marker")
    doc = document(beats, markers, with_table)

    assert measure_rows(doc, markers.id) == []
    assert measure_rows(doc, with_table.id) == []
    assert time_map_for(doc, with_table.id) is None
    assert measure_rows(doc, tla.new_id()) == []
    assert len(measure_rows(doc, beats.id)) == 2


def test_the_package_exports_the_contracts_names_that_exist():
    assert sorted(timemap.__all__) == [
        "MeasureRow",
        "Positions",
        "TimeMap",
        "TimeMapFound",
        "find_time_map",
        "measure_rows",
        "time_map_for",
        "time_map_of",
    ]
    for name in timemap.__all__:
        assert getattr(timemap, name) is not None
