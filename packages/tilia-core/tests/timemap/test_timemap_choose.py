import dataclasses
import json
import logging

import pytest

from docs import (
    beat_timeline,
    closed_piece,
    document,
    pickup_piece,
    read_as_a_file,
    two_movements,
)
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
        f"the media ({media_length}); the last measure ends one gap after it"
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
    # The schema allows a number above zero, or null. Since desktop#744 the
    # reader refuses text and bools, and a file can't hold NaN or infinity, so
    # a file can give only zero or less, or 10**400, a whole number too large
    # for a float; a document made in memory can hold them all. No cap on the
    # closing barline, no warning, and nothing raises.
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
        "media (6); the last measure ends one gap after it",
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


# Closing taps: a warning for each that stands where none may, past the media,
# or with a beat unit (FR-011, Q16).


def _misplaced_warning(timeline: tla.Timeline, tap: str) -> str:
    time = timeline.components[tap].attrs["time"]
    return (
        f"Timeline {timeline.id}: beat {tap} ({time}) is marked closing, but isn't "
        "the last tap of the timeline or of a movement; it is read as an ordinary beat"
    )


def _beat_unit_warning(timeline: tla.Timeline, tap: str) -> str:
    time = timeline.components[tap].attrs["time"]
    return (
        f"Timeline {timeline.id}: the closing tap {tap} ({time}) has a beat unit, "
        "which starts nothing"
    )


def test_a_closing_tap_where_one_may_stand_gets_no_warning(caplog):
    with caplog.at_level(logging.WARNING):
        for timeline in (closed_piece(), two_movements(), two_movements(closed=True)):
            assert find_time_map(document(timeline)).warnings == ()

    assert not caplog.records


def test_a_closing_tap_on_the_second_beat_gets_a_warning(caplog):
    timeline = beat_timeline(
        [
            {"time": 1.0, "measure": {"number": 1}},
            {"time": 2.0, "closing": True},
            {"time": 3.0, "measure": {}},
            {"time": 4.0},
        ]
    )
    tap = list(timeline.components)[1]

    with caplog.at_level(logging.WARNING):
        found = find_time_map(document(timeline))

    assert found.time_map is not None
    assert found.warnings == (_misplaced_warning(timeline, tap),)
    assert [r.getMessage() for r in caplog.records] == [f"{found.warnings[0]}."]


def test_of_two_closing_taps_at_the_end_the_first_gets_a_warning():
    timeline = closed_piece()
    tap = tla.new_id()
    timeline.components[tap] = tla.Component(
        id=tap, kind="beat", attrs={"time": 5.0, "closing": True}
    )

    found = find_time_map(document(timeline))

    assert found.warnings == (_misplaced_warning(timeline, tap),)
    assert found.time_map.end == 6.0


def test_each_misplaced_closing_tap_gets_its_own_warning_in_time_order():
    timeline = beat_timeline(
        [
            {"time": 1.0, "measure": {"number": 1}},
            {"time": 2.0, "closing": True},
            {"time": 3.0, "closing": True},
            {"time": 4.0, "measure": {}},
            {"time": 5.0, "closing": True},
            {"time": 6.0},
        ]
    )
    taps = list(timeline.components)

    found = find_time_map(document(timeline))

    assert found.warnings == tuple(
        _misplaced_warning(timeline, taps[k]) for k in (1, 2, 4)
    )


def test_a_closing_tap_before_a_bar_without_a_restart_gets_a_warning():
    timeline = beat_timeline(
        [
            {"time": 1.0, "measure": {"number": 1}},
            {"time": 2.0},
            {"time": 3.0, "closing": True},
            {"time": 4.0, "measure": {}},
            {"time": 5.0},
        ]
    )
    tap = list(timeline.components)[2]

    assert find_time_map(document(timeline)).warnings == (
        _misplaced_warning(timeline, tap),
    )


