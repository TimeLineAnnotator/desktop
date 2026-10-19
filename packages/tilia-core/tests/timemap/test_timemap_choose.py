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

TWO_CLAIM = "two timelines claim the role time_map; the first by ordinal is used"


def _beats(ordinal: int, role: str | None = None, *, last: int = 3) -> tla.Timeline:
    """2/4, a beat every second from 0 to `last`."""
    return beat_timeline(
        [
            {"time": float(t), "measure": {} if t % 2 == 0 else None}
            for t in range(last + 1)
        ],
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


@pytest.mark.parametrize("claimants", [2, 3])
def test_when_several_claim_the_role_the_first_by_ordinal_wins(claimants):
    # Spec, US4 scenario 3: one warning, however many claim it.
    unclaimed = _beats(1)
    claiming = [_beats(10 - j, role="time_map") for j in range(claimants)]

    found = find_time_map(document(unclaimed, *claiming))

    assert found.timeline_id == claiming[-1].id
    assert found.time_map.timeline_id == claiming[-1].id
    assert not found.guessed
    assert found.warnings == (TWO_CLAIM,)


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
    assert hash(found) == hash(found)


@pytest.mark.parametrize("media_length", [19.5, 20.0])
def test_the_last_beat_at_or_after_the_end_of_the_media_is_warned_once(
    media_length, caplog
):
    # FR-082: returned, and logged with the timeline's id, once per file.
    timeline = pickup_piece()  # the last beat at 20 s
    doc = document(timeline, media_length=media_length)

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.time_map.end == 21.0
    (warning,) = found.warnings
    assert warning == (
        f"the last beat (20.0) is at or after the end of the media ({media_length}); "
        "the last measure ends one gap after it"
    )
    (record,) = caplog.records
    assert record.name == "tilia_core.timemap"
    assert record.levelno == logging.WARNING
    assert timeline.id in record.getMessage()
    assert warning in record.getMessage()


def test_the_warnings_come_in_the_order_they_were_found():
    claiming = [_beats(j, role="time_map") for j in (1, 2)]

    found = find_time_map(document(*claiming, media_length=2.0))

    assert len(found.warnings) == 2
    assert found.warnings[0] == TWO_CLAIM
    assert found.warnings[1].startswith("the last beat (3.0)")


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


def test_no_media_warning_for_a_media_length_that_isnt_a_number(caplog):
    # Like the closing barline, which then keeps the gap: no length, no warning.
    doc = document(pickup_piece(), media_length=float("nan"))

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.time_map.end == 21.0 and found.warnings == ()
    assert not caplog.records


def test_no_media_warning_without_a_time_map(caplog):
    # The table is folded, so it has no closing barline to warn about.
    doc = document(_folded(), media_length=2.0)

    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.time_map is None and found.warnings == ()
    assert not caplog.records


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
