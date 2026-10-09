from fractions import Fraction as F

import pytest

from docs import beat_timeline
from tilia_core.timemap._rows import rows_of
from tilia_core.timemap.meters import meters_of

# What TiLiA puts on the first beat, and WP3's migration on an old file's.
DEFAULT = {"denominator": 4, "units": "1", "assumed": True}


def unit(denominator, units, assumed=False):
    return {"denominator": denominator, "units": units, "assumed": assumed}


def tapped(count, pattern=(4,), units=None):
    """
    `count` beats a second apart, in measures of `pattern` beats, repeated as
    a beat pattern is, with `units` ({beat index: unit}) set on beats. The first
    beat has the default unit, assumed, unless `units` says otherwise.
    """
    units = {0: DEFAULT, **(units or {})}
    starts, start, i = set(), 0, 0
    while start < count:
        starts.add(start)
        start += pattern[i % len(pattern)]
        i += 1
    return beat_timeline(
        [
            {
                "time": float(index),
                "measure": {} if index in starts else None,
                "beat_unit": units.get(index),
            }
            for index in range(count)
        ]
    )


def beat_ids(timeline):
    return list(timeline.components)


def meters(timeline):
    return meters_of(rows_of(timeline))


def time_signatures(timeline):
    return [(m.numerator, m.denominator) for m in meters(timeline)]


class TestMeasureMeters:
    def test_first_beat_gets_the_default_beat_unit(self):
        timeline = tapped(7)
        first = beat_ids(timeline)[0]

        assert time_signatures(timeline) == [(4, 4), (3, 4)]
        assert [m.beat_unit_id for m in meters(timeline)] == [first] * 2
        assert [m.starts_here for m in meters(timeline)] == [True, False]

    def test_empty_timeline(self):
        assert meters_of([]) == []

    def test_beat_unit_applies_until_next_change(self):
        timeline = tapped(8, (2,), {2: unit(8, "3")})
        first, beat_unit = beat_ids(timeline)[0], beat_ids(timeline)[2]

        assert time_signatures(timeline) == [(2, 4), (6, 8), (6, 8), (6, 8)]
        result = meters(timeline)
        assert [m.starts_here for m in result] == [True, True, False, False]
        assert [m.beat_unit_id for m in result] == [first] + [beat_unit] * 3

    def test_beat_unit_on_a_later_beat_applies_from_its_measure(self):
        timeline = tapped(8, units={6: unit(8, "1")})

        assert time_signatures(timeline) == [(4, 4), (4, 8)]

    def test_numerator_follows_bar_length(self):
        timeline = tapped(15, (5, 7, 3), {0: unit(8, "1")})

        assert time_signatures(timeline) == [(5, 8), (7, 8), (3, 8)]

    def test_fractional_units(self):
        timeline = tapped(7, (4, 3), {0: unit(2, "1/2")})

        assert time_signatures(timeline) == [(2, 2), (F(3, 2), 2)]

    def test_ambiguous_fit(self):
        timeline = tapped(5, (2, 3), {0: unit(4, "2+3")})

        result = meters(timeline)
        assert [m.beat_values for m in result] == [[2, 3], [2, 3, 2]]
        assert [m.is_ambiguous for m in result] == [False, True]

    def test_short_measures_take_the_start_of_the_pattern(self):
        timeline = tapped(6, (2,), {0: unit(4, "1+2+3")})

        result = meters(timeline)
        assert [m.beat_values for m in result] == [[1, 2]] * 3
        assert all(m.is_ambiguous for m in result)

    def test_pickup_also_takes_the_start_of_the_pattern(self):
        timeline = tapped(3, (1, 2), {0: unit(4, "3+2")})

        result = meters(timeline)
        assert result[0].beat_values == [3]
        assert result[1].beat_values == [3, 2]

    def test_two_beat_units_in_a_measure_first_wins(self):
        timeline = tapped(8, units={4: unit(8, "1"), 6: unit(2, "1")})

        meter = meters(timeline)[1]
        assert meter.is_conflicting
        assert meter.beat_unit_id == beat_ids(timeline)[4]
        assert meter.denominator == 8