def test_a_closing_tap_with_no_bar_to_close_gets_a_warning():
    timeline = beat_timeline(
        [
            {"time": 0.5, "closing": True},
            {"time": 1.0, "measure": {"number": 1, "restart": True}},
            {"time": 2.0},
        ]
    )
    tap = list(timeline.components)[0]

    assert find_time_map(document(timeline)).warnings == (
        _misplaced_warning(timeline, tap),
    )


def test_a_closing_tap_past_the_media_is_kept_with_a_warning(caplog):
    timeline = closed_piece(closing=8.0)
    tap = list(timeline.components)[-1]

    with caplog.at_level(logging.WARNING):
        found = find_time_map(document(timeline, media_length=7.0))

    assert found.time_map.end == 8.0
    assert found.warnings == (
        f"Timeline {timeline.id}: the closing tap {tap} (8.0) is past the end of "
        "the media (7.0)",
    )
    assert [r.getMessage() for r in caplog.records] == [f"{found.warnings[0]}."]


def test_a_closing_tap_on_the_end_of_the_media_gets_no_warning():
    timeline = closed_piece(closing=7.0)

    assert find_time_map(document(timeline, media_length=7.0)).warnings == ()


def test_a_last_beat_past_the_media_before_a_closing_tap_says_only_that():
    # "The last measure ends one gap after it" would be wrong: it ends at the tap.
    timeline = closed_piece(closing=8.0)
    tap = list(timeline.components)[-1]

    found = find_time_map(document(timeline, media_length=3.5))

    assert found.warnings == (
        f"Timeline {timeline.id}: the closing tap {tap} (8.0) is past the end of "
        "the media (3.5)",
    )


def test_each_movements_closing_tap_past_the_media_gets_a_warning():
    timeline = two_movements(closed=True)
    taps = list(timeline.components)

    found = find_time_map(document(timeline, media_length=5.0))

    assert found.warnings == (
        f"Timeline {timeline.id}: the closing tap {taps[4]} (5.5) is past the end "
        "of the media (5.0)",
        f"Timeline {timeline.id}: the closing tap {taps[9]} (13.0) is past the end "
        "of the media (5.0)",
    )


def test_a_last_bar_without_a_tap_past_the_media_still_gets_the_media_warning():
    timeline = two_movements()

    found = find_time_map(document(timeline, media_length=11.0))

    assert found.warnings == (
        f"Timeline {timeline.id}: the last beat (11.0) is at or after the end of "
        "the media (11.0); the last measure ends one gap after it",
    )


def test_a_quarters_file_has_no_media_for_a_closing_tap_to_pass():
    timeline = closed_piece(closing=8.0)
    doc = document(timeline, media_length=7.0, time_unit="quarters")

    assert find_time_map(doc).warnings == ()


def test_a_misplaced_closing_tap_past_the_media_gets_only_the_one_warning():
    # It is an ordinary beat, so it is no closing tap past the media.
    timeline = beat_timeline(
        [
            {"time": 1.0, "measure": {"number": 1}},
            {"time": 2.0, "closing": True},
            {"time": 3.0, "measure": {}},
            {"time": 4.0},
            {"time": 5.0, "closing": True},
        ]
    )
    taps = list(timeline.components)

    found = find_time_map(document(timeline, media_length=1.5))

    assert found.warnings == (
        _misplaced_warning(timeline, taps[1]),
        f"Timeline {timeline.id}: the closing tap {taps[4]} (5.0) is past the end "
        "of the media (1.5)",
    )


def test_a_misplaced_tap_in_the_last_row_leaves_the_media_warning_standing():
    # A misplaced tap closes nothing, so the last bar ends one gap after its
    # last beat, as the media warning says.
    timeline = beat_timeline(
        [
            {"time": 1.0, "measure": {"number": 1}},
            {"time": 1.5, "closing": True},
            {"time": 2.0},
        ]
    )
    tap = list(timeline.components)[1]

    found = find_time_map(document(timeline, media_length=1.8))

    assert found.warnings == (
        f"Timeline {timeline.id}: the last beat (2.0) is at or after the end of the "
        "media (1.8); the last measure ends one gap after it",
        _misplaced_warning(timeline, tap),
    )


