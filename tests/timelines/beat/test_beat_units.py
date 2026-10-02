from fractions import Fraction as F

import pytest

from tilia.timelines.beat.units import (
    fit_units,
    format_units,
    is_fit_ambiguous,
    parse_units,
)
from tilia.timelines.component_kinds import ComponentKind


class TestParseUnits:
    @pytest.mark.parametrize(
        "text, units",
        [
            ("1", [F(1)]),
            ("3", [F(3)]),
            ("2+3", [F(2), F(3)]),
            (" 2 + 2 + 3 ", [F(2), F(2), F(3)]),
            ("1/2", [F(1, 2)]),
            ("1/3+2/3", [F(1, 3), F(2, 3)]),
            ("2/4", [F(1, 2)]),
        ],
    )
    def test_valid(self, text, units):
        result = parse_units(text)
        assert result.is_valid
        assert result.units == units

    @pytest.mark.parametrize(
        "text", ["", " ", "2+", "+2", "2++3", "0", "1/0", "1.5", "-1", "a", "1e2"]
    )
    def test_invalid(self, text):
        result = parse_units(text)
        assert not result.is_valid
        assert result.error
        assert result.units == []

    def test_format(self):
        assert format_units([F(2), F(3)]) == "2+3"
        assert format_units([F(1, 3)]) == "1/3"
        assert format_units(parse_units(" 2/4 + 1 ").units) == "1/2+1"


class TestFitUnits:
    @pytest.mark.parametrize(
        "units, beat_count, values",
        [
            ([F(1)], 4, [F(1)] * 4),
            ([F(2), F(3)], 2, [F(2), F(3)]),
            ([F(2), F(3)], 4, [F(2), F(3), F(2), F(3)]),
            ([F(2), F(3)], 3, [F(2), F(3), F(2)]),
            ([F(3), F(2)], 1, [F(3)]),
            ([F(2), F(2), F(3)], 2, [F(2), F(2)]),
            ([F(1), F(2), F(3)], 2, [F(1), F(2)]),
            ([F(1)], 0, []),
        ],
    )
    def test_fit(self, units, beat_count, values):
        assert fit_units(units, beat_count) == values

    @pytest.mark.parametrize(
        "units, beat_count, ambiguous",
        [
            ([F(1)], 3, False),
            ([F(3)], 1, False),
            ([F(1, 2)], 3, False),
            ([F(2), F(3)], 2, False),
            ([F(2), F(3)], 4, False),
            ([F(2), F(3)], 1, True),
            ([F(2), F(3)], 3, True),
            ([F(2), F(2)], 3, False),
        ],
    )
    def test_ambiguous(self, units, beat_count, ambiguous):
        assert is_fit_ambiguous(units, beat_count) == ambiguous


def add_beats(beat_tl, count, start=0):
    for i in range(count):
        beat_tl.create_beat(start + i)


def time_signatures(beat_tl):
    return [(m.numerator, m.denominator) for m in beat_tl.measure_meters]


def add_beat_unit(beat_tl, beat_index, denominator, units):
    # The first beat always has a beat unit, which this edits.
    beat_id = beat_tl[beat_index].id
    beat_tl.put_beat_unit_on_beat(beat_id, denominator, units)
    return beat_tl.get_beat_unit_on_beat(beat_id)


def first_beat_unit(beat_tl):
    return beat_tl.get_beat_unit_on_beat(beat_tl[0].id)


def beat_unit_values(beat_tl):
    return [
        (
            beat_tl.get_beat_index(beat_tl.get_component(u.beat_id)),
            u.denominator,
            u.units,
        )
        for u in beat_tl.beat_units
    ]