class TestDefaultAndAssumed:
    def test_without_any_unit_a_measure_of_n_taps_is_n_over_4(self):
        timeline = tapped(7, units={0: None})

        result = meters(timeline)
        assert time_signatures(timeline) == [(4, 4), (3, 4)]
        assert [m.units for m in result] == [[1], [1]]
        assert [m.beat_unit_id for m in result] == [None, None]
        assert [m.starts_here for m in result] == [False, False]
        assert all(m.is_assumed for m in result)

    def test_assumed_follows_the_governing_unit(self):
        timeline = tapped(12, units={4: unit(8, "1"), 8: unit(8, "2", assumed=True)})

        assert [m.is_assumed for m in meters(timeline)] == [True, False, True]

    def test_the_first_unit_of_a_conflicting_measure_is_carried_forward(self):
        timeline = tapped(12, units={4: unit(8, "1"), 6: unit(2, "1")})

        result = meters(timeline)
        assert [m.is_conflicting for m in result] == [False, True, False]
        assert result[2].beat_unit_id == beat_ids(timeline)[4]
        assert result[2].time_signature == (4, 8)


class TestUnreadableUnits:
    @pytest.mark.parametrize(
        "bad",
        [
            unit(8, "a"),
            unit(8, "0"),
            unit(8, ""),
            unit(8, "2+"),
            unit(8, 3),
            unit(0, "1"),
            unit(129, "1"),
        ],
    )
    def test_is_ignored_and_the_unit_before_carries_on(self, bad, caplog):
        timeline = tapped(8, (2,), {2: unit(8, "3"), 4: bad})
        before = beat_ids(timeline)[2]

        result = meters(timeline)
        assert time_signatures(timeline) == [(2, 4), (6, 8), (6, 8), (6, 8)]
        assert [m.starts_here for m in result] == [True, True, False, False]
        assert [m.beat_unit_id for m in result][1:] == [before] * 3
        assert "beat unit" in caplog.text

    def test_does_not_make_its_measure_conflicting(self):
        timeline = tapped(4, units={0: unit(8, "3"), 2: unit(8, "x")})

        (meter,) = meters(timeline)
        assert not meter.is_conflicting
        assert meter.time_signature == (12, 8)


THIRDS = [F(1, 3)] * 4


class TestUserStory2:
    @pytest.mark.parametrize(
        "taps, beat_unit, time_signature, beat_values, quarters, assumed, ambiguous",
        [
            # A measure of two taps with only the default unit: 2/4, assumed.
            (2, DEFAULT, (2, 4), [1, 1], [1, 1], True, False),
            # 6/8 tapped in two.
            (2, unit(8, "3"), (6, 8), [3, 3], [F(3, 2), F(3, 2)], False, False),
            # 5/8 tapped as 2+3.
            (2, unit(8, "2+3"), (5, 8), [2, 3], [1, F(3, 2)], False, False),
            # Three taps under 2+3: 7/8, ambiguous.
            (3, unit(8, "2+3"), (7, 8), [2, 3, 2], [1, F(3, 2), 1], False, True),
            # A pickup of one tap under {8, "3"}: 3/8.
            (1, unit(8, "3"), (3, 8), [3], [F(3, 2)], False, False),
            # Units 1/3 over 4 on four taps: a numerator that isn't whole.
            (4, unit(4, "1/3"), (F(4, 3), 4), THIRDS, THIRDS, False, False),
        ],
    )
    def test_scenario(
        self, taps, beat_unit, time_signature, beat_values, quarters, assumed, ambiguous
    ):
        (meter,) = meters(tapped(taps, (taps,), {0: beat_unit}))

        assert meter.time_signature == time_signature
        assert meter.beat_values == beat_values
        assert [meter.quarter_length(value) for value in meter.beat_values] == quarters
        assert meter.is_assumed == assumed
        assert meter.is_ambiguous == ambiguous
        assert all(isinstance(value, F) for value in meter.beat_values)
        assert isinstance(meter.numerator, F)
