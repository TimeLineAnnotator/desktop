from __future__ import annotations

import functools
import itertools
import math
from enum import Enum
from bisect import bisect
from math import isclose
from typing import Optional

import tilia.errors
from tilia.requests import post, Post, get, Get
from tilia.settings import settings
from tilia.timelines.beat.validators import validate_integer_list
from tilia.timelines.base.component.pointlike import scale_pointlike, crop_pointlike
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager, TC
from tilia.timelines.beat.components import Beat


class BeatTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: BeatTimeline):
        super().__init__(timeline, [ComponentKind.BEAT])
        self.scale = functools.partial(scale_pointlike, self)
        self.crop = functools.partial(crop_pointlike, self)
        self.compute_is_first_in_measure = True

    @property
    def beat_times(self):
        return {b.time for b in self._components}

    def update_is_first_in_measure_of_subsequent_beats(self, start_index):
        beats_that_start_measure = set(self.timeline.beats_that_start_measures)
        for i, beat in enumerate(self.timeline[start_index:]):
            is_first_in_measure = start_index + i in beats_that_start_measure
            if is_first_in_measure != beat.is_first_in_measure:
                self.timeline.set_component_data(
                    beat.id,
                    "is_first_in_measure",
                    is_first_in_measure,
                )

    def create_component(
        self, kind: ComponentKind, timeline, id, *args, **kwargs
    ) -> tuple[bool, TC | None, str]:
        success, beat, reason = super().create_component(
            kind, timeline, id, *args, **kwargs
        )

        if success:
            self.timeline.recalculate_measures()
            if self.compute_is_first_in_measure:
                beat.is_first_in_measure = self.timeline.is_first_in_measure(beat)
                beat_index = self.get_components().index(beat) + 1
                self.update_is_first_in_measure_of_subsequent_beats(beat_index)
                measure_index = self.timeline.get_measure_index(beat_index)[0]
                post(
                    Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE,
                    self.timeline.id,
                    measure_index - 1,
                )

        return success, beat, reason

    def _validate_component_creation(
        self,
        _: ComponentKind,
        time: float,
        *args,
        **kwargs,
    ):
        return Beat.validate_creation(time, self.beat_times)

    def delete_component(self, component: TC, update_is_first_in_measure=True) -> None:
        component_idx = self.get_components().index(component)
        super().delete_component(component)
        if update_is_first_in_measure:
            self.update_is_first_in_measure_of_subsequent_beats(component_idx - 1)

    def update_component_order(self, component: TC):
        super().update_component_order(component)
        for component in self:
            self.update_component_is_first_in_measure(component)

    def update_component_is_first_in_measure(self, component):
        component.is_first_in_measure = self.timeline.is_first_in_measure(component)

    def get_beats_in_measure(self, measure_index: int) -> list[Beat] | None:
        if self.timeline is None:
            raise ValueError("self.timeline is None.")

        beats = self.get_components().copy()
        measure_start = self.timeline.beats_that_start_measures[measure_index]
        measure_end = self.timeline.beats_that_start_measures[measure_index + 1]
        return beats[measure_start:measure_end]

    def distribute_beats(self, measure_index: int) -> None:
        if self.timeline is None:
            raise ValueError("self.timeline is None.")

        if measure_index == self.timeline.measure_count - 1:
            tilia.errors.display(tilia.errors.BEAT_DISTRIBUTION_ERROR)
            return

        beats_in_measure = self.get_beats_in_measure(measure_index)

        measure_start_time = beats_in_measure[0].time
        next_measure_start_index = self.timeline.get_beat_index(beats_in_measure[-1])
        measure_end_time = self.get_components()[next_measure_start_index + 1].time
        interval = (measure_end_time - measure_start_time) / len(beats_in_measure)

        for index, beat in enumerate(beats_in_measure):
            self.set_component_data(
                beat.id, "time", measure_start_time + index * interval
            )

    def scale(self, factor: float) -> None:
        for beat in self._components:
            self.timeline.set_component_data(beat.id, "time", beat.time * factor)

    def crop(self, length: float) -> None:
        for beat in self._components.copy():
            if beat.time > length:
                self.delete_component(beat)

    def clear(self):
        for component in self._components.copy():
            self.delete_component(component, update_is_first_in_measure=False)

    def deserialize_components(self, serialized_components: dict[int, dict[str]]):
        # Storing these attributes so we can restore them below.
        beats_in_measure = self.timeline.beats_in_measure.copy()
        measure_numbers = self.timeline.measure_numbers.copy()
        measures_to_force_display = self.timeline.measures_to_force_display.copy()

        # This call will change the attributes above.
        super().deserialize_components(serialized_components)

        # But we restore them here.
        self.timeline.set_data("measure_numbers", measure_numbers)
        self.timeline.set_data("beats_in_measure", beats_in_measure)
        self.timeline.set_data("measures_to_force_display", measures_to_force_display)

        self.timeline.recalculate_measures()
        post(Post.BEAT_TIMELINE_COMPONENTS_DESERIALIZED, self.timeline.id)

    def restore_state(self, prev_state: dict):
        self.compute_is_first_in_measure = False
        super().restore_state(prev_state)
        self.compute_is_first_in_measure = True
        self.update_is_first_in_measure_of_subsequent_beats(0)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.timeline.id, 0)


