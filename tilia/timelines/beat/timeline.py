from __future__ import annotations

import itertools
import math
from bisect import bisect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from math import isclose
from typing import Any, cast

import tilia.errors
from tilia.log import logger
from tilia.requests import Get, LongOperation, Post, get, long_operation, post
from tilia.settings import settings
from tilia.timelines import serialize
from tilia.timelines.base.component.pointlike import crop_pointlike
from tilia.timelines.base.timeline import (
    TC,
    Timeline,
    TimelineComponentManager,
    TimelineFlag,
)
from tilia.timelines.base.validators import validate_bool
from tilia.timelines.beat.components import Beat, BeatUnit
from tilia.timelines.beat.pattern import parse
from tilia.timelines.beat.units import (
    DEFAULT_DENOMINATOR,
    DEFAULT_UNITS,
    MeasureMeter,
    fit_units,
    format_units,
    is_fit_ambiguous,
    parse_units,
    validate_denominator,
)
from tilia.timelines.beat.validators import (
    validate_beat_pattern,
    validate_integer_list,
)
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hash_timelines import hash_function

DEFAULT_BEAT_PATTERN = "4"


@dataclass(frozen=True)
class TimeStampTable:
    """
    Per beat: its time, its quarter stamp and how many seconds a quarter note
    lasts from it to the next beat, for converting between the two.
    """

    times: list[float]
    stamps: list[float]
    seconds_per_quarter: list[float]


class BeatTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: BeatTimeline):
        super().__init__(timeline, [ComponentKind.BEAT, ComponentKind.BEAT_UNIT])
        self.timeline = cast(BeatTimeline, self.timeline)
        self.compute_is_first_in_measure = True
        self.compute_metric_fraction_dict = True
        # Beat units are kept apart from beats, so everything that treats the
        # timeline's components as its beats (len, indexing, iteration) keeps
        # doing so.
        self._beat_units: list[BeatUnit] = []
        # Set while undo/redo rebuilds components, when beat units are
        # restored from the snapshot rather than moved off deleted beats.
        self.is_restoring = False
        # Bumped on every change to beats or beat units. Caches built from
        # them (quarter stamps, the time/stamp table) rebuild when it moves,
        # so a change can't leave them stale by missing an invalidation.
        self.version = 0

    def bump_version(self) -> None:
        self.version += 1

    @contextmanager
    def suppressing_is_first_in_measure(self) -> Iterator[bool]:
        """
        Suppress per-beat measure recomputation for the duration of the block.

        Yields the value the flag had on entry, so a caller can tell whether it
        owns the recomputation or an outer block will do it once at the end.
        Restoring that value rather than a literal True is what keeps nested
        blocks correct; the try/finally keeps a raising body from leaving the
        flag off for the rest of the timeline's life, which would silently stop
        every beat created afterwards from getting any measure data.
        """
        was_computing = self.compute_is_first_in_measure
        self.compute_is_first_in_measure = False
        try:
            yield was_computing
        finally:
            self.compute_is_first_in_measure = was_computing

    @contextmanager
    def suppressing_metric_fraction_dict(self) -> Iterator[bool]:
        """
        Suppress per-beat rebuilds of the metric-fraction dicts for the block.

        Same contract as suppressing_is_first_in_measure: restore what was
        found, and restore it even when the body raises. Leaving this flag off
        would stop set_component_data from ever rebuilding the dicts again, so
        every later get_time_by_measure and by-measure import would silently
        read stale time-to-measure data.
        """
        was_computing = self.compute_metric_fraction_dict
        self.compute_metric_fraction_dict = False
        try:
            yield was_computing
        finally:
            self.compute_metric_fraction_dict = was_computing

    @property
    def beat_times(self):
        return {b.time for b in self._components}

    @property
    def beat_units(self) -> list[BeatUnit]:
        return list(self._beat_units)

    def get_beat_unit_on_beat(self, beat_id: int) -> BeatUnit | None:
        return next((u for u in self._beat_units if u.beat_id == beat_id), None)

    def _add_to_components(self, component: TC) -> None:
        if component.KIND == ComponentKind.BEAT_UNIT:
            self._beat_units.append(component)
            self.id_to_component[component.id] = component
        else:
            super()._add_to_components(component)

    def _remove_from_components_set(self, component: TC) -> None:
        if component.KIND == ComponentKind.BEAT_UNIT:
            self._beat_units.remove(component)
            self.id_to_component.pop(component.id)
        else:
            super()._remove_from_components_set(component)

    def update_is_first_in_measure_of_subsequent_beats(self, start_index):
        with self.suppressing_metric_fraction_dict():
            beats_that_start_measure = set(self.timeline.beats_that_start_measures)
            for i, beat in enumerate(self.timeline[start_index:]):
                is_first_in_measure = start_index + i in beats_that_start_measure
                if is_first_in_measure != beat.is_first_in_measure:
                    self.timeline.set_component_data(
                        beat.id,
                        "is_first_in_measure",
                        is_first_in_measure,
                    )

        self.timeline.update_metric_fraction_dicts()

    def create_component(
        self, kind: ComponentKind, timeline, id, *args, **kwargs
    ) -> tuple[bool, TC | None, str]:
        success, beat, reason = super().create_component(
            kind, timeline, id, *args, **kwargs
        )
        if success:
            self.bump_version()

        if success and kind == ComponentKind.BEAT_UNIT:
            self.timeline.on_beat_units_changed()
        elif success:
            if self.compute_is_first_in_measure:
                self.timeline.recalculate_measures()
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
        kind: ComponentKind,
        *args,
        **kwargs,
    ):
        if kind == ComponentKind.BEAT_UNIT:
            return BeatUnit.validate_creation(
                *args,
                beat_ids={b.id for b in self._components},
                taken_beat_ids={u.beat_id for u in self._beat_units},
                **kwargs,
            )
        time = args[0] if args else kwargs["time"]
        return Beat.validate_creation(time, self.beat_times)

    def _get_beat_unit_destination(self, beat: Beat) -> Beat | None:
        """
        Where a beat unit goes when the beat it is on is deleted: the first
        other beat of the same measure, or, if that was the measure's only
        beat, the first beat of the next measure, so the measures it governed
        keep it. None if there is no such beat.
        """
        beats = self.get_components()
        beat_index = beats.index(beat)
        measure_index, _ = self.timeline.get_measure_index(beat_index)
        measure_start = self.timeline.beats_that_start_measures[measure_index]
        measure_end = measure_start + self.timeline.beats_in_measure[measure_index]
        for index in range(measure_start, min(measure_end, len(beats))):
            if index != beat_index:
                return beats[index]
        if measure_end < len(beats):
            return beats[measure_end]
        return None

    def delete_component(self, component: TC) -> None:
        if component.KIND == ComponentKind.BEAT_UNIT:
            super().delete_component(component)
            self.bump_version()
            self.timeline.on_beat_units_changed()
            return

        beat_unit = (
            None if self.is_restoring else self.get_beat_unit_on_beat(component.id)
        )
        destination = self._get_beat_unit_destination(component) if beat_unit else None

        component_idx = self.get_components().index(component)
        super().delete_component(component)
        self.bump_version()
        if self.compute_is_first_in_measure:
            self.update_is_first_in_measure_of_subsequent_beats(component_idx - 1)

        if beat_unit:
            if destination is None or self.get_beat_unit_on_beat(destination.id):
                self.delete_component(beat_unit)
            else:
                self.set_component_data(beat_unit.id, "beat_id", destination.id)

    def set_component_data(self, id: int, attr: str, value: Any):
        value, success = super().set_component_data(id, attr, value)
        if success:
            self.bump_version()
        if success and self.get_component(id).KIND == ComponentKind.BEAT_UNIT:
            self.timeline.on_beat_units_changed()
        elif success and self.compute_metric_fraction_dict:
            self.timeline.update_metric_fraction_dicts()
        return value, success

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
        # Order, indices, and metric positions are unaffected by uniform
        # positive scaling, so the only stale state is the time-keyed
        # metric_fraction dicts. Skip per-beat side-effects of calling
        # set_component_data and rebuild once.
        for beat in self._components:
            beat.time *= factor
            beat.update_hash()
        # Times were written directly, so nothing else bumps the version.
        self.bump_version()
        self.timeline.update_metric_fraction_dicts()

    def crop(self, length: float) -> None:
        with self.suppressing_is_first_in_measure() as was_computing:
            crop_pointlike(self, length)

        if was_computing:
            self.timeline.refresh_measures()

    def clear(self):
        with self.suppressing_is_first_in_measure() as was_computing:
            for beat_unit in self._beat_units.copy():
                self.delete_component(beat_unit)
            for component in self._components.copy():
                self.delete_component(component)

        if was_computing:
            self.timeline.refresh_measures()

    def _get_beats_and_beat_units(self) -> list[TC]:
        # Beat units in the order of their beats, not of creation, so equal
        # states hash and serialize alike however they were reached.
        return self._components + self.timeline.beat_units

    def hash_components(self) -> str:
        str_to_hash = ""
        for component in self._get_beats_and_beat_units():
            str_to_hash += component.hash + "|"

        return hash_function(str_to_hash)

    def serialize_components(self) -> dict[int | str, dict[str, Any]]:
        return serialize.serialize_components(self._get_beats_and_beat_units())

    @staticmethod
    def _split_beat_units(
        serialized_components: dict[int | str, dict[str, Any]],
    ) -> tuple[dict, dict]:
        beats, beat_units = {}, {}
        for id, data in serialized_components.items():
            if data["kind"] == ComponentKind.BEAT_UNIT.name:
                beat_units[id] = data
            else:
                beats[id] = data
        return beats, beat_units

    def deserialize_components(self, serialized_components: dict[int, dict[str]]):
        # Storing these attributes so we can restore them below.
        beats_in_measure = self.timeline.beats_in_measure.copy()
        measure_numbers = self.timeline.measure_numbers.copy()
        measures_to_force_display = self.timeline.measures_to_force_display.copy()

        with self.suppressing_is_first_in_measure():
            # Beat units refer to beats, so they are created once all beats are.
            beats, beat_units = self._split_beat_units(serialized_components)
            # This call will change the attributes above.
            super().deserialize_components(beats)
            super().deserialize_components(beat_units)

            # But we restore them here.
            self.timeline.set_data("measure_numbers", measure_numbers)
            self.timeline.set_data("beats_in_measure", beats_in_measure)
            self.timeline.set_data(
                "measures_to_force_display", measures_to_force_display
            )

        self.timeline.recalculate_measures()
        # Files saved by earlier versions can hold duplicate or out-of-range
        # indices.
        self.timeline.measures_to_force_display = [
            i
            for i in dict.fromkeys(self.timeline.measures_to_force_display)
            if 0 <= i < self.timeline.measure_count
        ]
        post(Post.BEAT_TIMELINE_COMPONENTS_DESERIALIZED, self.timeline.id)

    def restore_state(self, prev_state: dict):
        self.timeline.clear_cached_metric_positions()
        beats, beat_units = self._split_beat_units(prev_state)
        with self.suppressing_is_first_in_measure():
            # Beat units are few, so they are rebuilt from the snapshot rather
            # than diffed. Removing them first also keeps beat deletions below
            # from moving them.
            self.is_restoring = True
            try:
                for beat_unit in self._beat_units.copy():
                    self.delete_component(beat_unit)
                super().restore_state(beats)
                for id, data in beat_units.items():
                    data = data.copy()
                    data.pop("kind")
                    data.pop("hash", None)
                    self.timeline.create_component(
                        ComponentKind.BEAT_UNIT, id=id, **data
                    )
            finally:
                self.is_restoring = False
        self.bump_version()
        self.timeline.refresh_measures()


