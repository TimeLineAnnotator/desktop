"""Distances and lengths in bars and beats: where a time lies along the map, how
long a span lasts, and how long the beat and the bar holding a time last
(FR-040-FR-042). The prototype's own assertions are in
test_timemap_prototype.py; these are the spec's User Story 3, scenarios 4 and 6.
"""

from __future__ import annotations

import itertools
import logging
import math

import pytest

from docs import beat_timeline, document
from tilia_core import tla
from tilia_core.timemap import TimeMap, time_map_for


def _timeline(times: list[float], counts: list[int]) -> tla.Timeline:
    """A beat at each time, in measures of `counts` beats, numbered from 1."""
    marks = {k: {} for k in itertools.accumulate(counts[:-1], initial=0)}
    marks[0] = {"number": 1}
    return beat_timeline(
        [{"time": t, "measure": marks.get(k)} for k, t in enumerate(times)]
    )


def _map(times: list[float], counts: list[int], **kwargs) -> TimeMap:
    timeline = _timeline(times, counts)
    time_map = time_map_for(document(timeline, **kwargs), timeline.id)
    assert time_map is not None
    return time_map


def _accelerating(bars: int, beats: int = 4) -> list[float]:
    """A beat at each time, every gap 3 % shorter than the one before."""
    gaps = [0.97**k for k in range(bars * beats - 1)]
    return list(itertools.accumulate(gaps, initial=0.0))


def test_eight_bars_last_eight_bars_whatever_the_tempo():
    # Spec, US3 scenario 4: from the downbeat of bar 1 to the downbeat of bar 9.
    steady = _map([float(t) for t in range(40)], [4] * 10)
    faster = _map(_accelerating(10), [4] * 10)

    for tm in (steady, faster):
        bar_one, bar_nine = tm.measures()[0][0], tm.measures()[8][0]
        assert tm.length(bar_one, bar_nine, "bar") == 8.0
        assert tm.length(bar_one, bar_nine, "beat") == 32.0
        assert tm.position(bar_nine, "bar") == 8.0
    # Halfway through a bar in beats is halfway in bars, whatever the seconds.
    third_beat = _accelerating(10)[4 * 4 + 2]  # of bar 5
    assert faster.position(third_beat, "bar") == 4.5


# A 3/4 bar inside 4/4, a beat every second: bar 1 from 0 s, bar 2 (3/4) from
# 4 s, bar 3 from 7 s, the closing barline at 11 s.
THREE_FOUR_INSIDE = ([float(t) for t in range(11)], [4, 3, 4])


def test_a_bar_counts_one_whatever_its_metre():
    # Spec, US3 scenario 4: across a 3/4 bar inside 4/4, a bar counts 1, and
    # inside a bar the fraction counts beats.
    tm = _map(*THREE_FOUR_INSIDE)

    assert [tm.position(t, "bar") for t in (0.0, 4.0, 7.0)] == [0.0, 1.0, 2.0]
    assert tm.position(5.5, "bar") == 1.5  # halfway through the 3/4 bar
    assert tm.position(2.0, "bar") == 0.5  # halfway through bar 1
    assert tm.length(4.0, 7.0, "bar") == 1.0 and tm.length(4.0, 7.0, "beat") == 3.0
    # From beat 3 of bar 1 to beat 3 of bar 3: two bars, seven beats.
    assert tm.length(2.0, 9.0, "bar") == 2.0 and tm.length(2.0, 9.0, "beat") == 7.0
    # Two beats of bar 1 and one and a half of bar 2: half of each.
    assert tm.length(2.0, 5.5, "bar") == 1.0 and tm.length(2.0, 5.5, "beat") == 3.5
    # The whole map: three bars of eleven beats.
    assert tm.length(0.0, 11.0, "bar") == 3.0 and tm.length(0.0, 11.0, "beat") == 11.0


def test_lengths_are_rounded_to_a_millionth():
    # 1.3 s is 0.3 of a beat-gap of 0.5 s after 1.0 s, which floats give as
    # 0.6000000000000001 beats.
    tm = _map([1.0 + 0.5 * i for i in range(8)], [4, 4])

    assert (1.3 - 1.0) / 0.5 != 0.6
    assert tm.length(1.0, 1.3, "beat") == 0.6
    assert tm.length(1.0, 1.3, "bar") == 0.15


