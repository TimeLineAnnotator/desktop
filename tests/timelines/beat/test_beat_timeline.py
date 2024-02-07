import functools
import itertools
from unittest.mock import MagicMock
import pytest
import logging

from tilia.requests import Get, serve, stop_serving_all
from tilia.timelines.beat.timeline import BeatTLComponentManager, BeatTimeline
from tilia.timelines.collection import Timelines
from tilia.timelines.component_kinds import ComponentKind

logger = logging.getLogger(__name__)


class DummyTimelines(Timelines):
    def __init__(self):
        pass


ID_ITER = itertools.count()


@pytest.fixture
def beat_tl():
    cm = BeatTLComponentManager()
    serve(
        "beat_tl", Get.ID, lambda: next(ID_ITER)
    )  # required for timeline and component instancing
    serve(
        "beat_tl", Get.ORDINAL_FOR_NEW_TIMELINE, lambda: 1
    )  # required for timeline instancing
    serve(
        "beat_tl", Get.MEDIA_DURATION, lambda: 100
    )  # required for component validation

    _beat_tl = BeatTimeline(component_manager=cm, beat_pattern=[2])

    _beat_tl.create_timeline_component = functools.partial(
        _beat_tl.create_timeline_component, kind=ComponentKind.BEAT
    )

    _beat_tl.ui = MagicMock()
    cm.associate_to_timeline(_beat_tl)
    yield _beat_tl
    _beat_tl.delete()
    stop_serving_all("beat_tl")


