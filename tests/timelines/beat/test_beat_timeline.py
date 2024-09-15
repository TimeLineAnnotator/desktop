import pytest

from tilia.ui.actions import TiliaAction


class TestBeatTimeline:
    def test_create_beat_at_same_time_fails(self, beat_tl, actions):
        actions.trigger(TiliaAction.BEAT_ADD)
        actions.trigger(TiliaAction.BEAT_ADD)
        assert len(beat_tl) == 1

    def test_create_beat_at_negative_time_fails(self, beat_tl, tilia_state, actions):
        tilia_state.current_time = -10
        actions.trigger(TiliaAction.BEAT_ADD)
        assert len(beat_tl) == 0

    def test_create_beat_at_time_bigger_than_media_duration_fails(
        self, beat_tl, tilia_state, actions
    ):
        tilia_state.duration = 100
        tilia_state.current_time = 101
        actions.trigger(TiliaAction.BEAT_ADD)
        assert len(beat_tl) == 0

    def test_create_beat_at_middle_updates_next_beats_is_first_in_measure(
        self, beat_tl, tilia_state, actions
    ):
        beat_tl.beat_pattern = [2]
        tilia_state.current_time = 0
        actions.trigger(TiliaAction.BEAT_ADD)
        tilia_state.current_time = 10
        actions.trigger(TiliaAction.BEAT_ADD)
        tilia_state.current_time = 20
        actions.trigger(TiliaAction.BEAT_ADD)

        tilia_state.current_time = 5
        actions.trigger(TiliaAction.BEAT_ADD)

        assert beat_tl[1].get_data("is_first_in_measure") is False
        assert beat_tl[2].get_data("is_first_in_measure") is True
        assert beat_tl[3].get_data("is_first_in_measure") is False

    def test_recalculate_measures_added_one_measure(self, beat_tl):
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measures_added_one_beat(self, beat_tl):
        beat_tl.create_beat(time=1)

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [1]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measure_added_one_measure_and_a_beat(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 1]
        assert beat_tl.measure_numbers == [1, 2]

    def test_recalculate_measure_added_two_measures(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)
        beat_tl.create_beat(time=4)

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 2]
        assert beat_tl.measure_numbers == [1, 2]

    def test_recalculate_measures_added_one_beat_to_incomplete_measure_1(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])

        beat_tl.create_beat(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_beat(time=2)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measures_added_one_beat_to_incomplete_measure_2(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])

        beat_tl.beat_pattern = [4]

        beat_tl.create_beat(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_beat(time=2)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measures_added_one_measure_to_incomplete_measure(
        self, beat_tl
    ):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 1]
        assert beat_tl.measure_numbers == [1, 2]

    def test_recalculate_measures_added_measure_and_beat_to_incomplete_measure(
        self, beat_tl
    ):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)
        beat_tl.create_beat(time=4)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 2]
        assert beat_tl.measure_numbers == [1, 2]

    def test_recalculate_measures_added_two_measures_to_incomplete_measure(
        self, beat_tl
    ):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)
        beat_tl.create_beat(time=4)
        beat_tl.create_beat(time=5)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 2, 1]
        assert beat_tl.measure_numbers == [1, 2, 3]

    def test_reduce_beats_in_measure_more_than_available(self, beat_tl):
        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(13)
        assert beat_tl.beats_in_measure == []

    def test_recalculate_measures_removed_one_measure(self, beat_tl):
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)
        b1, _ = beat_tl.create_beat(time=3)
        b2, _ = beat_tl.create_beat(time=4)

        beat_tl.recalculate_measures()

        beat_tl.delete_components([beat_tl[2], beat_tl[3]])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measures_removed_one_beat(self, beat_tl):
        beat_tl.create_beat(time=1)
        b1, _ = beat_tl.create_beat(time=2)

        beat_tl.recalculate_measures()

        beat_tl.delete_components([beat_tl[1]])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [1]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measure_removed_one_measure_and_a_beat(self, beat_tl):
        beat_tl.create_beat(time=1)
        b1, _ = beat_tl.create_beat(time=2)
        b2, _ = beat_tl.create_beat(time=3)
        b3, _ = beat_tl.create_beat(time=4)

        beat_tl.recalculate_measures()

        beat_tl.delete_components([beat_tl[1], beat_tl[2], beat_tl[3]])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [1]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measure_removed_two_measures(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])

        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)
        b0, _ = beat_tl.create_beat(time=3)
        b1, _ = beat_tl.create_beat(time=4)
        b2, _ = beat_tl.create_beat(time=5)
        b3, _ = beat_tl.create_beat(time=6)

        beat_tl.recalculate_measures()

        beat_tl.delete_components([beat_tl[2],beat_tl[3],beat_tl[4],beat_tl[5]])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measure_first_beat_from_last_measure(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)
        beat_tl.create_beat(time=4)

        beat_tl.recalculate_measures()

        beat_tl.delete_components([beat_tl[2]])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 1]
        assert beat_tl.measure_numbers == [1, 2]

    def test_change_measure_number_case1(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.set_measure_number(1, 10)
        assert beat_tl.measure_numbers == [1, 10, 11, 12]
        assert beat_tl.measures_to_force_display == [1]

    def test_change_measure_number_case2(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.set_measure_number(2, 10)
        assert beat_tl.measure_numbers == [1, 2, 10, 11]
        assert beat_tl.measures_to_force_display == [2]

    def test_propagate_number_change_stops_at_forced_display(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4, 5, 6]
        beat_tl.measures_to_force_display = [4]
        beat_tl.set_measure_number(2, 10)
        assert beat_tl.measure_numbers == [1, 2, 10, 11, 5, 6]
        assert beat_tl.measures_to_force_display == [4, 2]

    def test_reset_measure_number_first_measure(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.set_measure_number(0, 10)
        beat_tl.reset_measure_number(0)
        beat_tl.measure_numbers = [1, 2, 3, 4]

    def test_reset_measure_number_middle_measure(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.set_measure_number(1, 10)
        beat_tl.reset_measure_number(1)
        beat_tl.measure_numbers = [1, 2, 3, 4]

    def test_reset_measure_number_last_measure(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.set_measure_number(3, 10)
        beat_tl.reset_measure_number(3)
        beat_tl.measure_numbers = [1, 2, 3, 4]

    def test_get_times_by_measure_no_beats(self, beat_tl):
        with pytest.raises(ValueError):
            beat_tl.get_time_by_measure(0)

    def test_get_times_by_measure_one_measure(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1) == [1]

    def test_get_times_by_measure_multiple_measures(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)
        beat_tl.create_beat(time=4)
        beat_tl.create_beat(time=5)
        beat_tl.create_beat(time=6)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1) == [1]
        assert beat_tl.get_time_by_measure(2) == [3]
        assert beat_tl.get_time_by_measure(3) == [5]

    def test_get_times_by_measure_index_bigger_than_measure_count(self, beat_tl):
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(2) == []

        assert beat_tl.get_time_by_measure(999) == []

    def test_get_times_by_measure_negative_index(self, beat_tl):
        beat_tl.create_beat(time=1)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(-1) == []

    def test_delete_beat_updates_is_first_in_measure_of_subsequent_beats(self, beat_tl):
        beat_tl.beat_pattern = [2]
        beat_tl.create_beat(0)
        beat_tl.create_beat(1)
        beat_tl.create_beat(2)
        beat_tl.create_beat(3)
        beat_tl.create_beat(4)

        beat_tl.delete_components([beat_tl[1]])

        assert beat_tl[0].get_data("is_first_in_measure")
        assert not beat_tl[1].get_data("is_first_in_measure")
        assert beat_tl[2].get_data("is_first_in_measure")
        assert not beat_tl[3].get_data("is_first_in_measure")
