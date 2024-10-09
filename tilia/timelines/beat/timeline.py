from __future__ import annotations

import functools
import itertools
from typing import TYPE_CHECKING, Optional

from tilia.requests import get, Get, post, Post
from tilia.settings import settings
from tilia.timelines.base.common import scale_discrete, crop_discrete
from tilia.timelines.beat.validators import validate_integer_list
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager, TC
import tilia.errors

if TYPE_CHECKING:
    from tilia.timelines.beat.components import Beat


class BeatTimeline(Timeline):
    SERIALIZABLE_BY_VALUE = [
        "beat_pattern",
        "beats_in_measure",
        "measure_numbers",
        "measures_to_force_display",
        "height",
        "is_visible",
        "name",
        "ordinal",
    ]

    KIND = TimelineKind.BEAT_TIMELINE
    component_manager: BeatTLComponentManager

    def __init__(
        self,
        component_manager: BeatTLComponentManager,
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
            component_manager=component_manager,
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
        self.update_beats_that_start_measures()
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
        return (
            measure_index in self.measures_to_force_display
            or measure_index % self.display_measure_number_period == 0
        )

    @property
    def measure_count(self):
        return len(self.beats_in_measure)

    def get_time_by_measure(self, number: int, fraction: float = 0) -> list[int]:
        """
        Given the measure index, returns the start time of the measure.
        If fraction is supplied, sums that fraction of the measure's
        length to the result.
        """

        if not self.measure_count:
            raise ValueError("No beats in timeline. Can't get time.")

        measure_indices = [i for i, n in enumerate(self.measure_numbers) if n == number]
        measure_times = []

        for index in measure_indices:
            beat_number = self.beats_that_start_measures[index]
            measure_time = self.components[beat_number].time

            if index == self.measure_count - 1:
                next_measure_time = measure_time
            else:
                beat_number = self.beats_that_start_measures[index + 1]
                next_measure_time = self.components[beat_number].time

            measure_times.append(
                measure_time + (next_measure_time - measure_time) * fraction
            )

        return measure_times

    def is_first_in_measure(self, beat):
        return self.components.index(beat) in self.beats_that_start_measures

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

    def update_beats_that_start_measures(self):
        # noinspection PyAttributeOutsideInit
        self.beats_that_start_measures = [0] + list(
            itertools.accumulate(self.beats_in_measure[:-1])
        )

    def get_measure_index(self, beat_index: int) -> tuple[int, int]:
        prev_n = 0
        for measure_index, n in enumerate(self.beats_that_start_measures):
            if beat_index < n:
                return measure_index - 1, beat_index - prev_n
            elif beat_index == n:
                return measure_index, 0
            prev_n = n
        else:
            # noinspection PyUnboundLocalVariable
            if beat_index > n:
                # noinspection PyUnboundLocalVariable
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
        self.force_display_measure_number(measure_index)

    def reset_measure_number(self, measure_index: int) -> None:
        if measure_index == 0:
            self.measure_numbers[0] = 1
        else:
            self.measure_numbers[measure_index] = (
                self.measure_numbers[measure_index - 1] + 1
            )
        self.propagate_measure_number_change(measure_index)

        try:
            self.unforce_display_measure_number(measure_index)
        except ValueError:
            pass

    def force_display_measure_number(self, measure_index: int) -> None:
        self.measures_to_force_display.append(measure_index)
        self.component_manager.update_beat_uis()

    def unforce_display_measure_number(self, measure_index: int) -> None:
        self.measures_to_force_display.remove(measure_index)
        self.component_manager.update_beat_uis()

    def set_beat_amount_in_measure(self, measure_index: int, beat_amount: int) -> None:
        new_beats_in_measure = self.beats_in_measure.copy()
        new_beats_in_measure[measure_index] = beat_amount
        self.set_data("beats_in_measure", new_beats_in_measure)

    def distribute_beats(self, measure_index: int) -> None:
        self.component_manager.distribute_beats(measure_index)

    def delete_components(self, components: list[TC]) -> None:
        self._validate_delete_components(components)

        for component in list(reversed(components)):
            self.component_manager.delete_component(
                component, update_is_first_in_measure=False
            )

        if not self.is_empty:
            self.component_manager.update_is_first_in_measure_of_subsequent_beats(
                0
            )  # Higher index is possible.


class BeatTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.BEAT]

    timeline: Optional[BeatTimeline]

    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)
        self.scale = functools.partial(scale_discrete, self)
        self.crop = functools.partial(crop_discrete, self)

    @property
    def beat_times(self):
        return {b.time for b in self._components}

    def update_is_first_in_measure_of_subsequent_beats(self, index):
        for beat_ in self.timeline[index + 1 :]:
            self.timeline.set_component_data(
                beat_.id,
                "is_first_in_measure",
                self.timeline.is_first_in_measure(beat_),
            )

    def create_component(
        self, kind: ComponentKind, timeline, id, *args, **kwargs
    ) -> tuple[bool, TC | None, str]:
        success, beat, reason = super().create_component(
            kind, timeline, id, *args, **kwargs
        )

        if success:
            self.timeline.recalculate_measures()
            beat.is_first_in_measure = self.timeline.is_first_in_measure(beat)
            self.update_is_first_in_measure_of_subsequent_beats(
                self.get_components().index(beat)
            )

        return success, beat, reason

    def _validate_component_creation(
        self,
        _: ComponentKind,
        time: float,
        *args,
        **kwargs,
    ):
        playback_time = get(Get.MEDIA_TIMES_PLAYBACK)
        media_duration = get(Get.MEDIA_DURATION)
        if playback_time.end != 0 and time > playback_time.end:
            return (
                False,
                f"Time '{time}' is greater than current media time '{playback_time.end}'",
            )
        elif playback_time.end == 0 and time > media_duration:
            return (
                False,
                f"Time '{time}' is greater than current media time '{media_duration}'",
            )
        elif time < playback_time.start:
            return (
                False,
                f"Time '{time}' is less than current media start time '{playback_time.start}",
            )
        elif time in self.beat_times:
            return (
                False,
                f"Can't create beat.\nThere is already a beat at time='{time}'.",
            )
        else:
            return True, ""

    def delete_component(self, component: TC, update_is_first_in_measure=True) -> None:
        component_idx = self.get_components().index(component)
        super().delete_component(component)
        if update_is_first_in_measure:
            self.update_is_first_in_measure_of_subsequent_beats(component_idx - 1)

    def update_beat_uis(self):
        beats = self.get_components().copy()
        for beat in beats:
            beat_index = beats.index(beat)
            is_first_in_measure = beat_index in self.timeline.beats_that_start_measures

            post(
                Post.TIMELINE_COMPONENT_SET_DATA_DONE,
                self.timeline.id,
                beat.id,
                "is_first_in_measure",
                is_first_in_measure,
            )

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

        self.timeline.recalculate_measures()  # Not sure if this is needed.