class TestMeasureMeters:
    def test_first_beat_gets_the_default_beat_unit(self, beat_tl):
        add_beats(beat_tl, 7)

        assert time_signatures(beat_tl) == [(4, 4), (3, 4)]
        assert beat_unit_values(beat_tl) == [(0, 4, "1")]
        first = first_beat_unit(beat_tl)
        assert [m.beat_unit_id for m in beat_tl.measure_meters] == [first.id] * 2
        assert [m.starts_here for m in beat_tl.measure_meters] == [True, False]

    def test_empty_timeline(self, beat_tl):
        assert beat_tl.measure_meters == []

    def test_beat_unit_applies_until_next_change(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 8)
        beat_unit = add_beat_unit(beat_tl, 2, 8, "3")

        assert time_signatures(beat_tl) == [(2, 4), (6, 8), (6, 8), (6, 8)]
        meters = beat_tl.measure_meters
        assert [m.starts_here for m in meters] == [True, True, False, False]
        first = first_beat_unit(beat_tl)
        assert [m.beat_unit_id for m in meters] == [first.id] + [beat_unit.id] * 3

    def test_beat_unit_on_a_later_beat_applies_from_its_measure(self, beat_tl):
        add_beats(beat_tl, 8)
        add_beat_unit(beat_tl, 6, 8, "1")

        assert time_signatures(beat_tl) == [(4, 4), (4, 8)]

    def test_numerator_follows_bar_length(self, beat_tl):
        beat_tl.set_data("beat_pattern", [5, 7, 3])
        add_beats(beat_tl, 15)
        add_beat_unit(beat_tl, 0, 8, "1")

        assert time_signatures(beat_tl) == [(5, 8), (7, 8), (3, 8)]

    def test_fractional_units(self, beat_tl):
        beat_tl.set_data("beat_pattern", [4, 3])
        add_beats(beat_tl, 7)
        add_beat_unit(beat_tl, 0, 2, "1/2")

        assert time_signatures(beat_tl) == [(2, 2), (F(3, 2), 2)]

    def test_ambiguous_fit(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2, 3])
        add_beats(beat_tl, 5)
        add_beat_unit(beat_tl, 0, 4, "2+3")

        meters = beat_tl.measure_meters
        assert [m.beat_values for m in meters] == [[2, 3], [2, 3, 2]]
        assert [m.is_ambiguous for m in meters] == [False, True]

    def test_short_measures_take_the_start_of_the_pattern(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 6)
        add_beat_unit(beat_tl, 0, 4, "1+2+3")

        meters = beat_tl.measure_meters
        assert [m.beat_values for m in meters] == [[1, 2]] * 3
        assert all(m.is_ambiguous for m in meters)

    def test_pickup_also_takes_the_start_of_the_pattern(self, beat_tl):
        beat_tl.set_data("beat_pattern", [1, 2])
        add_beats(beat_tl, 3)
        add_beat_unit(beat_tl, 0, 4, "3+2")

        assert beat_tl.get_measure_meter(0).beat_values == [3]
        assert beat_tl.get_measure_meter(1).beat_values == [3, 2]

    def test_two_beat_units_in_a_measure_first_wins(self, beat_tl):
        add_beats(beat_tl, 8)
        first = add_beat_unit(beat_tl, 4, 8, "1")
        add_beat_unit(beat_tl, 6, 2, "1")

        meter = beat_tl.get_measure_meter(1)
        assert meter.is_conflicting
        assert meter.beat_unit_id == first.id
        assert meter.denominator == 8

    def test_beat_unit_follows_its_beat_when_barlines_move(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 6)
        add_beat_unit(beat_tl, 4, 8, "3")
        assert time_signatures(beat_tl) == [(2, 4), (2, 4), (6, 8)]

        # A forgotten bar's beats, before the beat unit.
        beat_tl.create_beat(0.25)
        beat_tl.create_beat(0.5)

        assert time_signatures(beat_tl) == [(2, 4), (2, 4), (2, 4), (6, 8)]

    def test_cache_is_refreshed_when_units_change(self, beat_tl):
        add_beats(beat_tl, 4)
        beat_unit = add_beat_unit(beat_tl, 0, 4, "1")
        assert time_signatures(beat_tl) == [(4, 4)]

        beat_tl.set_component_data(beat_unit.id, "units", "1/2")

        assert time_signatures(beat_tl) == [(2, 4)]


class TestCreateBeatUnit:
    def test_on_missing_beat_fails(self, beat_tl):
        add_beats(beat_tl, 1)
        beat_unit, error = beat_tl.create_component(
            ComponentKind.BEAT_UNIT, beat_id=-1, denominator=4, units="1"
        )
        assert beat_unit is None
        assert error

    def test_two_on_the_same_beat_fails(self, beat_tl):
        add_beats(beat_tl, 1)
        # The first beat already has one.
        beat_unit, error = beat_tl.create_component(
            ComponentKind.BEAT_UNIT, beat_id=beat_tl[0].id, denominator=8, units="1"
        )
        assert beat_unit is None
        assert error

    @pytest.mark.parametrize("denominator, units", [(0, "1"), (4, "0"), (4, "a")])
    def test_invalid_values_fail(self, beat_tl, denominator, units):
        add_beats(beat_tl, 2)
        beat_unit, error = beat_tl.create_component(
            ComponentKind.BEAT_UNIT,
            beat_id=beat_tl[1].id,
            denominator=denominator,
            units=units,
        )
        assert beat_unit is None
        assert error

    def test_units_are_stored_canonically(self, beat_tl):
        add_beats(beat_tl, 1)
        beat_unit = add_beat_unit(beat_tl, 0, 4, " 2/4 + 1 ")
        assert beat_unit.units == "1/2+1"
        beat_tl.set_component_data(beat_unit.id, "units", "3 + 2")
        assert beat_unit.units == "3+2"

    def test_beat_units_do_not_count_as_beats(self, beat_tl):
        add_beats(beat_tl, 4)
        add_beat_unit(beat_tl, 0, 8, "1")

        assert len(beat_tl) == 4
        assert all(c.KIND == ComponentKind.BEAT for c in beat_tl)
        assert beat_tl.beats_in_measure == [4]