def test_lengths_and_positions_off_the_map():
    tm = _map(*THREE_FOUR_INSIDE)

    # Before the first beat, beyond the tolerance, or after the closing barline.
    assert tm.position(-0.5, "bar") is None and tm.position(11.5, "beat") is None
    assert tm.length(-0.5, 4.0, "bar") is None
    assert tm.length(4.0, 11.5, "bar") is None
    # The closing barline ends the last bar, for an end but not for a start.
    assert tm.position(11.0, "bar") == 3.0 and tm.position(11.05, "beat") == 11.0
    assert tm.length(11.0, 11.0, "bar") is None
    # Within the tolerance before the first beat: on it.
    assert tm.position(-0.05, "bar") == 0.0 and tm.length(-0.05, 4.0, "bar") == 1.0
    for t in (None, math.nan, math.inf):
        assert tm.position(t, "bar") is None
        assert tm.length(t, 4.0, "bar") is None and tm.length(0.0, t, "beat") is None
        assert tm.unit_seconds(t, "beat") is None


def test_how_long_a_beat_and_a_bar_last():
    # Spec, US3 scenario 6: how long the beat and the bar holding a time last,
    # in the file's unit (for WITHIN 1 beat). Bar 1's beats are uneven.
    times = [0.0, 0.8, 1.8, 2.4, 3.0, 3.5, 4.0, 4.5]
    tm = _map(times, [4, 4])

    assert tm.unit_seconds(0.0, "beat") == 0.8
    assert tm.unit_seconds(2.0, "beat") == pytest.approx(0.6)
    assert tm.unit_seconds(2.0, "bar") == 3.0
    assert tm.unit_seconds(3.2, "bar") == 2.0  # bar 2 ends at the closing barline
    # Snapped first: 2.95 is on bar 2's downbeat.
    assert tm.unit_seconds(2.95, "beat") == 0.5 and tm.unit_seconds(2.95, "bar") == 2.0
    # The last beat lasts as long as the gap before it (FR-011).
    assert tm.unit_seconds(4.7, "beat") == 0.5
    # Off the map: nothing.
    assert tm.unit_seconds(-1.0, "bar") is None and tm.unit_seconds(5.0, "beat") is None


def test_the_last_beat_ends_with_the_media():
    # FR-011: the last beat lasts until the end of the media, if that comes
    # before the gap ends.
    tm = _map([0.0, 1.0, 2.0, 3.0], [2, 2], media_length=3.4)

    assert tm.end == 3.4
    assert tm.unit_seconds(3.2, "beat") == pytest.approx(0.4)
    assert tm.unit_seconds(3.2, "bar") == pytest.approx(1.4)
    assert tm.position(3.2, "beat") == pytest.approx(3.5)
    assert tm.position(3.4, "bar") == 2.0 and tm.length(3.4, 3.4, "bar") is None


def test_in_a_quarters_file_the_unit_is_quarter_notes():
    # unit_seconds is in the file's unit, despite its name: nothing converts.
    times = [0.0, 1.5, 3.0, 4.5, 6.0]
    tm = _map(times, [2, 3], time_unit="quarters", media_length=5.0)

    assert tm.unit_seconds(0.5, "beat") == 1.5 and tm.unit_seconds(0.5, "bar") == 3.0
    # The media's length is in seconds: it doesn't end a quarters file's map.
    assert tm.end == 7.5 and tm.unit_seconds(6.2, "bar") == 4.5


@pytest.mark.parametrize("unit", ["bars", "measure", "", None])
def test_a_unit_other_than_bar_or_beat_gives_nothing(caplog, unit):
    # Not something a corpus file can give: a caller's mistake, logged as an
    # error rather than raised (desktop's CLAUDE.md), and never read as beats.
    tm = _map(*THREE_FOUR_INSIDE)

    with caplog.at_level(logging.ERROR, logger="tilia_core.timemap.timemap"):
        assert tm.position(5.5, unit) is None
        assert tm.length(0.0, 5.5, unit) is None
        assert tm.unit_seconds(5.5, unit) is None

    assert len(caplog.records) == 3
    assert all(repr(unit) in record.getMessage() for record in caplog.records)