UNIT = {"denominator": 8, "units": "1"}


def test_a_beat_unit_on_a_closing_tap_is_kept_with_a_warning(caplog):
    timeline = closed_piece(beat_unit=UNIT)
    tap = list(timeline.components)[-1]

    with caplog.at_level(logging.WARNING):
        found = find_time_map(document(timeline))

    assert found.warnings == (_beat_unit_warning(timeline, tap),)
    assert [r.getMessage() for r in caplog.records] == [f"{found.warnings[0]}."]
    assert timeline.components[tap].attrs["beat_unit"] == UNIT
    # It starts nothing.
    assert [r.time_signature for r in found.time_map.measure_rows()] == ["2/4", "2/4"]


def test_a_beat_unit_on_a_movements_closing_tap_gets_the_warning():
    timeline = two_movements()
    tap = list(timeline.components)[4]
    timeline.components[tap].attrs["beat_unit"] = UNIT

    found = find_time_map(document(timeline))

    assert found.warnings == (_beat_unit_warning(timeline, tap),)
    assert {r.time_signature for r in found.time_map.measure_rows()} == {"2/4"}


def test_a_beat_unit_on_a_closing_tap_past_the_media_gets_both_warnings():
    timeline = closed_piece(closing=8.0, beat_unit=UNIT)
    tap = list(timeline.components)[-1]

    found = find_time_map(document(timeline, media_length=7.0))

    assert found.warnings == (
        f"Timeline {timeline.id}: the closing tap {tap} (8.0) is past the end of "
        "the media (7.0)",
        _beat_unit_warning(timeline, tap),
    )


def test_a_beat_unit_on_a_closing_tap_in_a_file_read_is_kept_with_a_warning():
    timeline = closed_piece(beat_unit=UNIT)
    tap = list(timeline.components)[-1]

    doc = read_as_a_file(timeline)
    found = find_time_map(doc)

    assert found.warnings == (_beat_unit_warning(timeline, tap),)
    kept = doc.timelines[timeline.id].components[tap].attrs["beat_unit"]
    assert (kept["denominator"], kept["units"]) == (8, "1")


def test_a_beat_unit_on_a_timeline_with_no_measure_mark_gets_a_warning(caplog):
    # It is kept, and starts nothing: there is no measure for it to start
    # (TimeLineAnnotator/project-management#528).
    timeline = beat_timeline(
        [
            {"time": 0.0},
            {"time": 1.0, "beat_unit": UNIT},
            {"time": 2.0, "closing": True, "beat_unit": UNIT},
        ]
    )
    unit, tap = list(timeline.components)[1:]

    doc = read_as_a_file(timeline)
    with caplog.at_level(logging.WARNING):
        found = find_time_map(doc)

    assert found.time_map is None
    assert found.warnings == (
        f"Timeline {timeline.id}: beat {unit} (1.0) has a beat unit, which starts "
        "nothing: the timeline has no measure marks",
        f"Timeline {timeline.id}: beat {tap} (2.0) has a beat unit, which starts "
        "nothing: the timeline has no measure marks",
    )
    assert [r.getMessage() for r in caplog.records] == [f"{w}." for w in found.warnings]
    kept = doc.timelines[timeline.id].components[unit].attrs
    assert (kept["beat_unit"]["denominator"], kept["beat_unit"]["units"]) == (8, "1")


def test_a_timeline_with_no_measure_mark_and_no_beat_unit_gets_no_warning():
    timeline = beat_timeline([{"time": 0.0}, {"time": 1.0}])

    found = find_time_map(read_as_a_file(timeline))

    assert found.time_map is None and found.warnings == ()


def test_a_beat_unit_on_a_misplaced_tap_counts_as_an_ordinary_beats():
    # It is read as an ordinary beat, so the unit starts something.
    timeline = beat_timeline(
        [
            {"time": 1.0, "measure": {"number": 1}},
            {"time": 2.0, "closing": True, "beat_unit": UNIT},
            {"time": 3.0},
        ]
    )
    tap = list(timeline.components)[1]

    found = find_time_map(document(timeline))

    assert found.warnings == (_misplaced_warning(timeline, tap),)
    assert found.time_map.measure_rows()[0].time_signature == "3/8"