class TestFirstBeatUnit:
    def test_none_without_beats(self, beat_tl):
        assert beat_tl.beat_units == []

    def test_pickup_copies_the_next_beat_unit(self, beat_tl):
        beat_tl.set_data("beat_pattern", [1, 2])
        add_beats(beat_tl, 4, start=1)
        add_beat_unit(beat_tl, 0, 8, "3")

        # A pickup before the old first beat, in a measure of its own.
        beat_tl.create_beat(0)

        assert beat_unit_values(beat_tl) == [(0, 8, "3"), (1, 8, "3")]
        assert time_signatures(beat_tl)[0] == (3, 8)

    def test_pickup_in_the_same_measure_needs_no_new_beat_unit(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 4, start=1)
        add_beat_unit(beat_tl, 0, 8, "3")

        beat_tl.create_beat(0)

        assert beat_unit_values(beat_tl) == [(1, 8, "3")]

    def test_deleting_the_first_beat_keeps_the_values(self, beat_tl):
        beat_tl.set_data("beat_pattern", [1])
        add_beats(beat_tl, 3)
        add_beat_unit(beat_tl, 0, 8, "3")

        beat_tl.delete_components([beat_tl[0]])

        assert beat_unit_values(beat_tl) == [(0, 8, "3")]


class TestSetBeatUnit:
    def test_onward_creates_on_the_first_beat(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 6)

        assert beat_tl.set_beat_unit(1, 8, "3")

        assert time_signatures(beat_tl) == [(2, 4), (6, 8), (6, 8)]
        assert beat_unit_values(beat_tl) == [(0, 4, "1"), (2, 8, "3")]

    def test_onward_edits_in_place(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 6)
        beat_tl.set_beat_unit(1, 8, "3")

        beat_tl.set_beat_unit(1, 4, "1/2")

        assert beat_unit_values(beat_tl) == [(0, 4, "1"), (2, 4, "1/2")]
        assert time_signatures(beat_tl) == [(2, 4), (1, 4), (1, 4)]

    def test_onward_from_a_later_measure_splits(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 8)
        beat_tl.set_beat_unit(1, 8, "3")

        beat_tl.set_beat_unit(2, 4, "1")

        assert time_signatures(beat_tl) == [(2, 4), (6, 8), (2, 4), (2, 4)]

    def test_this_measure_only(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 8)
        beat_tl.set_beat_unit(1, 8, "3")

        beat_tl.set_beat_unit(2, 4, "1", only_this_measure=True)

        assert time_signatures(beat_tl) == [(2, 4), (6, 8), (2, 4), (6, 8)]

    def test_this_measure_only_restores_the_default(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 6)

        beat_tl.set_beat_unit(0, 8, "3", only_this_measure=True)

        assert time_signatures(beat_tl) == [(6, 8), (2, 4), (2, 4)]

    def test_this_measure_only_keeps_a_following_change(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 6)
        beat_tl.set_beat_unit(1, 2, "1")

        beat_tl.set_beat_unit(0, 8, "3", only_this_measure=True)

        assert time_signatures(beat_tl) == [(6, 8), (2, 2), (2, 2)]
        assert len(beat_tl.beat_units) == 2

    def test_this_measure_only_on_the_last_measure(self, beat_tl):
        add_beats(beat_tl, 4)

        beat_tl.set_beat_unit(0, 8, "1", only_this_measure=True)

        assert time_signatures(beat_tl) == [(4, 8)]
        assert len(beat_tl.beat_units) == 1

    @pytest.mark.parametrize(
        "measure_index, denominator, units", [(5, 4, "1"), (-1, 4, "1"), (0, 0, "1")]
    )
    def test_invalid(self, beat_tl, measure_index, denominator, units):
        add_beats(beat_tl, 4)

        assert not beat_tl.set_beat_unit(measure_index, denominator, units)
        assert beat_unit_values(beat_tl) == [(0, 4, "1")]