class TestBeatTimeline:
    def test_get_extension_mult_of_bp_without_beats_in_measure(self, beat_tl):
        beat_tl.beat_pattern = [4, 3, 2]
        assert beat_tl._get_beats_in_measure_extension(9) == [4, 3, 2]
        assert beat_tl._get_beats_in_measure_extension(18) == [4, 3, 2, 4, 3, 2]
        result_for_27 = [4, 3, 2, 4, 3, 2, 4, 3, 2]

        assert beat_tl._get_beats_in_measure_extension(27) == result_for_27

    def test_get_extension_mult_of_bp_with_beats_in_measure(self, beat_tl):
        beat_tl.beat_pattern = [4, 3, 2]
        beat_tl.beats_in_measure = [4, 3, 2]

        assert beat_tl._get_beats_in_measure_extension(9) == [4, 3, 2]
        assert beat_tl._get_beats_in_measure_extension(18) == [4, 3, 2, 4, 3, 2]
        result_for_27 = [4, 3, 2, 4, 3, 2, 4, 3, 2]
        assert beat_tl._get_beats_in_measure_extension(27) == result_for_27

    def test_get_extension_mult_of_bp_with_beats_in_measure_incomplete_pattern1(
        self, beat_tl
    ):
        beat_tl.beat_pattern = [4, 3, 2]
        beat_tl.beats_in_measure = [4, 3]

        assert beat_tl._get_beats_in_measure_extension(9) == [2, 4, 3]
        assert beat_tl._get_beats_in_measure_extension(18) == [2, 4, 3, 2, 4, 3]
        result_for_27 = [2, 4, 3, 2, 4, 3, 2, 4, 3]
        assert beat_tl._get_beats_in_measure_extension(27) == result_for_27

        beat_tl.beats_in_measure = [4]

        assert beat_tl._get_beats_in_measure_extension(9) == [3, 2, 4]
        assert beat_tl._get_beats_in_measure_extension(18) == [3, 2, 4, 3, 2, 4]
        result_for_27 = [3, 2, 4, 3, 2, 4, 3, 2, 4]
        assert beat_tl._get_beats_in_measure_extension(27) == result_for_27

    def test_get_extension_mult_of_bp_with_beats_in_measure_incomplete_measure(
        self, beat_tl
    ):
        beat_tl.beat_pattern = [4, 3, 2]
        beat_tl.beats_in_measure = [4, 3, 1]

        assert beat_tl._get_beats_in_measure_extension(9) == [1, 4, 3, 1]
        assert beat_tl._get_beats_in_measure_extension(18) == [1, 4, 3, 2, 4, 3, 1]
        result_for_27 = [1, 4, 3, 2, 4, 3, 2, 4, 3, 1]
        assert beat_tl._get_beats_in_measure_extension(27) == result_for_27

    def test_get_extension_multiple_of_beat_pattern_sum(self, beat_tl):
        beat_tl.beat_pattern = [4, 3, 2]
        assert beat_tl._get_beats_in_measure_extension(9) == [4, 3, 2]
        assert beat_tl._get_beats_in_measure_extension(18) == [4, 3, 2, 4, 3, 2]
        result_for_27 = [4, 3, 2, 4, 3, 2, 4, 3, 2]
        assert beat_tl._get_beats_in_measure_extension(27) == result_for_27

    def test_get_extension_not_multiple_of_beat_pattern_sum(self, beat_tl):
        beat_tl.beat_pattern = [4, 3, 2]
        assert beat_tl._get_beats_in_measure_extension(10) == [4, 3, 2, 1]
        assert beat_tl._get_beats_in_measure_extension(11) == [4, 3, 2, 2]
        assert beat_tl._get_beats_in_measure_extension(12) == [4, 3, 2, 3]

    def test_get_extension_amount_zero(self, beat_tl):
        assert beat_tl._get_beats_in_measure_extension(0) == []

    def test_get_extension_single_element_beat_pattern(self, beat_tl):
        beat_tl.beat_pattern = [4]
        assert beat_tl._get_beats_in_measure_extension(8) == [4, 4]
        assert beat_tl._get_beats_in_measure_extension(9) == [4, 4, 1]
        assert beat_tl._get_beats_in_measure_extension(1) == [1]

    def test_get_extension_single_element_bp_with_beats_in_measure(self, beat_tl):
        beat_tl.beat_pattern = [4]
        beat_tl.beats_in_measure = [4]
        assert beat_tl._get_beats_in_measure_extension(8) == [4, 4]
        assert beat_tl._get_beats_in_measure_extension(9) == [4, 4, 1]
        assert beat_tl._get_beats_in_measure_extension(1) == [1]

    def test_get_extension_single_element_bp_with_bim_incomplete_measure(self, beat_tl):
        beat_tl.beat_pattern = [4]
        beat_tl.beats_in_measure = [3]
        assert beat_tl._get_beats_in_measure_extension(8) == [1, 4, 3]
        assert beat_tl._get_beats_in_measure_extension(9) == [1, 4, 4]
        assert beat_tl._get_beats_in_measure_extension(1) == [1]
        assert beat_tl._get_beats_in_measure_extension(2) == [1, 1]

    def test_get_extension_empty_beat_pattern(self, beat_tl):
        # test when beat_pattern is empty
        beat_tl.beat_pattern = []
        with pytest.raises(ValueError):
            beat_tl._get_beats_in_measure_extension(8)

    def test_recalculate_measures_added_one_measure(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        beat_tl.create_timeline_component(time=2)

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measures_added_one_beat(self, beat_tl):
        beat_tl.create_timeline_component(time=1)

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [1]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measure_added_one_measure_and_a_beat(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        beat_tl.create_timeline_component(time=2)
        beat_tl.create_timeline_component(time=3)

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 1]
        assert beat_tl.measure_numbers == [1, 2]

    def test_recalculate_measure_added_two_measures(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        beat_tl.create_timeline_component(time=2)
        beat_tl.create_timeline_component(time=3)
        beat_tl.create_timeline_component(time=4)

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 2]
        assert beat_tl.measure_numbers == [1, 2]

    def test_recalculate_measures_added_one_beat_to_incomplete_measure_1(self, beat_tl):
        """Measure gets completed in this case."""
        beat_tl.create_timeline_component(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_timeline_component(time=2)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measures_added_one_beat_to_incomplete_measure_2(self, beat_tl):
        """Measure does not get completed in this case."""
        beat_tl.beat_pattern = [4]

        beat_tl.create_timeline_component(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_timeline_component(time=2)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measures_added_one_measure_to_incomplete_measure(
        self, beat_tl
    ):
        beat_tl.create_timeline_component(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_timeline_component(time=2)
        beat_tl.create_timeline_component(time=3)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 1]
        assert beat_tl.measure_numbers == [1, 2]

    def test_recalculate_measures_added_measure_and_beat_to_incomplete_measure(
        self, beat_tl
    ):
        beat_tl.create_timeline_component(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_timeline_component(time=2)
        beat_tl.create_timeline_component(time=3)
        beat_tl.create_timeline_component(time=4)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 2]
        assert beat_tl.measure_numbers == [1, 2]

    def test_recalculate_measures_added_two_measures_to_incomplete_measure(
        self, beat_tl
    ):
        beat_tl.create_timeline_component(time=1)
        beat_tl.recalculate_measures()

        beat_tl.create_timeline_component(time=2)
        beat_tl.create_timeline_component(time=3)
        beat_tl.create_timeline_component(time=4)
        beat_tl.create_timeline_component(time=5)
        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 2, 1]
        assert beat_tl.measure_numbers == [1, 2, 3]

    def test_reduce_beats_in_measure_last_element(self, beat_tl):
        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(1)
        assert beat_tl.beats_in_measure == [4, 3, 1]

        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(2)
        assert beat_tl.beats_in_measure == [4, 3]

    def test_reduce_beats_in_measure_multiple_elements(self, beat_tl):
        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(3)
        assert beat_tl.beats_in_measure == [4, 2]

        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(4)
        assert beat_tl.beats_in_measure == [4, 1]

        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(5)
        assert beat_tl.beats_in_measure == [4]

        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(6)
        assert beat_tl.beats_in_measure == [3]

        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(7)
        assert beat_tl.beats_in_measure == [2]

        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(8)
        assert beat_tl.beats_in_measure == [1]

        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(9)
        assert beat_tl.beats_in_measure == []

    def test_reduce_beats_in_measure_more_than_available(self, beat_tl):
        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.reduce_beats_in_measure(13)
        assert beat_tl.beats_in_measure == []

    def test_recalculate_measures_removed_one_measure(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        beat_tl.create_timeline_component(time=2)
        b1 = beat_tl.create_timeline_component(time=3)
        b2 = beat_tl.create_timeline_component(time=4)

        beat_tl.recalculate_measures()

        beat_tl.on_request_to_delete_components([b1, b2])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measures_removed_one_beat(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        b1 = beat_tl.create_timeline_component(time=2)

        beat_tl.recalculate_measures()

        beat_tl.on_request_to_delete_components([b1])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [1]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measure_removed_one_measure_and_a_beat(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        b1 = beat_tl.create_timeline_component(time=2)
        b2 = beat_tl.create_timeline_component(time=3)
        b3 = beat_tl.create_timeline_component(time=4)

        beat_tl.recalculate_measures()

        beat_tl.on_request_to_delete_components([b1, b2, b3])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [1]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measure_removed_two_measures(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        beat_tl.create_timeline_component(time=2)
        b0 = beat_tl.create_timeline_component(time=3)
        b1 = beat_tl.create_timeline_component(time=4)
        b2 = beat_tl.create_timeline_component(time=5)
        b3 = beat_tl.create_timeline_component(time=6)

        beat_tl.recalculate_measures()

        beat_tl.on_request_to_delete_components([b0, b1, b2, b3])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2]
        assert beat_tl.measure_numbers == [1]

    def test_recalculate_measure_first_beat_from_last_measure(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        beat_tl.create_timeline_component(time=2)
        b = beat_tl.create_timeline_component(time=3)
        beat_tl.create_timeline_component(time=4)

        beat_tl.recalculate_measures()

        beat_tl.on_request_to_delete_components([b])

        beat_tl.recalculate_measures()

        assert beat_tl.beats_in_measure == [2, 1]
        assert beat_tl.measure_numbers == [1, 2]

    def test_update_beats_that_start_measures(self, beat_tl):
        beat_tl.beats_in_measure = [4]
        beat_tl.update_beats_that_start_measures()
        assert beat_tl.beats_that_start_measures == [0]

        beat_tl.beats_in_measure = [4, 3]
        beat_tl.update_beats_that_start_measures()
        assert beat_tl.beats_that_start_measures == [0, 4]

        beat_tl.beats_in_measure = [4, 3, 2]
        beat_tl.update_beats_that_start_measures()
        assert beat_tl.beats_that_start_measures == [0, 4, 7]

        beat_tl.beats_in_measure = [4, 3, 2, 1]
        beat_tl.update_beats_that_start_measures()
        assert beat_tl.beats_that_start_measures == [0, 4, 7, 9]

    def test_display_measure_number_bool_array(self, beat_tl):
        beat_tl.beats_in_measure = [0] * 3
        beat_tl.measures_to_force_display = set()
        beat_tl.DISPLAY_MEASURE_NUMBER_PERIOD = 2
        assert beat_tl.display_measure_number_bool_array == [True, False, True]

        beat_tl.beats_in_measure = [0] * 3
        beat_tl.measures_to_force_display = {1}
        beat_tl.DISPLAY_MEASURE_NUMBER_PERIOD = 2
        assert beat_tl.display_measure_number_bool_array == [True, True, True]

        beat_tl.beats_in_measure = [0] * 5
        beat_tl.measures_to_force_display = {1}
        beat_tl.DISPLAY_MEASURE_NUMBER_PERIOD = 2
        assert beat_tl.display_measure_number_bool_array == [
            True,
            True,
            True,
            False,
            True,
        ]

        beat_tl.beats_in_measure = [0] * 3
        beat_tl.measures_to_force_display = set()
        beat_tl.DISPLAY_MEASURE_NUMBER_PERIOD = 3
        assert beat_tl.display_measure_number_bool_array == [True, False, False]

        beat_tl.beats_in_measure = [0] * 3
        beat_tl.measures_to_force_display = {2}
        beat_tl.DISPLAY_MEASURE_NUMBER_PERIOD = 3
        assert beat_tl.display_measure_number_bool_array == [True, False, True]

        beat_tl.beats_in_measure = [0] * 5
        beat_tl.measures_to_force_display = {2}
        beat_tl.DISPLAY_MEASURE_NUMBER_PERIOD = 3
        assert beat_tl.display_measure_number_bool_array == [
            True,
            False,
            True,
            True,
            False,
        ]

        beat_tl.beats_in_measure = [0] * 1
        beat_tl.measures_to_force_display = set()
        beat_tl.DISPLAY_MEASURE_NUMBER_PERIOD = 3
        assert beat_tl.display_measure_number_bool_array == [True]

    def test_change_measure_number_case1(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.change_measure_number(1, 10)
        assert beat_tl.measure_numbers == [1, 10, 11, 12]
        assert beat_tl.measures_to_force_display == [1]

    def test_change_measure_number_case2(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.change_measure_number(2, 10)
        assert beat_tl.measure_numbers == [1, 2, 10, 11]
        assert beat_tl.measures_to_force_display == [2]

    def test_propagate_number_change_stops_at_forced_display(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4, 5, 6]
        beat_tl.measures_to_force_display = [4]
        beat_tl.change_measure_number(2, 10)
        assert beat_tl.measure_numbers == [1, 2, 10, 11, 5, 6]
        assert beat_tl.measures_to_force_display == [4, 2]

    def test_reset_measure_number_first_measure(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.change_measure_number(0, 10)
        beat_tl.reset_measure_number(0)
        beat_tl.measure_numbers = [1, 2, 3, 4]

    def test_reset_measure_number_middle_measure(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.change_measure_number(1, 10)
        beat_tl.reset_measure_number(1)
        beat_tl.measure_numbers = [1, 2, 3, 4]

    def test_reset_measure_number_last_measure(self, beat_tl):
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.change_measure_number(3, 10)
        beat_tl.reset_measure_number(3)
        beat_tl.measure_numbers = [1, 2, 3, 4]

    def test_change_beats_in_measure(self, beat_tl):
        beat_tl.beats_in_measure = [3, 3, 3, 3]
        beat_tl.measure_numbers = [1, 2, 3, 4]
        beat_tl.component_manager._components = [None] * 12
        beat_tl.component_manager.update_beat_uis = lambda: None
        beat_tl.component_manager.clear = lambda: None
        beat_tl.change_beats_in_measure(1, 4)
        assert beat_tl.beats_in_measure == [3, 4, 3, 2]
        assert beat_tl.measure_numbers == [1, 2, 3, 4]

        beat_tl.change_beats_in_measure(0, 4)
        assert beat_tl.beats_in_measure == [4, 4, 3, 1]
        assert beat_tl.measure_numbers == [1, 2, 3, 4]

        beat_tl.change_beats_in_measure(3, 2)
        assert beat_tl.beats_in_measure == [4, 4, 3, 1]
        assert beat_tl.measure_numbers == [1, 2, 3, 4]

        beat_tl.change_beats_in_measure(2, 4)
        assert beat_tl.beats_in_measure == [4, 4, 4]
        assert beat_tl.measure_numbers == [1, 2, 3]

        beat_tl.change_beats_in_measure(0, 12)
        assert beat_tl.beats_in_measure == [12]
        assert beat_tl.measure_numbers == [1]

    def test_get_times_by_measure_no_beats(self, beat_tl):
        with pytest.raises(ValueError):
            beat_tl.get_time_by_measure(0)

    def test_get_times_by_measure_one_measure(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        beat_tl.create_timeline_component(time=2)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1) == [1]

    def test_get_times_by_measure_multiple_measures(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        beat_tl.create_timeline_component(time=2)
        beat_tl.create_timeline_component(time=3)
        beat_tl.create_timeline_component(time=4)
        beat_tl.create_timeline_component(time=5)
        beat_tl.create_timeline_component(time=6)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(1) == [1]
        assert beat_tl.get_time_by_measure(2) == [3]
        assert beat_tl.get_time_by_measure(3) == [5]

    def test_get_times_by_measure_index_bigger_than_measure_count(self, beat_tl):
        beat_tl.create_timeline_component(time=1)
        beat_tl.create_timeline_component(time=2)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(2) == []

        assert beat_tl.get_time_by_measure(999) == []

    def test_get_times_by_measure_negative_index(self, beat_tl):
        beat_tl.create_timeline_component(time=1)

        beat_tl.recalculate_measures()

        assert beat_tl.get_time_by_measure(-1) == []