def test_no_beat_unit_on_a_closing_tap_gets_no_such_warning():
    timeline = closed_piece(beat_unit=None)

    assert find_time_map(document(timeline)).warnings == ()


def test_a_table_without_rows_gets_no_closing_tap_warning():
    # A timeline of one closing tap: nothing is read as a beat or a barline.
    timeline = beat_timeline([{"time": 1.0, "closing": True}])

    found = find_time_map(document(timeline, media_length=0.5))

    assert found.reason == "no measure table"
    assert found.warnings == ()


def test_one_beat_and_a_closing_tap_give_no_time_map():
    # FR-003 counts beats, and a closing tap isn't one. Its row still ends at it.
    timeline = beat_timeline(
        [{"time": 1.0, "measure": {"number": 1}}, {"time": 3.0, "closing": True}]
    )
    doc = document(timeline)

    found = find_time_map(doc)

    assert found.reason == "fewer than two beats"
    assert found.warnings == ()
    assert [(r.beats, r.end) for r in measure_rows(doc, timeline.id)] == [(1, 3.0)]


def test_a_table_with_a_problem_gets_no_closing_tap_warning():
    # It has no rows, so nothing is read as a beat or a barline.
    timeline = closed_piece(closing=4.0)

    found = find_time_map(document(timeline, media_length=1.0))

    assert found.reason == "two beats at the same time (4.0)"
    assert found.warnings == ()


def test_every_beat_timeline_gets_its_closing_tap_warnings():
    chosen, other = closed_piece(closing=8.0), closed_piece(closing=9.0)
    other.ordinal = 2

    found = find_time_map(document(chosen, other, media_length=7.0))

    assert [w.partition(":")[0] for w in found.warnings] == [
        f"Timeline {chosen.id}",
        f"Timeline {other.id}",
    ]


def test_the_warnings_of_a_file_read_are_the_time_maps_too():
    # The reader's table leaves out every closing tap, misplaced ones too.
    timeline = beat_timeline(
        [
            {"time": 1.0, "measure": {"number": 1}},
            {"time": 2.0, "closing": True},
            {"time": 3.0, "measure": {}},
            {"time": 4.0},
            {"time": 6.0, "closing": True},
        ]
    )
    tap = list(timeline.components)[1]

    found = find_time_map(read_as_a_file(timeline, media_length=5.0))

    assert found.warnings[0] == _misplaced_warning(timeline, tap)
    assert "the closing tap" in found.warnings[1]
    assert [r.beats for r in found.time_map.measure_rows()] == [2, 2]
    assert found.time_map.end == 6.0


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
    reason = find_time_map(document(other)).reason
    assert reason == f"a beat without a time (beat {last})"


# A beat without a time, read from a file: WP3's table leaves it out of every
# row, so the time map finds it among the timeline's beats
# (TimeLineAnnotator/project-management#377). The reason names it by its id
# (TimeLineAnnotator/project-management#381).


def _read(timeline: tla.Timeline, times: dict[int, object]) -> tla.Document:
    """`timeline` written to a file, the times of its beats given by index in
    `times` replaced (`...` removes the key), and read as the core reads a file."""
    content = json.loads(tla.canonical_bytes(document(timeline)))
    components = content["timelines"][timeline.id]["components"]
    for index, time in times.items():
        beat = components[list(timeline.components)[index]]
        if time is ...:
            del beat["time"]
        else:
            beat["time"] = time
    return tla.loads((json.dumps(content, indent=2) + "\n").encode())


