from fractions import Fraction as F
from unittest.mock import patch

import pytest

from tilia.timelines.beat.timeline import BeatTimeline


def add_beats(beat_tl, times):
    for time in times:
        beat_tl.create_beat(time)


def add_beat_unit(beat_tl, beat_index, denominator, units):
    # The first beat already has a beat unit, which this edits.
    beat_tl.put_beat_unit_on_beat(beat_tl[beat_index].id, denominator, units)


class TestBeatStamps:
    def test_default_is_one_quarter_per_beat(self, beat_tl):
        add_beats(beat_tl, range(6))

        assert beat_tl.quarter_stamps == [0, 1, 2, 3, 4, 5]

    def test_dotted_quarter_beats(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, range(4))
        add_beat_unit(beat_tl, 0, 8, "3")

        assert beat_tl.quarter_stamps == [0, F(3, 2), 3, F(9, 2)]

    def test_changing_beat_unit(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, range(6))
        add_beat_unit(beat_tl, 2, 2, "1")

        assert beat_tl.quarter_stamps == [0, 1, 2, 4, 6, 8]

    def test_uneven_units(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, range(4))
        add_beat_unit(beat_tl, 0, 8, "2+3")

        assert beat_tl.quarter_stamps == [0, 1, F(5, 2), F(7, 2)]

    def test_triplets_are_exact(self, beat_tl):
        beat_tl.set_data("beat_pattern", [3])
        add_beats(beat_tl, range(7))
        add_beat_unit(beat_tl, 0, 4, "1/3")

        assert beat_tl.quarter_stamps[6] == 2
        assert beat_tl.quarter_stamps[1] == F(1, 3)

    def test_pickup_starts_at_zero(self, beat_tl):
        beat_tl.set_data("beat_pattern", [1, 2])
        add_beats(beat_tl, range(3))
        add_beat_unit(beat_tl, 0, 4, "3+2")

        # One pickup tap, read from the start of 3+2, then a full bar.
        assert beat_tl.quarter_stamps == [0, 3, 6]

    def test_stamps_follow_inserted_beats(self, beat_tl):
        add_beats(beat_tl, [0, 2, 3])
        assert beat_tl.quarter_stamps == [0, 1, 2]

        beat_tl.create_beat(1)

        assert beat_tl.quarter_stamps == [0, 1, 2, 3]

    def test_of_beat(self, beat_tl):
        add_beats(beat_tl, range(3))

        assert beat_tl.get_quarter_stamp_of_beat(beat_tl[2]) == 2


class TestTimeToStamp:
    @pytest.fixture
    def tl(self, beat_tl):
        # Beats every 2 s, worth a dotted quarter each.
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, [10, 12, 14, 16])
        add_beat_unit(beat_tl, 0, 8, "3")
        return beat_tl

    @pytest.mark.parametrize(
        "time, stamp",
        [(10, 0), (11, 0.75), (12, 1.5), (15, 3.75), (16, 4.5), (18, 6), (8, -1.5)],
    )
    def test_time_to_stamp(self, tl, time, stamp):
        assert tl.get_quarter_stamp_by_time(time) == pytest.approx(stamp)

    @pytest.mark.parametrize(
        "stamp, time",
        [(0, 10), (0.75, 11), (1.5, 12), (3.75, 15), (4.5, 16), (6, 18), (-1.5, 8)],
    )
    def test_stamp_to_time(self, tl, stamp, time):
        assert tl.get_time_by_quarter_stamp(stamp) == pytest.approx(time)

    def test_round_trip(self, tl):
        for time in [10.3, 12.7, 13.1, 16.9]:
            stamp = tl.get_quarter_stamp_by_time(time)
            assert tl.get_time_by_quarter_stamp(stamp) == pytest.approx(time)

    def test_uneven_beat_lengths(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        add_beats(beat_tl, [0, 1, 2])
        add_beat_unit(beat_tl, 0, 4, "2+3")

        # Beat 0 lasts 2 quarters over 1 s; beat 1 lasts 3 quarters over 1 s.
        assert beat_tl.get_quarter_stamp_by_time(0.5) == pytest.approx(1)
        assert beat_tl.get_quarter_stamp_by_time(1.5) == pytest.approx(3.5)

    @pytest.mark.parametrize("times", [[], [5]])
    def test_needs_two_beats(self, beat_tl, times):
        add_beats(beat_tl, times)

        assert beat_tl.get_quarter_stamp_by_time(5) is None
        assert beat_tl.get_time_by_quarter_stamp(0) is None

    def test_follows_dragged_beat(self, tl):
        tl.set_component_data(tl[1].id, "time", 13)

        assert tl.get_quarter_stamp_by_time(13) == pytest.approx(1.5)


class TestCaching:
    def test_conversions_reuse_one_table(self, beat_tl):
        add_beats(beat_tl, range(100))
        build = BeatTimeline._build_time_stamp_table

        with patch.object(
            BeatTimeline, "_build_time_stamp_table", autospec=True, side_effect=build
        ) as spy:
            for i in range(500):
                stamp = beat_tl.get_quarter_stamp_by_time(i * 0.2)
                beat_tl.get_time_by_quarter_stamp(stamp)

        assert spy.call_count == 1

    def test_table_is_rebuilt_after_a_change(self, beat_tl):
        add_beats(beat_tl, range(4))
        assert beat_tl.get_quarter_stamp_by_time(3) == pytest.approx(3)

        beat_tl.set_component_data(beat_tl[3].id, "time", 4)

        assert beat_tl.get_quarter_stamp_by_time(4) == pytest.approx(3)