class TestDeletingBeats:
    def test_beat_unit_moves_to_another_beat_of_its_measure(self, beat_tl):
        add_beats(beat_tl, 8)
        beat_unit = add_beat_unit(beat_tl, 4, 8, "1")

        beat_tl.delete_components([beat_tl[4]])

        assert beat_unit.beat_id == beat_tl[4].id
        assert beat_unit_values(beat_tl) == [(0, 4, "1"), (4, 8, "1")]

    def test_beat_unit_moves_to_the_next_measure_when_its_measure_goes(self, beat_tl):
        beat_tl.set_data("beat_pattern", [1])
        add_beats(beat_tl, 3)
        add_beat_unit(beat_tl, 1, 8, "1")

        beat_tl.delete_components([beat_tl[1]])

        # The measures it governed keep it.
        assert beat_unit_values(beat_tl) == [(0, 4, "1"), (1, 8, "1")]
        assert time_signatures(beat_tl) == [(1, 4), (1, 8)]

    def test_beat_unit_is_dropped_with_the_last_measure(self, beat_tl):
        beat_tl.set_data("beat_pattern", [1])
        add_beats(beat_tl, 3)
        add_beat_unit(beat_tl, 2, 8, "1")

        beat_tl.delete_components([beat_tl[2]])

        assert beat_unit_values(beat_tl) == [(0, 4, "1")]

    def test_beat_unit_is_dropped_if_the_destination_has_one(self, beat_tl):
        add_beats(beat_tl, 8)
        add_beat_unit(beat_tl, 4, 8, "1")
        kept = add_beat_unit(beat_tl, 5, 2, "1")

        beat_tl.delete_components([beat_tl[4]])

        assert beat_tl.beat_units == [first_beat_unit(beat_tl), kept]

    def test_deleting_a_beat_unit(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, 4)
        beat_unit = add_beat_unit(beat_tl, 2, 8, "1")

        beat_tl.delete_components([beat_unit])

        assert beat_unit_values(beat_tl) == [(0, 4, "1")]
        assert len(beat_tl) == 4
        assert time_signatures(beat_tl) == [(2, 4), (2, 4)]

    def test_deleting_the_first_beat_unit_resets_it(self, beat_tl):
        add_beats(beat_tl, 4)
        beat_unit = add_beat_unit(beat_tl, 0, 8, "1")

        beat_tl.delete_components([beat_unit])

        assert beat_unit_values(beat_tl) == [(0, 4, "1")]
        assert time_signatures(beat_tl) == [(4, 4)]

    def test_clear_removes_beat_units(self, beat_tl):
        add_beats(beat_tl, 4)
        add_beat_unit(beat_tl, 0, 8, "1")

        beat_tl.clear()

        assert beat_tl.beat_units == []
        assert len(beat_tl) == 0


class TestState:
    def test_restore_state(self, beat_tl):
        add_beats(beat_tl, 8)
        add_beat_unit(beat_tl, 4, 8, "3")
        state = beat_tl.get_state()["components"]

        beat_tl.delete_components([beat_tl[4], beat_tl[5], beat_tl[6], beat_tl[7]])
        beat_tl.set_beat_unit(0, 2, "1")
        assert beat_unit_values(beat_tl) == [(0, 2, "1")]

        beat_tl.component_manager.restore_state(state)

        assert len(beat_tl) == 8
        assert beat_unit_values(beat_tl) == [(0, 4, "1"), (4, 8, "3")]
        assert time_signatures(beat_tl) == [(4, 4), (12, 8)]

    def test_serialized_components_include_beat_units(self, beat_tl):
        add_beats(beat_tl, 4)
        beat_unit = add_beat_unit(beat_tl, 0, 8, "2+2")

        components = beat_tl.get_state()["components"]

        assert components[beat_unit.id] == {
            "beat_id": beat_tl[0].id,
            "denominator": 8,
            "units": "2+2",
            "assumed": False,
            "kind": "BEAT_UNIT",
            "hash": beat_unit.hash,
        }

    def test_hash_changes_with_beat_units(self, beat_tl):
        add_beats(beat_tl, 4)
        before = beat_tl.component_manager.hash_components()

        add_beat_unit(beat_tl, 0, 8, "1")

        assert beat_tl.component_manager.hash_components() != before