class BeatTimeline(Timeline):
    SERIALIZABLE = [
        "beat_pattern",
        "measure_numbers",  # order matters, m. ns. need to be restored
        "beats_in_measure",  # before beats in measure
        "measures_to_force_display",
        "show_time_signatures",
        "height",
        "is_visible",
        "name",
        "ordinal",
    ]

    COMPONENT_MANAGER_CLASS = BeatTLComponentManager
    FLAGS = [TimelineFlag.COMPONENTS_COPYABLE, TimelineFlag.COMPONENTS_IMPORTABLE]

    @staticmethod
    def update_component_references(
        components: dict[int | str, dict[str, Any]],
        new_ids: dict[int | str, int | str],
    ) -> None:
        # A beat unit names the beat it is on by its id.
        for data in components.values():
            if data["kind"] == ComponentKind.BEAT_UNIT.name:
                data["beat_id"] = new_ids.get(data["beat_id"], data["beat_id"])

    def __init__(
        self,
        beat_pattern: str | list[int] | None = None,
        name: str = "",
        height: int | None = None,
        beats_in_measure: list[int] | None = None,
        measure_numbers: list[int] | None = None,
        measures_to_force_display: list[int] | None = None,
        show_time_signatures: bool = False,
        **kwargs,
    ):
        # Caches keyed by the component manager's version; see _cached.
        self._caches: dict[str, tuple[int, Any]] = {}
        super().__init__(
            name=name,
            height=height,
            **kwargs,
        )

        self.validators = self.validators | {
            "beat_pattern": validate_beat_pattern,
            "beats_in_measure": validate_integer_list,
            "measure_numbers": validate_integer_list,
            "measures_to_force_display": validate_integer_list,
            "show_time_signatures": validate_bool,
        }

        self.beat_pattern = beat_pattern or DEFAULT_BEAT_PATTERN
        self._beats_in_measure = beats_in_measure or []
        self.measure_numbers = measure_numbers or []
        self.measures_to_force_display = measures_to_force_display or []
        # False for files saved before time signatures existed, so their
        # layout doesn't change; new timelines are created with it on.
        self.show_time_signatures = show_time_signatures

    @property
    def beat_pattern(self) -> str:
        """The pattern as the user wrote it, e.g. "10[4] 3"."""
        return self._beat_pattern

    @beat_pattern.setter
    def beat_pattern(self, value: str | list[int]) -> None:
        # Files and callers from before patterns were text pass a list of bar
        # lengths, which is always valid pattern text once joined.
        text = " ".join(map(str, value)) if isinstance(value, list) else value
        result = parse(text)
        if not result.is_complete:
            logger.error(
                f"Invalid beat pattern {text!r} on {self}: {result.error} "
                f"Using {DEFAULT_BEAT_PATTERN!r} instead."
            )
            text = DEFAULT_BEAT_PATTERN
            result = parse(text)
        self._beat_pattern = text
        self._beat_pattern_bars = result.bars

    @property
    def beat_pattern_bars(self) -> list[int]:
        """The bar lengths the pattern expands to."""
        return self._beat_pattern_bars

    @property
    def default_height(self):
        return settings.get("beat_timeline", "default_height")

    @property
    def display_measure_number_period(self):
        return settings.get("beat_timeline", "display_measure_periodicity")

    @property
    def beats_in_measure(self) -> list[int]:
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

    @property
    def numbers_of_measures(self) -> list[int]:
        # A hand-edited or buggy file can have more numbers than measures.
        return self.measure_numbers[: self.measure_count]

    def get_time_by_measure(
        self, number: int, fraction: float = 0, is_segment_end: bool = False
    ) -> list[float]:
        """
        Returns the times at `fraction` (0 to 1, counted in beats) of each
        measure numbered `number`: one time per pass through it, in time order.
        Between two beats, the time is interpolated. A fraction that, rounded to
        3 decimals, is a beat's (0.333 of three beats) gives that beat's time.

        Fraction 1 gives the next measure's start if that measure is numbered
        `number + 1`, and no time otherwise. The last beat lasts as long as the
        gap before it, up to the media's end, and the last measure never ends
        before that beat.

        `is_segment_end` should be set to `True` on the end of any segment-like
        components. Fraction 1 then gives where the measure ends, whatever
        follows it, and fraction 0 also gives where each pass of the measure
        numbered just below `number` ends.
        """

        if not self.measure_count:
            raise ValueError("No beats in timeline. Can't get time.")

        if not (0 <= fraction <= 1.0):
            tilia.errors.display(tilia.errors.INVALID_MEASURE_FRACTION, fraction)
            return []

        beats = self.components
        measure_indices = [
            i for i, n in enumerate(self.numbers_of_measures) if n == number
        ]
        times = [
            time
            for i in measure_indices
            if (time := self._get_time_in_measure(beats, i, fraction, is_segment_end))
            is not None
        ]
        if (
            is_segment_end
            and measure_indices
            and round(number + fraction, 3) == round(number, 3)
        ):
            times += self._get_ends_of_measures_before(beats, number)

        times = sorted(times)
        times = [
            time
            for i, time in enumerate(times)
            if i == 0 or not isclose(time, times[i - 1])
        ]

        if not is_segment_end:
            # get_metric_fraction_by_time interpolates between these times.
            # Interpolated end times aren't stored: an end point on a downbeat
            # belongs to the measure before it.
            metric_fraction = round(number + fraction, 3)
            for time in times:
                self.time_to_metric_fraction[time] = metric_fraction
            self.__sort_time_to_metric()
        return times

    def _get_time_in_measure(
        self,
        beats: list[Beat],
        measure_index: int,
        fraction: float,
        is_segment_end: bool,
    ) -> float | None:
        number = self.measure_numbers[measure_index]
        beat_count = self.beats_in_measure[measure_index]
        first = self.beats_that_start_measures[measure_index]

        beat = self._get_beat_at_fraction(number, fraction, beat_count)
        if beat == beat_count:
            if is_segment_end:
                return self._get_measure_end(beats, measure_index)
            next_index = measure_index + 1
            if (
                next_index < self.measure_count
                and self.measure_numbers[next_index] == number + 1
            ):
                return beats[first + beat_count].time
            return None
        if beat is not None:
            return beats[first + beat].time

        position = fraction * beat_count
        k = int(position)  # below beat_count: a fraction this close to 1 is at 1
        start = beats[first + k].time
        if k + 1 < beat_count:
            end = beats[first + k + 1].time
        else:
            end = self._get_measure_end(beats, measure_index)
            if end is None:
                return None
        return start + (position - k) * (end - start)

    @staticmethod
    def _get_beat_at_fraction(
        number: int, fraction: float, beat_count: int
    ) -> int | None:
        """
        The index in its measure of the beat at `fraction`, `beat_count` for
        fraction 1, or None between beats. Compared at 3 decimals, so that 0.333
        is the second of three beats.
        """
        target = round(number + fraction, 3)
        if target == number + 1:
            return beat_count
        for k in range(beat_count):
            if target == round(number + k / beat_count, 3):
                return k
        return None

    def _get_measure_end(self, beats: list[Beat], measure_index: int) -> float | None:
        """
        The next measure's start. The last measure ends where its last beat does:
        that beat lasts as long as the gap before it, and stops at the media's
        end if that comes sooner, but never before the beat itself, so that times
        never run backwards. A timeline with one beat has no gap to measure it by.
        """
        if measure_index + 1 < self.measure_count:
            return beats[self.beats_that_start_measures[measure_index + 1]].time
        if len(beats) < 2:
            return None
        last_beat = beats[-1].time
        end = last_beat + (last_beat - beats[-2].time)
        return max(last_beat, min(end, get(Get.MEDIA_DURATION)))

    def _get_ends_of_measures_before(
        self, beats: list[Beat], number: int
    ) -> list[float]:
        """Where each pass of the measure numbered just below `number` ends."""
        numbers_below = [n for n in self.numbers_of_measures if n < number]
        if not numbers_below:
            return []
        number_before = max(numbers_below)
        return [
            end
            for i, n in enumerate(self.numbers_of_measures)
            if n == number_before
            and (end := self._get_measure_end(beats, i)) is not None
        ]

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

    def clear_cached_metric_positions(self):
        for beat in self:
            beat.clear_cached_metric_position()
        self._invalidate_meters()

    @property
    def beat_units(self) -> list[BeatUnit]:
        """Beat units in the order of the beats they are on."""
        beat_index = {beat.id: i for i, beat in enumerate(self)}
        return sorted(
            self.component_manager.beat_units,
            key=lambda u: beat_index.get(u.beat_id, len(beat_index)),
        )

    def get_beat_unit_on_beat(self, beat_id: int) -> BeatUnit | None:
        return self.component_manager.get_beat_unit_on_beat(beat_id)

    def _invalidate_meters(self) -> None:
        self._measure_meters = None
        # Bar lengths or beat units changed: caches built from beats are stale.
        self.component_manager.bump_version()

    def on_beat_units_changed(self) -> None:
        self._invalidate_meters()

    @property
    def measure_meters(self) -> list[MeasureMeter]:
        """The meter of every measure, from the beat units in effect."""
        if getattr(self, "_measure_meters", None) is None:
            self._measure_meters = self._compute_measure_meters()
        return self._measure_meters

    def get_measure_meter(self, measure_index: int) -> MeasureMeter:
        return self.measure_meters[measure_index]

    def get_beat_units_in_measure(self, measure_index: int) -> list[BeatUnit]:
        """Beat units on the beats of a measure, in beat order."""
        start = self.beats_that_start_measures[measure_index]
        beats = self.components[start : start + self.beats_in_measure[measure_index]]
        return [
            beat_unit
            for beat in beats
            if (beat_unit := self.get_beat_unit_on_beat(beat.id)) is not None
        ]

    @property
    def beat_quarter_lengths(self) -> list[Fraction]:
        """How long each beat is, in quarter notes."""
        return [
            meter.quarter_length(value)
            for meter in self.measure_meters
            for value in meter.beat_values
        ][: len(self)]

    def _cached(self, name: str, build: Callable[[], Any]) -> Any:
        """
        The value of `build()`, rebuilt only when the component manager's
        version has changed since it was last built.
        """
        version = self.component_manager.version
        cached = self._caches.get(name)
        if cached is None or cached[0] != version:
            cached = (version, build())
            self._caches[name] = cached
        return cached[1]

    @property
    def quarter_stamps(self) -> list[Fraction]:
        """
        Each beat's position in quarter notes, counted in playback order from
        the first beat (pickup included), as Verovio's and the Measure Map's
        "qstamp".
        """
        return self._cached("quarter_stamps", self._build_quarter_stamps)

    def _build_quarter_stamps(self) -> list[Fraction]:
        stamps = [Fraction(0)] + list(
            itertools.accumulate(self.beat_quarter_lengths[:-1])
        )
        return stamps[: len(self)]

    def get_quarter_stamp_of_beat(self, beat: Beat) -> Fraction:
        return self.quarter_stamps[self.get_beat_index(beat)]

    def _build_time_stamp_table(self) -> TimeStampTable:
        times = [beat.time for beat in self.components]
        lengths = self.beat_quarter_lengths
        seconds_per_quarter = [
            (times[index + 1] - times[index]) / float(lengths[index])
            for index in range(len(times) - 1)
        ]
        # The last beat has no next beat to measure against, so the tempo of
        # the gap before it carries on past it. Its own length doesn't enter:
        # that gap lasted the previous beat's length, not the last one's.
        seconds_per_quarter.append(seconds_per_quarter[-1])
        return TimeStampTable(
            times=times,
            stamps=[float(stamp) for stamp in self.quarter_stamps],
            seconds_per_quarter=seconds_per_quarter,
        )

    def _get_time_stamp_table(self) -> TimeStampTable:
        return self._cached("time_stamp_table", self._build_time_stamp_table)

    def get_quarter_stamp_by_time(self, time: float) -> float | None:
        """
        The quarter stamp at `time`, interpolated between beats and
        extrapolated beyond them. None with fewer than two beats.
        """
        if len(self) < 2:
            return None
        table = self._get_time_stamp_table()
        index = max(0, min(bisect(table.times, time) - 1, len(table.times) - 1))
        return (
            table.stamps[index]
            + (time - table.times[index]) / table.seconds_per_quarter[index]
        )

    def get_time_by_quarter_stamp(self, stamp: float) -> float | None:
        """
        The time of quarter stamp `stamp`, interpolated between beats and
        extrapolated beyond them. None with fewer than two beats.
        """
        if len(self) < 2:
            return None
        table = self._get_time_stamp_table()
        index = max(0, min(bisect(table.stamps, stamp) - 1, len(table.stamps) - 1))
        return (
            table.times[index]
            + (stamp - table.stamps[index]) * table.seconds_per_quarter[index]
        )

    def _compute_measure_meters(self) -> list[MeasureMeter]:
        beats = self.components
        units_by_beat_id = {u.beat_id: u for u in self.component_manager.beat_units}
        starts = getattr(self, "beats_that_start_measures", [])
        default_units = parse_units(DEFAULT_UNITS).units

        meters = []
        governing: BeatUnit | None = None
        for measure_index, beat_count in enumerate(self.beats_in_measure):
            start = starts[measure_index] if measure_index < len(starts) else 0
            in_measure = [
                units_by_beat_id[beat.id]
                for beat in beats[start : start + beat_count]
                if beat.id in units_by_beat_id
            ]
            if in_measure:
                governing = in_measure[0]

            if governing is None:
                denominator, units = DEFAULT_DENOMINATOR, default_units
            else:
                denominator, units = governing.denominator, governing.unit_values

            meters.append(
                MeasureMeter(
                    denominator=denominator,
                    units=tuple(units),
                    beat_values=tuple(fit_units(units, beat_count)),
                    beat_unit_id=governing.beat_id if governing else None,
                    starts_here=bool(in_measure),
                    is_ambiguous=is_fit_ambiguous(units, beat_count),
                    is_conflicting=len(in_measure) > 1,
                    is_assumed=governing is None or governing.assumed,
                )
            )
        return meters

    def get_export_data(self) -> dict[str, Any]:
        # Beat units are kept apart from beats in the component manager, so
        # the base export, which iterates it, only sees beats. They have no
        # time of their own; their beat's time and measure are added so the
        # export reads without looking the beat up.
        result = super().get_export_data()
        for beat_unit in self.beat_units:
            beat = self.get_component(beat_unit.beat_id)
            measure_index, _ = self.get_measure_index(self.get_beat_index(beat))
            data = {
                attr: getattr(beat_unit, attr)
                for attr in beat_unit.get_export_attributes()
            }
            data["time"] = beat.time
            data["measure"] = self.measure_numbers[measure_index]
            data["kind"] = beat_unit.KIND.name
            result["components"].append(data)
        return result

    def set_beat_unit(
        self,
        measure_index: int,
        denominator: int,
        units: str,
        only_this_measure: bool = False,
    ) -> bool:
        """
        Sets the beat unit from `measure_index` until the next change, or for
        that measure only, restoring the previous values from the next one.
        Edits the beat unit starting in that measure if there is one, and
        otherwise creates one on the measure's first beat. The values count
        as set by the user even when unchanged, which confirms assumed ones.
        """
        result = parse_units(units)
        if not result.is_valid or not validate_denominator(denominator):
            return False
        if not 0 <= measure_index < self.measure_count:
            return False

        previous = self.get_measure_meter(measure_index)
        self._put_beat_unit(
            measure_index, denominator, format_units(result.units), assumed=False
        )

        next_index = measure_index + 1
        if (
            only_this_measure
            and next_index < self.measure_count
            and not self.get_measure_meter(next_index).starts_here
        ):
            self._put_beat_unit(
                next_index,
                previous.denominator,
                format_units(previous.units),
                assumed=previous.is_assumed,
            )

        return True

    def _put_beat_unit(
        self, measure_index: int, denominator: int, units: str, assumed: bool
    ) -> None:
        meter = self.get_measure_meter(measure_index)
        if meter.starts_here:
            beat_id = meter.beat_unit_id
        else:
            beat_id = self[self.beats_that_start_measures[measure_index]].id
        self.put_beat_unit_on_beat(beat_id, denominator, units, assumed)

    def recalculate_measures(self):
        beat_delta = (len(self)) - sum(self.beats_in_measure)
        if beat_delta > 0:
            self.extend_beats_in_measure(beat_delta)
            self.extend_measure_numbers()
        elif beat_delta < 0:
            self.reduce_beats_in_measure(-beat_delta)
            self.reduce_measure_numbers()

        self.clear_cached_metric_positions()
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
            else:
                # A measure may hold more beats than the beat pattern
                # prescribes for it, as "Set amount in measure" sets an
                # arbitrary amount. There is nothing left to fill in that
                # case, so the extension starts a new measure.
                extension = []
                remaining_beats = amount
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
        if not self.beat_pattern_bars:
            raise ValueError("Beat pattern is empty, can't get measure extension.")

        if self.beats_in_measure:
            beats_on_starting_measure = self.beats_in_measure[-1]
            start_index = (
                self.measure_count % len(self.beat_pattern_bars) - 1
            ) % self.measure_count

            if (
                start_index == -1
                and beats_on_starting_measure == self.beat_pattern_bars[-1]
            ):
                beats_on_starting_measure = 0
                start_index = 0
        else:
            beats_on_starting_measure = 0
            start_index = 0

        return self.get_extension_from_beat_pattern(
            self.beat_pattern_bars,
            amount,
            start_index=start_index,
            beats_on_starting_measure=beats_on_starting_measure,
        )

    def extend_beats_in_measure(self, amount: int) -> None:
        extension = self._get_beats_in_measure_extension(amount)

        if not self._beats_in_measure:
            self._beats_in_measure += extension
            return

        bp_index = (self.measure_count % len(self.beat_pattern_bars)) - 1
        is_last_measure_complete = (
            self._beats_in_measure[-1] >= self.beat_pattern_bars[bp_index]
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
        # measures_to_force_display is not sorted, so every index has to be
        # checked, not just the ones at the end of the list.
        self.measures_to_force_display = [
            i for i in self.measures_to_force_display if i < self.measure_count
        ]

    def update_beats_that_start_measures(self):
        # noinspection PyAttributeOutsideInit
        self.beats_that_start_measures = [0] + list(
            itertools.accumulate(self.beats_in_measure[:-1])
        )
        self.beats_that_start_measures_set = set(self.beats_that_start_measures)
        self._invalidate_meters()
        self.update_metric_fraction_dicts()
        self._ensure_first_beat_unit()

    def _ensure_first_beat_unit(self, copy_next: bool = True) -> None:
        """
        Keeps a beat unit in the first measure, so every measure is governed
        by one and every time signature label can be selected and edited.

        When one is missing, e.g. because a pickup was added before the old
        first beat, it copies the next beat unit's values (a pickup in a 6/8
        piece starts as 6/8); with no other beat units, or `copy_next` False,
        it gets the default. Either way it is assumed: nobody set a time
        signature on the measures before the next beat unit. Skipped while
        beats are being changed in bulk, which recalculates and calls this
        once at the end.
        """
        manager = self.component_manager
        if (
            manager.is_restoring
            or not manager.compute_is_first_in_measure
            or not len(self)
            or not self.beats_in_measure
        ):
            return

        first_measure = self.components[: self.beats_in_measure[0]]
        if any(self.get_beat_unit_on_beat(beat.id) for beat in first_measure):
            return

        beat_units = self.beat_units
        if copy_next and beat_units:
            denominator, units = beat_units[0].denominator, beat_units[0].units
        else:
            denominator, units = DEFAULT_DENOMINATOR, DEFAULT_UNITS
        self.create_component(
            ComponentKind.BEAT_UNIT,
            beat_id=self[0].id,
            denominator=denominator,
            units=units,
            assumed=True,
        )

    def put_beat_unit_on_beat(
        self,
        beat_id: int | str,
        denominator: int,
        units: str,
        assumed: bool = False,
    ) -> None:
        """Sets the beat unit on a beat, creating it or editing the one there."""
        beat_unit = self.get_beat_unit_on_beat(beat_id)
        if beat_unit is None:
            self.create_component(
                ComponentKind.BEAT_UNIT,
                beat_id=beat_id,
                denominator=denominator,
                units=units,
                assumed=assumed,
            )
        else:
            self.set_component_data(beat_unit.id, "denominator", denominator)
            self.set_component_data(beat_unit.id, "units", units)
            self.set_component_data(beat_unit.id, "assumed", assumed)

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
        for j in range(len(self.measure_numbers[start_index + 1 :])):
            propagate_index = j + start_index + 1
            if propagate_index in self.measures_to_force_display:
                break
            else:
                self.measure_numbers[propagate_index] = (
                    self.measure_numbers[propagate_index - 1] + 1
                )

    def set_measure_number(self, measure_index: int, number: int) -> None:
        self.clear_cached_metric_positions()
        self.measure_numbers[measure_index] = number
        self.propagate_measure_number_change(measure_index)
        if not number == 0:
            self.force_display_measure_number(measure_index)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, measure_index)
        self.update_metric_fraction_dicts()

    def reset_measure_number(self, measure_index: int) -> None:
        self.clear_cached_metric_positions()
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
        self.clear_cached_metric_positions()
        if measure_index not in self.measures_to_force_display:
            self.measures_to_force_display.append(measure_index)

    def unforce_display_measure_number(self, measure_index: int) -> None:
        self.clear_cached_metric_positions()
        self.measures_to_force_display.remove(measure_index)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, measure_index)

    def set_beat_amount_in_measure(self, measure_index: int, beat_amount: int) -> None:
        self.clear_cached_metric_positions()
        new_beats_in_measure = self.beats_in_measure.copy()
        new_beats_in_measure[measure_index] = beat_amount
        self.set_data("beats_in_measure", new_beats_in_measure)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, measure_index)

    def distribute_beats(self, measure_index: int) -> None:
        self.component_manager.distribute_beats(measure_index)

    def refresh_measures(self) -> None:
        """
        Rebuild the measure structure and have the UI relabel every beat.

        Run this after any bulk operation that added or removed beats with
        per-beat recomputation suppressed. It is safe on an emptied timeline,
        and required there: otherwise beats_in_measure and measure_numbers go
        on describing beats that no longer exist, and the labels stay on
        screen.
        """
        self.recalculate_measures()
        self.component_manager.update_is_first_in_measure_of_subsequent_beats(0)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, 0)

    def get_hand_set_bars(self) -> list[int]:
        """
        Indices of bars whose length differs from the pattern, i.e. bars set
        with "Set amount in measure". The last bar is left out: it may simply
        not have all its beats yet.
        """
        bars = self.beat_pattern_bars
        return [
            i
            for i, beats in enumerate(self.beats_in_measure[:-1])
            if beats != bars[i % len(bars)]
        ]

    def get_bars_overwritten_by(self, pattern_bars: list[int]) -> list[int]:
        """Indices of hand-set bars that applying `pattern_bars` would change."""
        return [
            i
            for i in self.get_hand_set_bars()
            if self.beats_in_measure[i] != pattern_bars[i % len(pattern_bars)]
        ]

    def set_beat_pattern(self, pattern: str) -> bool:
        """
        Sets the pattern and recomputes every bar from it, discarding bars set
        by hand. Measure numbers are kept by bar position.
        """
        _, success = self.set_data("beat_pattern", pattern)
        if not success:
            return False

        self._beats_in_measure = self.get_extension_from_beat_pattern(
            self.beat_pattern_bars, len(self)
        )
        # Measure numbers must match the new bar count before measures are
        # recalculated, which reads a number for every bar.
        if len(self.measure_numbers) < self.measure_count:
            self.extend_measure_numbers()
        elif len(self.measure_numbers) > self.measure_count:
            self.reduce_measure_numbers()

        self.clear_cached_metric_positions()
        self.update_beats_that_start_measures()
        self.component_manager.update_is_first_in_measure_of_subsequent_beats(0)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, 0)
        return True

    def delete_components(self, components: list[TC]) -> None:
        self._validate_delete_components(components)

        self.clear_cached_metric_positions()

        component_manager = self.component_manager
        with component_manager.suppressing_is_first_in_measure() as was_computing:
            for component in list(reversed(components)):
                component_manager.delete_component(component)

        if not was_computing:
            # BeatTLComponentManager.restore_state, reached on every undo and
            # redo, suppresses recomputation across a whole delete-then-create
            # pass and recomputes once at the end. Recomputing here would make
            # every beat it re-creates afterwards sweep the whole timeline.
            return

        # Deleting the first measure's beat unit resets it to the default,
        # rather than copying the next one as a structural change would.
        if any(c.KIND == ComponentKind.BEAT_UNIT for c in components):
            self._ensure_first_beat_unit(copy_next=False)

        self.refresh_measures()

    class FillMethod(Enum):
        BY_AMOUNT = 0
        BY_INTERVAL = 1

    @long_operation("Creating beats...")
    def fill_with_beats(self, method: BeatTimeline.FillMethod, value: int | float):
        duration = get(Get.MEDIA_DURATION)
        # only compute at end
        with self.component_manager.suppressing_is_first_in_measure():
            if method == BeatTimeline.FillMethod.BY_AMOUNT:
                total = int(value)
                for i in range(total):
                    self.create_component(ComponentKind.BEAT, i * duration / value)
                    post(Post.LONG_OPERATION, LongOperation.PROGRESS, i + 1, total)
            elif method == BeatTimeline.FillMethod.BY_INTERVAL:
                total = math.floor(duration / value)
                for i in range(total):
                    self.create_component(ComponentKind.BEAT, i * value)
                    post(Post.LONG_OPERATION, LongOperation.PROGRESS, i + 1, total)

        self.recalculate_measures()
        self.component_manager.update_is_first_in_measure_of_subsequent_beats(0)
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, 0)

    def add_measure_zero(self, fraction_of_measure_one: float) -> tuple[bool, str]:
        if self.measure_count < 2:
            return (
                False,
                "Timeline has less than two measures. Cannot estimate measure zero duration.",
            )

        # The first two measures, whatever their numbers: the new measure goes
        # before the first, and is estimated from how long the first lasts.
        first_start, second_start = (
            self[i].time for i in self.beats_that_start_measures[:2]
        )

        measure_zero_duration = (second_start - first_start) * fraction_of_measure_one
        measure_zero_start = first_start - measure_zero_duration
        if measure_zero_start < 0:
            return (
                False,
                "There is not enough available space before the first measure.",
            )

        self.create_component(ComponentKind.BEAT, measure_zero_start)

        self.set_measure_number(0, 0)
        self.set_beat_amount_in_measure(0, 1)

        return True, ""
