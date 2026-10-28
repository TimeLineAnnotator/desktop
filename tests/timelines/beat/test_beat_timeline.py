import pytest

from tests.mock import patch_yes_or_no_dialog
from tests.utils import undoable
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.ui import commands


class TestBeatTimeline:
    def test_create_beat_at_same_time_fails(self, beat_tlui):
        commands.execute("timeline.beat.add")
        commands.execute("timeline.beat.add")
        assert len(beat_tlui) == 1

    def test_create_beat_at_negative_time_fails(self, beat_tlui):
        commands.execute("timeline.beat.add", time=-10)
        assert len(beat_tlui) == 0

    def test_create_beat_at_time_bigger_than_media_duration_fails(
        self, beat_tlui, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute("timeline.beat.add", time=101)
        assert len(beat_tlui) == 0

    def test_create_beat_at_middle_keeps_the_measures_lengths(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [2]
        commands.execute("media.seek", 0)
        commands.execute("timeline.beat.add")
        commands.execute("media.seek", 10)
        commands.execute("timeline.beat.add")
        commands.execute("media.seek", 20)
        commands.execute("timeline.beat.add")

        commands.execute("media.seek", 5)
        commands.execute("timeline.beat.add")

        # The first measure keeps two beats, so the beat at 10 starts the
        # second, which the beat at 20 fills.
        assert [b.get_data("is_first_in_measure") for b in beat_tlui] == [
            True,
            False,
            True,
            False,
        ]
        assert beat_tlui.timeline.beats_in_measure == [2, 2]

    def test_create_beat_before_the_first_starts_measure_zero(self, beat_tlui):
        for time in [10, 11, 12]:
            commands.execute("media.seek", time)
            commands.execute("timeline.beat.add")

        commands.execute("media.seek", 5)
        commands.execute("timeline.beat.add")

        assert beat_tlui.timeline.beats_in_measure == [1, 3]
        assert beat_tlui.timeline.measure_numbers == [0, 1]

    def test_create_beat_before_a_pickup_joins_it(self, beat_tlui):
        for time in [10, 11, 12, 13, 14]:
            commands.execute("media.seek", time)
            commands.execute("timeline.beat.add")
        commands.execute("media.seek", 9)
        commands.execute("timeline.beat.add")

        commands.execute("media.seek", 8)
        commands.execute("timeline.beat.add")

        assert beat_tlui.timeline.beats_in_measure == [2, 4, 1]
        assert beat_tlui.timeline.measure_numbers == [0, 1, 2]

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

        beat_tl.delete_components([beat_tl[2], beat_tl[3], beat_tl[4], beat_tl[5]])

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

    @staticmethod
    def _add_measures(beat_tl, count):
        beat_tl.set_data("beat_pattern", [1])
        for time in range(count):
            beat_tl.create_beat(time=time + 1)

    def test_change_measure_number_case1(self, beat_tl):
        self._add_measures(beat_tl, 4)
        beat_tl.set_measure_number(1, 10)
        assert beat_tl.measure_numbers == [1, 10, 11, 12]
        assert beat_tl.measures_to_force_display == [1]

    def test_change_measure_number_case2(self, beat_tl):
        self._add_measures(beat_tl, 4)
        beat_tl.set_measure_number(2, 10)
        assert beat_tl.measure_numbers == [1, 2, 10, 11]
        assert beat_tl.measures_to_force_display == [2]

    def test_number_change_stops_at_a_measure_numbered_by_hand(self, beat_tl):
        self._add_measures(beat_tl, 6)
        beat_tl.set_measure_number(4, 5)
        beat_tl.set_measure_number(2, 10)
        assert beat_tl.measure_numbers == [1, 2, 10, 11, 5, 6]
        assert beat_tl.measures_to_force_display == [2, 4]

    def test_set_measure_number_twice_forces_display_once(self, beat_tl):
        self._add_measures(beat_tl, 4)
        beat_tl.set_measure_number(1, 10)
        beat_tl.set_measure_number(1, 10)
        assert beat_tl.measures_to_force_display == [1]

    def test_reset_measure_number_unforces_display_after_repeated_sets(self, beat_tl):
        self._add_measures(beat_tl, 4)
        beat_tl.set_measure_number(1, 10)
        beat_tl.set_measure_number(1, 20)
        beat_tl.set_measure_number(1, 30)
        beat_tl.reset_measure_number(1)
        assert beat_tl.measures_to_force_display == []

    def test_deleting_measures_drops_their_forced_display(self, beat_tl):
        self._add_measures(beat_tl, 5)

        beat_tl.set_measure_number(4, 40)
        beat_tl.set_measure_number(1, 10)
        assert beat_tl.measures_to_force_display == [1, 4]

        beat_tl.delete_components([beat_tl[2], beat_tl[3], beat_tl[4]])

        assert beat_tl.measure_count == 2
        assert beat_tl.measures_to_force_display == [1]

    def test_reset_measure_number_first_measure(self, beat_tl):
        self._add_measures(beat_tl, 4)
        beat_tl.set_measure_number(0, 10)
        beat_tl.reset_measure_number(0)
        assert beat_tl.measure_numbers == [1, 2, 3, 4]

    def test_reset_measure_number_middle_measure(self, beat_tl):
        self._add_measures(beat_tl, 4)
        beat_tl.set_measure_number(1, 10)
        beat_tl.reset_measure_number(1)
        assert beat_tl.measure_numbers == [1, 2, 3, 4]

    def test_reset_measure_number_last_measure(self, beat_tl):
        self._add_measures(beat_tl, 4)
        beat_tl.set_measure_number(3, 10)
        beat_tl.reset_measure_number(3)
        assert beat_tl.measure_numbers == [1, 2, 3, 4]

    def test_set_measure_numbers_with_a_repeat(self, beat_tl):
        self._add_measures(beat_tl, 6)
        beat_tl.set_measure_numbers([1, 2, 3, 1, 2, 3])
        assert beat_tl.measure_numbers == [1, 2, 3, 1, 2, 3]
        assert [b.measure_number_override for b in beat_tl] == [
            None,
            None,
            None,
            1,
            None,
            None,
        ]

    def test_get_times_by_measure_no_beats(self, beat_tl):
        with pytest.raises(ValueError):
            beat_tl.get_time_by_measure(0)

    def test_get_times_by_measure_one_measure(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1) == [1]

    def test_get_times_by_measure_one_measures_repeating_decimal(self, beat_tl):
        beat_tl.set_data("beat_pattern", [3])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)
        beat_tl.create_beat(time=4)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1, 0) == [1]
        assert beat_tl.get_time_by_measure(1, 0.333) == [2]
        assert beat_tl.get_time_by_measure(1, 0.667) == [3]

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

    def test_get_times_by_measure_uneven_beats_time_at_beats(self, beat_tl):
        beat_tl.set_data("beat_pattern", [4])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=3)
        beat_tl.create_beat(time=7)
        beat_tl.create_beat(time=8)
        beat_tl.create_beat(time=9)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1, 0) == [1]
        assert beat_tl.get_time_by_measure(1, 0.25) == [3]
        assert beat_tl.get_time_by_measure(1, 0.5) == [7]
        assert beat_tl.get_time_by_measure(1, 0.75) == [8]

    def test_get_times_by_measure_fraction_is_1(self, beat_tl):
        # fraction == 1.0 means get the start time of the next measure
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1, 1) == [3]

    def test_get_times_by_measure_uneven_beats_time_in_between_beats(self, beat_tl):
        beat_tl.set_data("beat_pattern", [4])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=3)
        beat_tl.create_beat(time=4)
        beat_tl.create_beat(time=5)
        beat_tl.create_beat(time=6)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1, 0.125) == [2]
        assert beat_tl.get_time_by_measure(1, 0.375) == [3.5]
        assert beat_tl.get_time_by_measure(1, 0.625) == [4.5]

    def test_get_time_between_last_beat_of_measure_and_first_beat_of_next_measure(
        self, beat_tl
    ):
        beat_tl.set_data("beat_pattern", [2])
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)
        beat_tl.create_beat(time=3)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1, 0.75) == [2.5]

    def test_get_times_by_measure_index_bigger_than_max_measure(self, beat_tl):
        beat_tl.create_beat(time=1)
        beat_tl.create_beat(time=2)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(2) == []

        assert beat_tl.get_time_by_measure(999) == []

    def test_get_times_by_measure_smaller_than_min_measure_number(self, beat_tl):
        beat_tl.create_beat(time=1)

        beat_tl.recalculate_measures()
        assert beat_tl.get_time_by_measure(0) == []

        beat_tl.set_measure_number(0, 0)
        beat_tl.recalculate_measures()
        assert beat_tl.get_time_by_measure(0) == [1]

    def test_get_times_by_fraction_in_repeat_measure_number(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        for t in range(1, 13):
            beat_tl.create_beat(time=t)
        beat_tl.set_measure_numbers([1, 2, 3, 1, 2, 1])

        assert beat_tl.get_time_by_measure(1) == [1, 7, 11]
        assert beat_tl.get_time_by_measure(2, 0.5) == [4, 10]
        assert beat_tl.get_time_by_measure(2, 0.75) == [4.5, 10.5]
        assert beat_tl.get_time_by_measure(3, 0.5) == [6]
        assert beat_tl.get_time_by_measure(3, 0.75) == [6.5]
        assert beat_tl.get_time_by_measure(3, 1.0) == []
        assert beat_tl.get_time_by_measure(3, 1.0, True) == [7]

    def test_delete_beat_keeps_the_measures_lengths(self, beat_tl):
        beat_tl.beat_pattern = [2]
        for time in range(5):
            beat_tl.create_beat(time)

        beat_tl.delete_components([beat_tl[1]])

        assert [b.get_data("is_first_in_measure") for b in beat_tl] == [
            True,
            False,
            True,
            False,
        ]
        assert beat_tl.beats_in_measure == [2, 2]

    def test_delete_first_beat_of_a_measure_keeps_its_number(self, beat_tl):
        beat_tl.beat_pattern = [2]
        for time in range(5):
            beat_tl.create_beat(time)
        beat_tl.set_measure_number(1, 10)

        beat_tl.delete_components([beat_tl[2]])

        assert beat_tl.beats_in_measure == [2, 2]
        assert beat_tl.measure_numbers == [1, 10]
        assert beat_tl[2].measure_number_override == 10

    def test_delete_every_beat_of_a_measure_removes_it(self, beat_tl):
        beat_tl.beat_pattern = [2]
        for time in range(7):
            beat_tl.create_beat(time)
        beat_tl.set_measure_number(2, 10)

        beat_tl.delete_components([beat_tl[2], beat_tl[3]])

        assert beat_tl.beats_in_measure == [2, 2, 1]
        assert beat_tl.measure_numbers == [1, 10, 11]

    @pytest.mark.timeout(5)
    def test_open_file_with_many_beats(self, resources, tilia):
        commands.execute("file.open", path=resources / "tla" / "many_beats.tla")

        assert len(tilia.timelines[0]) == 1000

    @pytest.mark.timeout(5)
    def test_scale_timeline_with_many_beats(self, resources, tilia, tilia_state):
        commands.execute("file.open", path=resources / "tla" / "many_beats.tla")
        tilia_state.set_duration(2000, scale_timelines="yes")

        assert len(tilia.timelines[0]) == 1000
        assert tilia.timelines[0][-1].get_data("time") == 1998.0

    @pytest.mark.timeout(5)
    def test_crop_timeline_with_many_beats(self, resources, tilia, tilia_state):
        commands.execute("file.open", path=resources / "tla" / "many_beats.tla")
        tilia_state.set_duration(10, scale_timelines="no")

        assert len(tilia.timelines[0]) == 11
        assert tilia.timelines[0][-1].get_data("time") == 10

    @staticmethod
    def _add_beats(times):
        for time in times:
            commands.execute("media.seek", time)
            commands.execute("timeline.beat.add")

    def test_insert_beats_after_deleting_all_beats(self, beat_tlui):
        self._add_beats(range(8))

        beat_tlui.select_all_elements()
        commands.execute("timeline.component.delete")

        # An emptied timeline must not keep a measure structure describing
        # beats that no longer exist.
        assert beat_tlui.timeline.beats_in_measure == []
        assert beat_tlui.timeline.measure_numbers == []

        self._add_beats(range(8))

        assert beat_tlui.timeline.beats_in_measure == [4, 4]
        assert [
            i for i, b in enumerate(beat_tlui) if b.get_data("is_first_in_measure")
        ] == [0, 4]

    def test_insert_beats_after_deleting_some_beats(self, beat_tlui):
        self._add_beats(range(8))

        for element in list(beat_tlui)[4:]:
            beat_tlui.select_element(element)
        commands.execute("timeline.component.delete")

        assert beat_tlui.timeline.beats_in_measure == [4]

        self._add_beats(range(8, 12))

        assert beat_tlui.timeline.beats_in_measure == [4, 4]
        assert [
            i for i, b in enumerate(beat_tlui) if b.get_data("is_first_in_measure")
        ] == [0, 4]

    def test_undo_redo_delete_all_beats(self, beat_tlui):
        self._add_beats(range(8))

        beat_tlui.select_all_elements()
        with undoable():
            commands.execute("timeline.component.delete")

    def test_delete_keeps_an_outer_bulk_change_in_place(self, beat_tlui):
        # BeatTLComponentManager.restore_state makes a whole delete-then-create
        # pass a bulk change, and reaches delete_components in the middle of
        # it. Ending the bulk change there would place every beat the restore
        # re-creates afterwards as if a user had added it.
        self._add_beats(range(8))
        timeline = beat_tlui.timeline
        component_manager = timeline.component_manager

        with component_manager.bulk():
            timeline.delete_components(list(timeline.components)[4:])

            assert component_manager.is_bulk is True

        assert component_manager.is_bulk is False

    def test_bulk_change_ends_when_its_body_raises(self, beat_tlui):
        # Leaving the flag on would stop every beat created later in the
        # session from being placed in a measure.
        component_manager = beat_tlui.timeline.component_manager

        with pytest.raises(ValueError):
            with component_manager.bulk():
                raise ValueError

        assert component_manager.is_bulk is False

    def test_crop_recalculates_measures(self, beat_tlui, tilia_state):
        beat_tlui.timeline.set_data("beat_pattern", [2, 3])
        self._add_beats(range(10))
        beat_tlui.timeline.set_measure_number(3, 20)

        tilia_state.set_duration(5.5, scale_timelines="no")

        timeline = beat_tlui.timeline
        assert len(timeline) == 6
        assert timeline.beats_in_measure == [2, 3, 1]
        assert timeline.measure_numbers == [1, 2, 3]
        assert timeline.measures_to_force_display == []
        assert [b.is_first_in_measure for b in timeline] == [
            True,
            False,
            True,
            False,
            False,
            True,
        ]

    def test_shrinking_media_drops_measures_for_cropped_beats(
        self, beat_tlui, tilia_state
    ):
        tilia_state.duration = 100
        self._add_beats(range(12))

        assert beat_tlui.timeline.beats_in_measure == [4, 4, 4]

        tilia_state.set_duration(7.5, scale_timelines="no")

        # The measure structure has to shrink with the beats. Leaving a third
        # measure behind makes measure_count over-report, makes
        # get_time_by_measure interpolate against a partition that no longer
        # exists, and makes "Distribute beats" on the last measure raise.
        assert len(beat_tlui) == 8
        assert beat_tlui.timeline.beats_in_measure == [4, 4]

    def test_clearing_the_timeline_drops_the_measure_structure(self, beat_tlui):
        self._add_beats(range(12))

        assert beat_tlui.timeline.beats_in_measure == [4, 4, 4]

        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", beat_tlui)

        assert len(beat_tlui) == 0
        assert beat_tlui.timeline.beats_in_measure == []
        assert beat_tlui.timeline.measure_numbers == []


class TestGetExtensionFromBeatPattern:
    def test_starting_measure_emptier_than_beat_pattern(self):
        extension = BeatTimeline.get_extension_from_beat_pattern(
            [4], 3, beats_on_starting_measure=2
        )
        assert extension == [2, 1]

    def test_starting_measure_as_full_as_beat_pattern(self):
        extension = BeatTimeline.get_extension_from_beat_pattern(
            [4], 3, beats_on_starting_measure=4
        )
        assert extension == [3]

    def test_starting_measure_fuller_than_beat_pattern(self):
        """ "Set amount in measure" can put more beats in a measure than the
        beat pattern prescribes for it. There is nothing left to fill in that
        case, so the extension has to start a new measure.
        """
        extension = BeatTimeline.get_extension_from_beat_pattern(
            [4], 3, beats_on_starting_measure=5
        )
        assert extension == [3]


def load_beat_timeline(tls, beats_in_measure, measure_numbers, times=None):
    """A beat timeline as TiLiA loads it from a file, with a beat every second
    from 1 s, or at `times`."""
    times = times or [i + 1 for i in range(sum(beats_in_measure))]
    components = {i: {"kind": "BEAT", "time": time} for i, time in enumerate(times)}
    return tls.create_timeline(
        BeatTimeline,
        components,
        beats_in_measure=beats_in_measure,
        measure_numbers=measure_numbers,
    )


class TestGetTimeByMeasureEachPass:
    """One time for each pass through a measure, at the fraction of that pass's
    own beats."""

    def test_last_measure_between_its_beats(self, tls):
        beat_tl = load_beat_timeline(tls, [4, 4], [1, 2])

        assert beat_tl.get_time_by_measure(2, 0.5) == [7]
        assert beat_tl.get_time_by_measure(2, 0.75) == [8]

    def test_passes_with_different_beat_counts(self, tls):
        beat_tl = load_beat_timeline(tls, [4, 4, 3, 4, 2], [1, 2, 1, 2, 3])

        assert beat_tl.get_time_by_measure(1, 0.5) == [3, 10.5]

    def test_passes_with_different_beat_counts_between_beats(self, tls):
        beat_tl = load_beat_timeline(tls, [4, 4, 3, 4, 2], [1, 2, 1, 2, 3])

        assert beat_tl.get_time_by_measure(1, 0.4) == pytest.approx([2.6, 10.2])

    def test_fraction_between_beats_is_not_rounded(self, tls):
        beat_tl = load_beat_timeline(tls, [3, 1], [1, 2])

        assert beat_tl.get_time_by_measure(1, 0.5) == [2.5]

    def test_measure_that_does_not_exist(self, tls):
        beat_tl = load_beat_timeline(tls, [2, 2, 2, 2], [1, 2, 4, 5])

        assert beat_tl.get_time_by_measure(3) == []
        assert beat_tl.get_time_by_measure(3, 0.5) == []
        assert beat_tl.get_time_by_measure(3, 0, True) == []
        assert beat_tl.get_time_by_measure(6, 0, True) == []

    def test_fraction_1_is_next_downbeat_only_if_next_measure_number_follows(self, tls):
        beat_tl = load_beat_timeline(tls, [2] * 6, [1, 2, 3, 2, 3, 4])

        assert beat_tl.get_time_by_measure(1, 1) == [3]
        assert beat_tl.get_time_by_measure(3, 1) == [11]

    def test_fraction_1_at_segment_end_is_end_of_each_pass(self, tls):
        beat_tl = load_beat_timeline(tls, [2] * 6, [1, 2, 3, 2, 3, 4])

        assert beat_tl.get_time_by_measure(1, 1, True) == [3]
        assert beat_tl.get_time_by_measure(3, 1, True) == [7, 11]

    def test_last_pass_lasts_past_last_beat(self, tls):
        beat_tl = load_beat_timeline(tls, [2] * 6, [1, 2, 3, 1, 2, 1])

        assert beat_tl.get_time_by_measure(1, 0.75) == [2.5, 8.5, 12.5]
        assert beat_tl.get_time_by_measure(1, 1, True) == [3, 9, 13]

    def test_segment_end_on_downbeat_includes_end_of_previous_measure(self, tls):
        beat_tl = load_beat_timeline(tls, [2] * 6, [1, 2, 3, 1, 2, 1])

        assert beat_tl.get_time_by_measure(3, 0, True) == [5, 11]

    def test_segment_end_on_downbeat_after_passes_with_different_beat_counts(self, tls):
        beat_tl = load_beat_timeline(tls, [2, 2, 2, 3, 2], [1, 2, 1, 2, 3])

        assert beat_tl.get_time_by_measure(3, 0, True) == [5, 10]

    def test_one_beat(self, tls):
        beat_tl = load_beat_timeline(tls, [1], [0])

        assert beat_tl.get_time_by_measure(0) == [1]
        assert beat_tl.get_time_by_measure(0, 0, True) == [1]
        assert beat_tl.get_time_by_measure(0, 0.5) == []
        assert beat_tl.get_time_by_measure(0, 1) == []
        assert beat_tl.get_time_by_measure(0, 1, True) == []

    def test_fraction_that_rounds_to_1_before_a_jump(self, tls):
        beat_tl = load_beat_timeline(tls, [2, 2, 2, 2], [1, 2, 4, 5])

        assert beat_tl.get_time_by_measure(2.0, 0.9996) == []

    def test_measure_number_past_the_last_measure(self, tls):
        # Only a hand-edited or buggy file has more numbers than measures.
        beat_tl = load_beat_timeline(tls, [2, 2], [1, 2, 3, 4])

        assert beat_tl.get_time_by_measure(2, 0.5) == [4]
        assert beat_tl.get_time_by_measure(3) == []
        assert beat_tl.get_time_by_measure(3, 0.5) == []
        assert beat_tl.get_time_by_measure(3, 1, True) == []

    @pytest.mark.parametrize(
        "beats_in_measure, measure_numbers, expected",
        [
            pytest.param(
                [2, 2, 2], [1, 3, 1, 2], [3, 7], id="not the number just below"
            ),
            pytest.param(
                [2, 2], [1, 3, 1, 4], [3], id="not a pass of the number below"
            ),
        ],
    )
    def test_segment_end_with_measure_number_past_the_last_measure(
        self, tls, beats_in_measure, measure_numbers, expected
    ):
        beat_tl = load_beat_timeline(tls, beats_in_measure, measure_numbers)

        assert beat_tl.get_time_by_measure(3, 0, True) == expected


class TestLastMeasureEnd:
    """The last beat lasts as long as the gap before it."""

    def test_steady_measure(self, tls):
        beat_tl = load_beat_timeline(tls, [4, 4], [1, 2])

        assert beat_tl.get_time_by_measure(2, 1, True) == [9]

    def test_measure_longer_than_the_one_before(self, tls):
        beat_tl = load_beat_timeline(tls, [3, 4], [1, 2])

        assert beat_tl.get_time_by_measure(2, 1, True) == [8]
        assert beat_tl.get_time_by_measure(2, 0.875) == [7.5]

    def test_measure_shorter_than_the_one_before(self, tls):
        beat_tl = load_beat_timeline(tls, [2, 1], [1, 2])

        assert beat_tl.get_time_by_measure(2, 1, True) == [4]
        assert beat_tl.get_time_by_measure(2, 0.5) == [3.5]

    @pytest.mark.parametrize("beats_in_last_measure", [4, 40])
    def test_times_never_run_backwards(self, tls, beats_in_last_measure):
        beat_tl = load_beat_timeline(tls, [2, beats_in_last_measure], [1, 2])

        steps = 2 * beats_in_last_measure
        times = [beat_tl.get_time_by_measure(2, i / steps)[0] for i in range(steps)]
        times += beat_tl.get_time_by_measure(2, 1, True)

        assert times == sorted(set(times))

    def test_one_measure_of_two_beats_has_an_end(self, tls):
        beat_tl = load_beat_timeline(tls, [2], [1])

        assert beat_tl.get_time_by_measure(1, 1, True) == [3]
        assert beat_tl.get_time_by_measure(1, 0.75) == [2.5]


class TestLastMeasureEndsAtTheMediaEnd:
    """A last measure's end stops at the media's end."""

    def test_segment_end(self, tls, tilia_state):
        tilia_state.duration = 4.5
        beat_tl = load_beat_timeline(tls, [2, 2], [1, 2])

        assert beat_tl.get_time_by_measure(2, 1, True) == [4.5]

    def test_time_after_the_last_beat_is_interpolated_up_to_it(self, tls, tilia_state):
        tilia_state.duration = 4.5
        beat_tl = load_beat_timeline(tls, [2, 2], [1, 2])

        assert beat_tl.get_time_by_measure(2, 0.75) == [4.25]

    def test_time_up_to_the_last_beat_does_not_change(self, tls, tilia_state):
        tilia_state.duration = 4.5
        beat_tl = load_beat_timeline(tls, [2, 2], [1, 2])

        assert beat_tl.get_time_by_measure(2, 0) == [3]
        assert beat_tl.get_time_by_measure(2, 0.25) == [3.5]
        assert beat_tl.get_time_by_measure(2, 0.5) == [4]

    def test_end_of_the_last_pass_as_a_segment_end_on_a_downbeat(
        self, tls, tilia_state
    ):
        tilia_state.duration = 6.5
        beat_tl = load_beat_timeline(tls, [2, 2, 2], [1, 2, 1])

        assert beat_tl.get_time_by_measure(2, 0, True) == [3, 6.5]

    def test_end_before_the_media_end_does_not_change(self, tls, tilia_state):
        tilia_state.duration = 10
        beat_tl = load_beat_timeline(tls, [2, 2], [1, 2])

        assert beat_tl.get_time_by_measure(2, 1, True) == [5]
        assert beat_tl.get_time_by_measure(2, 0.75) == [4.5]

    def test_end_at_the_media_end(self, tls, tilia_state):
        tilia_state.duration = 5
        beat_tl = load_beat_timeline(tls, [2, 2], [1, 2])

        assert beat_tl.get_time_by_measure(2, 1, True) == [5]

    def test_measure_before_the_last_keeps_its_end(self, tls, tilia_state):
        tilia_state.duration = 4.5
        beat_tl = load_beat_timeline(tls, [2, 2], [1, 2])

        assert beat_tl.get_time_by_measure(1, 1, True) == [3]

    def test_one_measure_of_two_beats(self, tls, tilia_state):
        tilia_state.duration = 2.5
        beat_tl = load_beat_timeline(tls, [2], [1])

        assert beat_tl.get_time_by_measure(1, 1, True) == [2.5]
        assert beat_tl.get_time_by_measure(1, 0.75) == [2.25]


class TestLastMeasureNeverEndsBeforeItsLastBeat:
    """A last measure ends at max(last beat, min(last beat + gap, media's end))."""

    @staticmethod
    def _load(tls, tilia_state, duration, beats_in_measure, measure_numbers):
        """Loaded with the media's end on or past the last beat, as a file is, and
        then shorter, as when a media reports a slightly shorter length: TiLiA
        keeps the timeline as it is (DURATION_JITTER_TOLERANCE)."""
        last_beat = sum(beats_in_measure)
        tilia_state.duration = max(duration, last_beat)
        beat_tl = load_beat_timeline(tls, beats_in_measure, measure_numbers)
        tilia_state.set_duration(duration, scale_timelines="keep")
        return beat_tl

    @pytest.mark.parametrize(
        "duration, end, at_three_quarters",
        [(3, 3, 3), (2.5, 3, 3), (12, 4, 3.25)],
        ids=["on the last beat", "before the last beat", "long after it"],
    )
    def test_end(self, tls, tilia_state, duration, end, at_three_quarters):
        beat_tl = self._load(tls, tilia_state, duration, [3], [1])

        assert beat_tl[-1].time == 3
        assert beat_tl.get_time_by_measure(1, 0.75) == [at_three_quarters]
        assert beat_tl.get_time_by_measure(1, 1, True) == [end]
        assert beat_tl.get_time_by_measure(1, 1) == []

    @pytest.mark.parametrize("duration", [8, 7.95, 6.5])
    def test_times_never_run_backwards(self, tls, tilia_state, duration):
        beat_tl = self._load(tls, tilia_state, duration, [4, 4], [1, 2])

        times = [beat_tl.get_time_by_measure(2, i / 16)[0] for i in range(16)]
        times += beat_tl.get_time_by_measure(2, 1, True)

        assert times == sorted(times)
        assert times[-1] == 8

    def test_end_of_the_last_pass_as_a_segment_end_on_a_downbeat(
        self, tls, tilia_state
    ):
        beat_tl = self._load(tls, tilia_state, 5.5, [2, 2, 2], [1, 2, 1])

        assert beat_tl.get_time_by_measure(2, 0, True) == [3, 6]

    def test_measure_before_the_last_keeps_its_end(self, tls, tilia_state):
        beat_tl = self._load(tls, tilia_state, 3.5, [2, 2], [1, 2])

        assert beat_tl.get_time_by_measure(1, 1, True) == [3]


class TestSharedExamplesOfTheLastMeasure:
    """TimeLineAnnotator/desktop#828 (closing taps) adds these four to the core's
    shared examples. This branch has neither that file nor its app-side test, so
    the cases are here, with the same beats, media, questions and answers."""

    @pytest.mark.parametrize(
        "fraction, is_segment_end, expected",
        [(0.75, False, 5.75), (1, True, 6)],
        ids=["past its last beat", "as a segment's end"],
    )
    def test_a_last_bar_that_isnt_steady(self, tls, fraction, is_segment_end, expected):
        beat_tl = load_beat_timeline(tls, [4, 2], [1, 2], [1, 2, 3, 4, 5, 5.5])

        assert beat_tl.get_time_by_measure(2, fraction, is_segment_end) == [expected]

    @pytest.mark.parametrize(
        "fraction, is_segment_end, expected",
        [(0.75, False, 3), (1, True, 3)],
        ids=["past it", "as a segment's end"],
    )
    def test_a_last_beat_at_the_medias_end(
        self, tls, tilia_state, fraction, is_segment_end, expected
    ):
        tilia_state.duration = 3
        beat_tl = load_beat_timeline(tls, [3], [1])

        assert beat_tl.get_time_by_measure(1, fraction, is_segment_end) == [expected]


class TestAddMeasureZero:
    def test_timeline_with_no_measure_2(self, tls):
        beat_tl = load_beat_timeline(tls, [2, 2, 2], [1, 3, 4])

        assert beat_tl.add_measure_zero(0.25) == (True, "")

        # A quarter of the first measure, which lasts 2 s, before its 1 s.
        assert beat_tl[0].time == 0.5
        assert beat_tl.measure_numbers[0] == 0
        assert beat_tl.beats_in_measure[0] == 1

    def test_first_measure_is_not_measure_1(self, tls):
        beat_tl = load_beat_timeline(tls, [2, 2, 2], [5, 1, 2])

        assert beat_tl.add_measure_zero(0.25) == (True, "")

        assert beat_tl[0].time == 0.5
        assert beat_tl.measure_numbers[0] == 0
        assert beat_tl.beats_in_measure[0] == 1

    def test_not_enough_space_before_the_first_measure(self, tls):
        beat_tl = load_beat_timeline(tls, [2, 2, 2], [1, 3, 4])

        success, _ = beat_tl.add_measure_zero(1)

        assert not success
        assert len(beat_tl) == 6