class BeatTimeline(Timeline):
    SERIALIZABLE_BY_VALUE = [
        "beat_pattern",
        "measure_numbers",  # order matters, m. ns. need to be restored
        "beats_in_measure",  # before beats in measure
        "measures_to_force_display",
        "height",
        "is_visible",
        "name",
        "ordinal",
    ]

    KIND = TimelineKind.BEAT_TIMELINE
    COMPONENT_MANAGER_CLASS = BeatTLComponentManager

    def __init__(
        self,
        beat_pattern: list[int] = None,
        name: str = "",
        height: Optional[int] = None,
        beats_in_measure: Optional[list[int]] = None,
        measure_numbers: Optional[list[int]] = None,
        measures_to_force_display: Optional[list[int]] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            height=height,
            **kwargs,
        )

        self.validators = self.validators | {
            "beat_pattern": validate_integer_list,
            "beats_in_measure": validate_integer_list,
            "measure_numbers": validate_integer_list,
            "measures_to_force_display": validate_integer_list,
        }

        self.beat_pattern = beat_pattern or [4]
        self._beats_in_measure = beats_in_measure or []
        self.measure_numbers = measure_numbers or []
        self.measures_to_force_display = measures_to_force_display or []

    @property
    def default_height(self):
        return settings.get("beat_timeline", "default_height")

    @property
    def display_measure_number_period(self):
        return settings.get("beat_timeline", "display_measure_periodicity")

    @property
    def beats_in_measure(self):
        return self._beats_in_measure

    @beats_in_measure.setter
    def beats_in_measure(self, value):
        self._beats_in_measure = value
        self.recalculate_measures()
        self.component_manager.update_is_first_in_measure_of_subsequent_beats(0)

    def should_display_measure_number(self, measure_index):
        # this is a cheap workaround to deal with pickup measures
        # we should implement a more robust solution
        display_index = (
            measure_index if 0 not in self.measure_numbers else measure_index - 1
        )
        return (
            measure_index in self.measures_to_force_display
            or display_index % self.display_measure_number_period == 0
        )

    @property
    def measure_count(self):
        return len(self.beats_in_measure)

    def get_time_by_measure(
        self, number: int, fraction: float = 0, is_segment_end: bool = False
    ) -> list[float]:
        """
        Given the measure index, returns the start time of the measure.
        If fraction is supplied, returns interpolated time between measure's beats.

        `is_segment_end` should be set to `True` on the end of any segment-like components.
        Searches for end points from the previous known beat even if the end point already exists in `metric_fraction_to_time`, since the actual end point might have a non-consecutive measure number to the start point.
        """

        if not self.measure_count:
            raise ValueError("No beats in timeline. Can't get time.")

        if not (0 <= fraction <= 1.0):
            raise ValueError("Fraction must be between 0 and 1 inclusive.")

        metric_fraction = round(number + fraction, 3)
        keys = list(self.metric_fraction_to_beat_dict.keys())

        # make sure metric_fraction is within available beats
        if min(keys) > metric_fraction or max(keys) < (
            metric_fraction // 1 if not is_segment_end else metric_fraction - 1
        ):
            return []

        idx = bisect(keys, metric_fraction)
        if idx == 0:
            return []

        times = []
        if beats := self.metric_fraction_to_time.get(metric_fraction):
            # check if the given metric_fraction has already been memoised
            # if found and is segment-like start, or point-like time, return because a second search will produce duplicates that should not be considered.
            # if found and idx == 1, given metric_fraction is equal to min metric_position of beats. return because no other times will be found through iteration.

            # otherwise, if the metric_fraction already exists, push idx back by one to do a second search.
            if idx == 1 or not is_segment_end:
                return beats
            if keys[idx - 1] == metric_fraction:
                idx -= 1

            times.extend(beats)

        starts = self.metric_fraction_to_beat_dict[keys[idx - 1]]
        start_measure = keys[idx - 1] // 1
        start_metric_fraction = keys[idx - 1] % 1
        for start in starts:
            if next_comp := self.get_next_component(start.id):
                end_time = next_comp.time
                end_metric_fraction = (
                    1.0
                    if (mp := next_comp.metric_position).measure < start_measure
                    else (
                        (mp.beat - 1) / mp.measure_beat_count
                        + (mp.measure - start_measure)
                    )
                )
            else:
                continue

            metric_fraction_diff = (end_metric_fraction - start_metric_fraction) % 1

            # interpolate between beats to get new time
            new_time = start.time + (metric_fraction - keys[idx - 1]) / (
                metric_fraction_diff if metric_fraction_diff != 0 else 1
            ) * (end_time - start.time)

            index = bisect(times, new_time)
            # if new_time is close to its neighbours, don't add to list. otherwise, insert in sorted order.
            if not (
                (index != 0 and isclose(new_time, times[index - 1]))
                or (index != len(times) and isclose(new_time, times[index]))
            ):
                times.insert(index, new_time)

        if not is_segment_end:
            # don't memoise if not is_segment_end - interpolated times will contain beat numbers that don't actually exist.
            self.metric_fraction_to_time[metric_fraction] = times
            for o in times:
                self.time_to_metric_fraction[o] = metric_fraction
            self.__sort_metric_to_time()
            self.__sort_time_to_metric()
        return sorted(times)

    def get_metric_fraction_by_time(self, time: float) -> float:
        if mf := self.time_to_metric_fraction.get(time):
            return mf
        times = list(self.time_to_metric_fraction.keys())
        metric_fraction = list(self.time_to_metric_fraction.values())
        idx = bisect(times, time)
        if idx == 0:
            if len(times):
                return metric_fraction[0]
            return 0
        if idx == len(times) or metric_fraction[idx] < metric_fraction[idx - 1]:
            return metric_fraction[idx - 1]
        return (time - times[idx - 1]) / (times[idx] - times[idx - 1]) * (
            metric_fraction[idx] - metric_fraction[idx - 1]
        ) + metric_fraction[idx - 1]

    def is_first_in_measure(self, beat):
        return self.components.index(beat) in self.beats_that_start_measures_set

    def recalculate_measures(self):
        beat_delta = (len(self)) - sum(self.beats_in_measure)
        if beat_delta > 0:
            self.extend_beats_in_measure(beat_delta)
            self.extend_measure_numbers()
        elif beat_delta < 0:
            self.reduce_beats_in_measure(-beat_delta)
            self.reduce_measure_numbers()

        self.update_beats_that_start_measures()

    @staticmethod
    def get_extension_from_beat_pattern(
        beat_pattern: list[int],
        amount: int,
        start_index: int = 0,
        beats_on_starting_measure: int = 0,
    ) -> list[int]:
        if amount == 0:
            return []

        if start_index < 0:
            raise ValueError(f"Start index must be a positive value. Got {start_index}")

        beat_pattern_cycle = itertools.cycle(beat_pattern)

        # iterate up to start index
        for _ in range(start_index):
            next(beat_pattern_cycle)

        if beats_on_starting_measure:
            beats = next(beat_pattern_cycle)
            if beats_on_starting_measure < beats:
                diff = beats - beats_on_starting_measure
                extension = [min(diff, amount)]
                remaining_beats = amount - diff
            elif beats_on_starting_measure == beats:
                extension = []
                remaining_beats = amount
            else:
                raise ValueError(
                    "More beats on starting measure than found in the iterator"
                )
        else:
            extension = []
            remaining_beats = amount

        if remaining_beats > 0:
            for beats in beat_pattern_cycle:
                if remaining_beats > beats:
                    remaining_beats -= beats
                    extension.append(beats)
                else:
                    extension.append(remaining_beats)
                    break

        return extension

    def _get_beats_in_measure_extension(self, amount: int):
        if not self.beat_pattern:
            raise ValueError("Beat pattern is empty, can't get measure extension.")

        if self.beats_in_measure:
            beats_on_starting_measure = self.beats_in_measure[-1]
            start_index = (
                self.measure_count % len(self.beat_pattern) - 1
            ) % self.measure_count

            if start_index == -1 and beats_on_starting_measure == self.beat_pattern[-1]:
                beats_on_starting_measure = 0
                start_index = 0
        else:
            beats_on_starting_measure = 0
            start_index = 0

        return self.get_extension_from_beat_pattern(
            self.beat_pattern,
            amount,
            start_index=start_index,
            beats_on_starting_measure=beats_on_starting_measure,
        )

    def extend_beats_in_measure(self, amount: int) -> None:
        extension = self._get_beats_in_measure_extension(amount)

        if not self._beats_in_measure:
            self._beats_in_measure += extension
            return

        bp_index = (self.measure_count % len(self.beat_pattern)) - 1
        is_last_measure_complete = (
            self._beats_in_measure[-1] == self.beat_pattern[bp_index]
        )

        if is_last_measure_complete:
            self._beats_in_measure += extension
        else:
            self._beats_in_measure[-1] += extension[0]
            self._beats_in_measure += extension[1:]

    def reduce_beats_in_measure(self, amount: int) -> None:
        remaining_beats = amount
        for beats_in_measure in reversed(self._beats_in_measure):
            if beats_in_measure < remaining_beats:
                self._beats_in_measure.pop(-1)
                remaining_beats -= beats_in_measure
            elif beats_in_measure > remaining_beats:
                self._beats_in_measure[-1] -= remaining_beats
                break
            else:
                self._beats_in_measure.pop(-1)
                break

    def extend_measure_numbers(self):
        extra_measure_count = len(self.beats_in_measure) - len(self.measure_numbers)

        for _ in range(extra_measure_count):
            if not self.measure_numbers:
                self.measure_numbers.append(1)
            else:
                self.measure_numbers.append(self.measure_numbers[-1] + 1)

    def reduce_measure_numbers(self):
        extra_measure_count = len(self.measure_numbers) - len(self.beats_in_measure)
        if not extra_measure_count:
            return
        self.measure_numbers = self.measure_numbers[:-extra_measure_count]
        if self.measures_to_force_display:
            while (
                self.measures_to_force_display
                and self.measures_to_force_display[-1] >= self.measure_count
            ):
                self.measures_to_force_display.pop(-1)

    def update_beats_that_start_measures(self):
        # noinspection PyAttributeOutsideInit
        self.beats_that_start_measures = [0] + list(
            itertools.accumulate(self.beats_in_measure[:-1])
        )
        self.beats_that_start_measures_set = set(self.beats_that_start_measures)
        self.update_metric_fraction_dicts()

    def update_metric_fraction_dicts(self):
        self.metric_fraction_to_beat_dict = {}
        self.metric_fraction_to_time = {}
        self.time_to_metric_fraction = {}
        for beat in self.components:
            metric_fraction = round(
                (mp := beat.metric_position).measure
                + (mp.beat - 1) / mp.measure_beat_count,
                3,
            )
            if mp := self.metric_fraction_to_beat_dict.get(metric_fraction):
                mp.append(beat)
                self.metric_fraction_to_time[metric_fraction].append(beat.time)
                self.time_to_metric_fraction[beat.time] = metric_fraction
            else:
                self.metric_fraction_to_beat_dict[metric_fraction] = [beat]
                self.metric_fraction_to_time[metric_fraction] = [beat.time]
                self.time_to_metric_fraction[beat.time] = metric_fraction
        self.__sort_metric_to_beat()
        self.__sort_metric_to_time()
        self.__sort_time_to_metric()

    def __sort_metric_to_beat(self) -> None:
        self.metric_fraction_to_beat_dict = {
            k: self.metric_fraction_to_beat_dict[k]
            for k in sorted(self.metric_fraction_to_beat_dict.keys())
        }

    def __sort_metric_to_time(self) -> None:
        self.metric_fraction_to_time = {
            k: self.metric_fraction_to_time[k]
            for k in sorted(self.metric_fraction_to_time.keys())
        }

    def __sort_time_to_metric(self) -> None:
        self.time_to_metric_fraction = {
            k: self.time_to_metric_fraction[k]
            for k in sorted(self.time_to_metric_fraction.keys())
        }

    def get_measure_index(self, beat_index: int) -> tuple[int, int]:
        prev_n = 0
        for measure_index, n in enumerate(self.beats_that_start_measures):
            if beat_index < n:
                return measure_index - 1, beat_index - prev_n
            elif beat_index == n:
                return measure_index, 0
            prev_n = n

        if beat_index > n:
            return measure_index, 1
        else:
            raise ValueError(f'No beat with index "{beat_index}" at {self}.')

    def get_beat_index(self, beat: Beat) -> int:
        return self.components.index(beat)

    def propagate_measure_number_change(self, start_index: int):
        for j, measure in enumerate(self.measure_numbers[start_index + 1 :]):
            propagate_index = j + start_index + 1
            if propagate_index in self.measures_to_force_display:
                break
            else:
                self.measure_numbers[propagate_index] = (
                    self.measure_numbers[propagate_index - 1] + 1
                )

    def set_measure_number(self, measure_index: int, number: int) -> None:
        self.measure_numbers[measure_index] = number
        self.propagate_measure_number_change(measure_index)
        if not number == 0:
            self.force_display_measure_number(measure_index)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, measure_index)
        self.update_metric_fraction_dicts()

    def reset_measure_number(self, measure_index: int) -> None:
        if measure_index == 0:
            self.measure_numbers[0] = 1
        else:
            self.measure_numbers[measure_index] = (
                self.measure_numbers[measure_index - 1] + 1
            )
        self.propagate_measure_number_change(measure_index)
        self.update_metric_fraction_dicts()

        try:
            self.unforce_display_measure_number(measure_index)
        except ValueError:
            pass

    def force_display_measure_number(self, measure_index: int) -> None:
        self.measures_to_force_display.append(measure_index)

    def unforce_display_measure_number(self, measure_index: int) -> None:
        self.measures_to_force_display.remove(measure_index)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, measure_index)

    def set_beat_amount_in_measure(self, measure_index: int, beat_amount: int) -> None:
        new_beats_in_measure = self.beats_in_measure.copy()
        new_beats_in_measure[measure_index] = beat_amount
        self.set_data("beats_in_measure", new_beats_in_measure)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, measure_index)

    def distribute_beats(self, measure_index: int) -> None:
        self.component_manager.distribute_beats(measure_index)

    def delete_components(self, components: list[TC]) -> None:
        self._validate_delete_components(components)

        for component in list(reversed(components)):
            self.component_manager.delete_component(
                component, update_is_first_in_measure=False
            )

        if not self.is_empty:
            self.component_manager.update_is_first_in_measure_of_subsequent_beats(0)
            post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, 0)

            # Higher index is possible.

    class FillMethod(Enum):
        BY_AMOUNT = 0
        BY_INTERVAL = 1

    def fill_with_beats(self, method: BeatTimeline.FillMethod, value: int | float):
        duration = get(Get.MEDIA_DURATION)
        self.component_manager.compute_is_first_in_measure = False
        # only compute at end

        if method == BeatTimeline.FillMethod.BY_AMOUNT:
            for i in range(value):
                self.create_component(ComponentKind.BEAT, i * duration / value)
        elif method == BeatTimeline.FillMethod.BY_INTERVAL:
            for i in range(math.floor(duration / value)):
                self.create_component(ComponentKind.BEAT, i * value)

        self.component_manager.compute_is_first_in_measure = True
        self.component_manager.update_is_first_in_measure_of_subsequent_beats(0)

    def add_measure_zero(self, fraction_of_measure_one: float) -> tuple[bool, str]:
        if self.measure_count < 2:
            return (
                False,
                "Timeline has less than two measures. Cannot estimate measure zero duration.",
            )

        measure_one_start = self.get_time_by_measure(1)[0]
        measure_two_start = self.get_time_by_measure(2)[0]

        measure_zero_duration = (
            measure_two_start - measure_one_start
        ) * fraction_of_measure_one
        measure_zero_start = measure_one_start - measure_zero_duration
        if measure_zero_start < 0:
            return (
                False,
                "There is not enough available space before the first measure.",
            )

        self.create_component(ComponentKind.BEAT, measure_zero_start)

        self.set_measure_number(0, 0)
        self.set_beat_amount_in_measure(0, 1)

        return True, ""