@pytest.mark.parametrize(
    "index, time, what",
    [
        pytest.param(1, ..., "a beat", id="beat without a time"),
        pytest.param(1, None, "a beat", id="beat whose time is null"),
        pytest.param(2, ..., "a downbeat", id="downbeat without a time"),
        pytest.param(0, ..., "a downbeat", id="first downbeat without a time"),
        pytest.param(3, 10**400, "a beat", id="time too large for a float"),
    ],
)
def test_a_beat_without_a_time_in_a_file_gives_no_time_map(index, time, what):
    # 2/4, a beat every second from 0 to 3: downbeats at 0 and 2.
    timeline = _beats(1)
    beat_id = list(timeline.components)[index]
    doc = _read(timeline, {index: time})
    read = doc.timelines[timeline.id]
    assert read.measures.rows  # the table isn't empty: some measures are left

    found = find_time_map(doc)

    assert found.timeline_id == timeline.id and found.time_map is None
    assert found.reason == f"{what} without a time (beat {beat_id})"
    assert time_map_for(doc, timeline.id) is None
    assert measure_rows(doc, timeline.id) == []  # FR-010


def test_a_table_without_rows_names_the_downbeat_without_a_time():
    # Its only downbeat has no time, so WP3's table has no rows: the beat
    # without a time is why, and the reason says so.
    timeline = beat_timeline([{"time": 0.0, "measure": {}}, {"time": 1.0}])
    downbeat = next(iter(timeline.components))
    doc = _read(timeline, {0: ...})
    assert doc.timelines[timeline.id].measures.rows == []

    found = find_time_map(doc)

    assert found.time_map is None
    assert found.reason == f"a downbeat without a time (beat {downbeat})"


def test_a_timeline_without_a_table_names_its_beat_without_a_time():
    timeline = _beats(1)
    timeline.measures = None
    beat_id = list(timeline.components)[1]
    del timeline.components[beat_id].attrs["time"]

    reason = find_time_map(document(timeline)).reason

    assert reason == f"a beat without a time (beat {beat_id})"


def test_of_several_beats_without_a_time_the_first_by_id_is_named():
    # By id, as a file lists them: their times aren't known. Not in WP3's
    # order of the beats, which takes a whole number too large for a float as
    # a time, nor in a document's order once it changes in memory.
    timeline = _beats(1, last=5)
    ids = list(timeline.components)  # in time order, and in id order
    assert ids == sorted(ids)
    doc = _read(timeline, {4: ..., 3: 10**400, 1: ...})
    expected = f"a beat without a time (beat {ids[1]})"

    assert find_time_map(doc).reason == expected
    read = doc.timelines[timeline.id]
    read.components = dict(reversed(read.components.items()))
    assert find_time_map(doc).reason == expected


@pytest.mark.parametrize("mark", [None, {}], ids=["without a mark", "with a mark"])
def test_a_closing_tap_without_a_time_gives_no_time_map(mark):
    # A closing tap is the closing barline, in no row; without a time, where the
    # last measure ends isn't known. It is no downbeat, even with a measure
    # mark, which starts no measure on a closing tap
    # (TimeLineAnnotator/project-management#375).
    timeline = _beats(1)
    tap = list(timeline.components)[-1]
    content = json.loads(tla.canonical_bytes(document(timeline)))
    beat = content["timelines"][timeline.id]["components"][tap]
    del beat["time"]
    beat["closing"] = True
    if mark is not None:
        beat["measure"] = mark
    doc = tla.loads((json.dumps(content, indent=2) + "\n").encode())
    assert ("measure" in doc.timelines[timeline.id].components[tap].attrs) is (
        mark is not None
    )

    found = find_time_map(doc)

    assert found.time_map is None
    assert found.reason == f"a beat without a time (beat {tap})"


def test_a_beat_whose_mark_is_null_is_no_downbeat():
    # The reader leaves out a null mark, so only a document built or changed
    # in memory has one: a beat without a mark all the same.
    timeline = _beats(1)
    beat_id = list(timeline.components)[1]
    timeline.components[beat_id].attrs.update(time=None, measure=None)

    reason = find_time_map(document(timeline)).reason

    assert reason == f"a beat without a time (beat {beat_id})"


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
