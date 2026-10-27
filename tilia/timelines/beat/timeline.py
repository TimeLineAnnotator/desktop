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
from tilia.timelines.base.metric_position import MetricPosition
from tilia.timelines.base.timeline import (
    TC,
    Timeline,
    TimelineComponentManager,
    TimelineFlag,
)
from tilia.timelines.base.validators import validate_bool
from tilia.timelines.beat.components import Beat, BeatUnit
from tilia.timelines.beat.measures import (
    Measures,
    build_measures,
    fit_legacy_lists,
    get_extension_from_beat_pattern,
)
from tilia.timelines.beat.pattern import PlannedBar, format_planned_bars, parse
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
from tilia.timelines.beat.validators import validate_beat_pattern
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
        # Beat units are kept apart from beats, so everything that treats the
        # timeline's components as its beats (len, indexing, iteration) keeps
        # doing so.
        self._beat_units: list[BeatUnit] = []
        # Set while undo/redo rebuilds components from a snapshot, which
        # already says which beats start measures and where beat units are.
        self.is_restoring = False
        # Set while beats are changed in bulk (loading, filling, cropping).
        # A beat created then is not placed in a measure by the rules for a
        # single beat, and the UI relabels the beats once at the end.
        self.is_bulk = False
        # Bumped on every change to beats or beat units. Caches built from
        # them (the measures, quarter stamps, the time/stamp table) rebuild
        # when it moves, so a change can't leave them stale by missing an
        # invalidation.
        self.version = 0

    def bump_version(self) -> None:
        self.version += 1

    @contextmanager
    def bulk(self) -> Iterator[bool]:
        """
        Marks the block as a bulk change (see `is_bulk`). Yields the value
        the flag had on entry, so a caller can tell whether it owns the final
        refresh or an outer block will do it. The flag is restored even when
        the body raises.
        """
        was_bulk = self.is_bulk
        self.is_bulk = True
        try:
            yield was_bulk
        finally:
            self.is_bulk = was_bulk

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

    def create_component(
        self, kind: ComponentKind, timeline, id, *args, **kwargs
    ) -> tuple[bool, TC | None, str]:
        success, component, reason = super().create_component(
            kind, timeline, id, *args, **kwargs
        )
        if success:
            self.bump_version()
        return success, component, reason

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

    def move_measure_start(self, beat: Beat, destination: Beat) -> None:
        """
        Moves the start of the measure that `beat` starts to `destination`,
        with its number, its display and its beat unit.
        """
        for attr in ("measure_number_override", "measure_number_always_shown"):
            value = getattr(beat, attr)
            if value != getattr(destination, attr):
                self.set_component_data(destination.id, attr, value)
        if not destination.is_first_in_measure:
            self.set_component_data(destination.id, "is_first_in_measure", True)
        if beat.is_first_in_measure:
            self.set_component_data(beat.id, "is_first_in_measure", False)
        if beat.measure_number_override is not None:
            self.set_component_data(beat.id, "measure_number_override", None)
        if beat.measure_number_always_shown:
            self.set_component_data(beat.id, "measure_number_always_shown", False)

        beat_unit = self.get_beat_unit_on_beat(beat.id)
        if beat_unit is None:
            return
        if self.get_beat_unit_on_beat(destination.id):
            self.delete_component(beat_unit)
        else:
            self.set_component_data(beat_unit.id, "beat_id", destination.id)

    def _on_beat_deleted(self, beat: Beat) -> None:
        """
        Keeps the other beats' measures as they are. A deleted beat that
        starts a measure hands the measure to the beat after it; if it was
        the measure's only beat, the measure goes, and its beat unit moves to
        the next measure, so the measures it governed keep it. A beat unit on
        a beat that doesn't start a measure moves to the first beat of the
        measure.
        """
        beats = self._components
        index = beats.index(beat)
        next_beat = beats[index + 1] if index + 1 < len(beats) else None
        starts_measure = index == 0 or beat.is_first_in_measure
        if starts_measure and next_beat and not next_beat.is_first_in_measure:
            self.move_measure_start(beat, next_beat)
            return

        beat_unit = self.get_beat_unit_on_beat(beat.id)
        if beat_unit is None:
            return
        if starts_measure:
            destination = next_beat
        else:
            measures = self.timeline.measures
            destination = beats[measures.starts[measures.measure_of_beat[index]]]
        if destination is None or self.get_beat_unit_on_beat(destination.id):
            self.delete_component(beat_unit)
        else:
            self.set_component_data(beat_unit.id, "beat_id", destination.id)

    def delete_component(self, component: TC) -> None:
        if component.KIND == ComponentKind.BEAT_UNIT:
            super().delete_component(component)
            self.bump_version()
            return

        if not self.is_restoring:
            self._on_beat_deleted(component)

        super().delete_component(component)
        self.bump_version()

    def set_component_data(self, id: int, attr: str, value: Any):
        value, success = super().set_component_data(id, attr, value)
        if success:
            self.bump_version()
        return value, success

    def update_component_order(self, component: TC):
        super().update_component_order(component)
        if not self.is_restoring and not self.is_bulk:
            self.timeline.ensure_first_beat_starts_measure()

    def get_beats_in_measure(self, measure_index: int) -> list[Beat]:
        measures = self.timeline.measures
        start = measures.starts[measure_index]
        return self._components[start : start + measures.counts[measure_index]]

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
        # Order and measures are unaffected by uniform positive scaling, so
        # the per-beat side effects of set_component_data are skipped.
        for beat in self._components:
            beat.time *= factor
            beat.update_hash()
        # Times were written directly, so nothing else bumps the version.
        self.bump_version()

    def crop(self, length: float) -> None:
        # From the last beat back, so a deleted beat that starts a measure
        # never hands it to a beat that is about to go too.
        with self.bulk() as was_bulk:
            for beat in reversed(self._components.copy()):
                if beat.time > length:
                    self.delete_component(beat)

        if not was_bulk:
            self.timeline.refresh_measures()

    def clear(self):
        with self.bulk() as was_bulk:
            for beat_unit in self._beat_units.copy():
                self.delete_component(beat_unit)
            for component in reversed(self._components.copy()):
                self.delete_component(component)

        if not was_bulk:
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
        beats, beat_units = self._split_beat_units(serialized_components)
        # Files from before measures were marked on their beats keep them in
        # lists by measure, which the timeline was given when it was created.
        is_legacy = any("is_first_in_measure" not in data for data in beats.values())
        with self.bulk():
            # Beat units refer to beats, so they are created once all beats are.
            super().deserialize_components(beats)
            if is_legacy:
                self.timeline.mark_measures_from_legacy_lists()
            super().deserialize_components(beat_units)

        self.timeline.refresh_measures()
        post(Post.BEAT_TIMELINE_COMPONENTS_DESERIALIZED, self.timeline.id)

    def restore_state(self, prev_state: dict):
        beats, beat_units = self._split_beat_units(prev_state)
        with self.bulk():
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
        self._metric_fraction_version: int | None = None
        super().__init__(
            name=name,
            height=height,
            **kwargs,
        )

        self.validators = self.validators | {
            "beat_pattern": validate_beat_pattern,
            "show_time_signatures": validate_bool,
        }

        self.beat_pattern = beat_pattern or DEFAULT_BEAT_PATTERN
        # Files from before measures were marked on their beats keep them in
        # these lists by measure. They are read once, when the file's beats
        # are loaded; see mark_measures_from_legacy_lists.
        self._legacy_measure_lists = (
            beats_in_measure or [],
            measure_numbers or [],
            measures_to_force_display or [],
        )
        # False for files saved before time signatures existed, so their
        # layout doesn't change; new timelines are created with it on.
        self.show_time_signatures = show_time_signatures

    @property
    def beat_pattern(self) -> str:
        """The pattern as the user wrote it, e.g. "10[4/4] 3/4"."""
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
        self._planned_bars = result.planned_bars

    @property
    def beat_pattern_bars(self) -> list[int]:
        """The bar lengths the pattern expands to."""
        return [bar.beat_count for bar in self._planned_bars]

    @property
    def planned_bars(self) -> list[PlannedBar]:
        """The bars the pattern expands to."""
        return self._planned_bars

    @property
    def plans_time_signatures(self) -> bool:
        """
        Whether the pattern gives time signatures, rather than only the number
        of beats in each bar, as patterns from before time signatures did.
        """
        return any(not bar.assumed for bar in self._planned_bars)

    def get_planned_bar(self, measure_index: int) -> PlannedBar:
        """The bar the pattern plans for a measure, repeating from its start."""
        return self._planned_bars[measure_index % len(self._planned_bars)]

    def get_measures_as_planned_bars(self) -> list[PlannedBar]:
        """
        Each measure as a bar of a pattern: its beats, with the values its
        beat unit gives them. The last measure, while it has only the first
        of the beats the pattern plans for it, is the planned bar.
        """
        bars = []
        for measure_index, meter in enumerate(self.measure_meters):
            values = list(meter.beat_values)
            bar = PlannedBar.from_values(values, meter.denominator, meter.is_assumed)
            planned = self.get_planned_bar(measure_index)
            if (
                measure_index == self.measure_count - 1
                and len(values) < planned.beat_count
                and planned.denominator == meter.denominator
                and planned.values[: len(values)] == values
            ):
                bar = planned
            bars.append(bar)
        return bars

    def get_bars_to_edit(self) -> tuple[str, list[PlannedBar]]:
        """
        The pattern and the bars to edit it from: the measures as they are,
        then the bars the pattern plans after them, up to its end. The
        pattern is the timeline's when the measures follow it, or else one
        written from the bars.
        """
        measures = self.get_measures_as_planned_bars()
        follow_pattern = all(
            bar == self.get_planned_bar(index) for index, bar in enumerate(measures)
        )
        bars = measures + self._planned_bars[len(measures) :]
        if follow_pattern:
            return self.beat_pattern, bars
        return format_planned_bars(bars), bars

    @property
    def default_height(self):
        return settings.get("beat_timeline", "default_height")

    @property
    def display_measure_number_period(self):
        return settings.get("beat_timeline", "display_measure_periodicity")

    @property
    def measures(self) -> Measures:
        """The measures, read from the beats that start them."""
        return self._cached("measures", lambda: build_measures(self.components))

    @property
    def beats_in_measure(self) -> list[int]:
        return self.measures.counts

    @property
    def measure_numbers(self) -> list[int]:
        return self.measures.numbers

    @property
    def measures_to_force_display(self) -> list[int]:
        return self.measures.always_shown

    @property
    def beats_that_start_measures(self) -> list[int]:
        return self.measures.starts

    @property
    def beats_that_start_measures_set(self) -> set[int]:
        return set(self.measures.starts)

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
        return self.measures.count

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

        self._ensure_metric_fraction_dicts()

        if not (0 <= fraction <= 1.0):
            tilia.errors.display(tilia.errors.INVALID_MEASURE_FRACTION, fraction)
            return []

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
            elif start == self.components[-1]:
                # If getting time for the last component, there is no next component to interpolate with.
                # So, we interpolate with a projected next measure, assuming the same duration as the last.
                prev_measure_number = start.metric_position.measure - 1
                prev_measure_starts = self.get_time_by_measure(prev_measure_number)
                if not prev_measure_starts:
                    continue
                else:
                    prev_measure_start = prev_measure_starts[0]
                cur_measure_start = self.get_time_by_measure(
                    start.metric_position.measure
                )[0]
                prev_measure_duration = cur_measure_start - prev_measure_start
                end_time = cur_measure_start + prev_measure_duration
                end_metric_fraction = 0

            metric_fraction_diff = (end_metric_fraction - start_metric_fraction) % 1

            # interpolate between beats to get new time
            new_time = start.time + (metric_fraction - keys[idx - 1]) / (
                metric_fraction_diff
                if not isclose(metric_fraction_diff, 0, abs_tol=0.001)
                else 1
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
        self._ensure_metric_fraction_dicts()
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
        return self.get_beat_index(beat) in self.beats_that_start_measures_set

    def get_metric_position_of_beat(self, beat: Beat) -> MetricPosition:
        measures = self.measures
        index = self.get_beat_index(beat)
        measure_index = measures.measure_of_beat[index]
        return MetricPosition(
            measures.numbers[measure_index],
            index - measures.starts[measure_index] + 1,
            measures.counts[measure_index],
        )

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

    @property
    def measure_meters(self) -> list[MeasureMeter]:
        """The meter of every measure, from the beat units in effect."""
        return self._cached("measure_meters", self._compute_measure_meters)

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
        measures = self.measures
        default_units = parse_units(DEFAULT_UNITS).units

        meters = []
        governing: BeatUnit | None = None
        for start, beat_count in zip(measures.starts, measures.counts, strict=True):
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

    @staticmethod
    def get_extension_from_beat_pattern(
        beat_pattern: list[int],
        amount: int,
        start_index: int = 0,
        beats_on_starting_measure: int = 0,
    ) -> list[int]:
        return get_extension_from_beat_pattern(
            beat_pattern, amount, start_index, beats_on_starting_measure
        )

    def create_component(
        self, kind: ComponentKind, *args, id=None, **kwargs
    ) -> tuple[TC | None, str | None]:
        """
        A beat created without saying whether it starts a measure is placed
        by where it falls: after the last beat, it starts a measure once the
        last one has as many beats as the beat pattern gives it; before the
        first, it starts a measure of its own, numbered one less than the
        first, so a pickup is measure 0; anywhere else, it joins the measure
        it falls in. No other beat changes measure.
        """
        is_placed = kwargs.get("is_first_in_measure") is not None
        component, reason = super().create_component(kind, *args, id=id, **kwargs)
        manager = self.component_manager
        if (
            component is None
            or kind != ComponentKind.BEAT
            or manager.is_bulk
            or manager.is_restoring
        ):
            return component, reason

        if not is_placed:
            self._place_new_beat(component)
        self.ensure_first_beat_starts_measure()
        self._ensure_first_beat_unit()
        post(
            Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE,
            self.id,
            max(self.get_beat_index(component) - 1, 0),
        )
        return component, reason

    def _place_new_beat(self, beat: Beat) -> None:
        index = self.get_beat_index(beat)
        if len(self) == 1:
            self.set_component_data(beat.id, "is_first_in_measure", True)
            self.lay_planned_beat_units(0)
        elif index == 0:
            old_first = self[1]
            number = (
                1
                if old_first.measure_number_override is None
                else old_first.measure_number_override
            )
            if not old_first.is_first_in_measure:
                self.set_component_data(old_first.id, "is_first_in_measure", True)
            self.set_component_data(beat.id, "is_first_in_measure", True)
            if number >= 1:
                self.set_component_data(beat.id, "measure_number_override", number - 1)
        elif index == len(self) - 1:
            measures = self.measures
            last_measure = measures.count - 1
            beats_before = measures.counts[last_measure] - 1
            if beats_before >= self.get_planned_bar(last_measure).beat_count:
                self.set_component_data(beat.id, "is_first_in_measure", True)
                self.lay_planned_beat_units(last_measure + 1)

    def lay_planned_beat_units(self, from_measure: int) -> None:
        """
        Gives the measures from `from_measure` on the beat units the pattern
        plans for them, replacing theirs: one on the first beat of each
        measure whose planned time signature differs from the one before.
        Does nothing when the pattern gives no time signatures.
        """
        measures = self.measures
        if not self.plans_time_signatures or from_measure >= measures.count:
            return

        previous = None
        if from_measure:
            meter = self.get_measure_meter(from_measure - 1)
            previous = (meter.denominator, meter.units, meter.is_assumed)

        beats = self.components
        planned: dict[int | str, tuple[int, str, bool]] = {}
        for measure_index in range(from_measure, measures.count):
            bar = self.get_planned_bar(measure_index)
            meter = (bar.denominator, bar.units, bar.assumed)
            if meter != previous:
                beat_id = beats[measures.starts[measure_index]].id
                planned[beat_id] = (bar.denominator, bar.units_text, bar.assumed)
            previous = meter

        # Beat units already as planned are left in place, so the change
        # touches only what it changes.
        with self.component_manager.bulk():
            for beat_unit in self.beat_units:
                beat_index = self.get_beat_index(self.get_component(beat_unit.beat_id))
                if (
                    measures.measure_of_beat[beat_index] >= from_measure
                    and beat_unit.beat_id not in planned
                ):
                    self.component_manager.delete_component(beat_unit)

            for beat_id, (denominator, units, assumed) in planned.items():
                beat_unit = self.get_beat_unit_on_beat(beat_id)
                if beat_unit is None or (
                    beat_unit.denominator,
                    beat_unit.units,
                    beat_unit.assumed,
                ) != (denominator, units, assumed):
                    self.put_beat_unit_on_beat(beat_id, denominator, units, assumed)

    def ensure_first_beat_starts_measure(self) -> None:
        if len(self) and not self[0].is_first_in_measure:
            self.set_component_data(self[0].id, "is_first_in_measure", True)

    def mark_measures_from_legacy_lists(self) -> None:
        """
        Marks the beats that start measures from the lists by measure that
        files from before measures were marked on their beats store, fitted
        to the beats as TiLiA fitted them on loading. A measure gets a number
        of its own where it isn't one more than the measure before (or 1, for
        the first).
        """
        beats_in_measure, measure_numbers, always_shown = self._legacy_measure_lists
        self._legacy_measure_lists = ([], [], [])
        if not len(self):
            return

        counts, numbers = fit_legacy_lists(
            len(self), self.beat_pattern_bars, beats_in_measure, measure_numbers
        )
        starts = [0] + list(itertools.accumulate(counts[:-1]))
        for measure_index, start in enumerate(starts):
            beat = self[start]
            expected = numbers[measure_index - 1] + 1 if measure_index else 1
            if not beat.is_first_in_measure:
                self.set_component_data(beat.id, "is_first_in_measure", True)
            if numbers[measure_index] != expected:
                self.set_component_data(
                    beat.id, "measure_number_override", numbers[measure_index]
                )
            if measure_index in always_shown:
                self.set_component_data(beat.id, "measure_number_always_shown", True)

    def _ensure_first_beat_unit(self, copy_next: bool = True) -> None:
        """
        Keeps a beat unit in the first measure, so every measure is governed
        by one and every time signature label can be selected and edited.

        When one is missing, e.g. because a pickup was added before the old
        first beat, it copies the next beat unit's values (a pickup in a 6/8
        piece starts as 6/8); with no other beat units, or `copy_next` False,
        it gets the default. Either way it is assumed: nobody set a time
        signature on the measures before the next beat unit. Skipped while
        beats are being changed in bulk, which refreshes and calls this once
        at the end.
        """
        manager = self.component_manager
        if manager.is_restoring or manager.is_bulk or not len(self):
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

    def _ensure_metric_fraction_dicts(self) -> None:
        # get_time_by_measure memoizes into the dicts, so they are rebuilt
        # only when the beats have changed since they were last built.
        if self._metric_fraction_version != self.component_manager.version:
            self.update_metric_fraction_dicts()

    def update_metric_fraction_dicts(self):
        self._metric_fraction_version = self.component_manager.version
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
        """The index of the measure a beat is in, and its index there."""
        measures = self.measures
        if not 0 <= beat_index < len(measures.measure_of_beat):
            raise ValueError(f'No beat with index "{beat_index}" at {self}.')
        measure_index = measures.measure_of_beat[beat_index]
        return measure_index, beat_index - measures.starts[measure_index]

    def get_beat_index(self, beat: Beat) -> int:
        indices = self._cached(
            "beat_indices", lambda: {b.id: i for i, b in enumerate(self.components)}
        )
        return indices[beat.id]

    def _get_first_beat_of_measure(self, measure_index: int) -> Beat:
        return self[self.measures.starts[measure_index]]

    def _post_measures_changed(self, measure_index: int) -> None:
        post(
            Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE,
            self.id,
            self.measures.starts[measure_index],
        )

    def set_measure_number(self, measure_index: int, number: int) -> None:
        """
        Numbers a measure by hand. The measures after it that have no number
        of their own count on from it.
        """
        beat = self._get_first_beat_of_measure(measure_index)
        self.set_component_data(beat.id, "measure_number_override", number)
        if not number == 0:
            self.force_display_measure_number(measure_index)
        self._post_measures_changed(measure_index)

    def set_measure_numbers(self, numbers: list[int], start_measure: int = 0) -> None:
        """
        Numbers the measures from `start_measure` on, one per entry. A measure
        gets a number of its own, always shown unless it is 0, only where
        its number isn't the previous measure's plus one (or 1, for the first
        measure); elsewhere it counts on from the measure before.
        """
        measures = self.measures
        numbers = numbers[: measures.count - start_measure]
        with self.component_manager.bulk():
            for offset, number in enumerate(numbers):
                measure_index = start_measure + offset
                if offset:
                    previous = numbers[offset - 1]
                elif measure_index:
                    previous = measures.numbers[measure_index - 1]
                else:
                    previous = 0
                beat = self._get_first_beat_of_measure(measure_index)
                override = None if number == previous + 1 else number
                if beat.measure_number_override != override:
                    self.set_component_data(
                        beat.id, "measure_number_override", override
                    )
                if override not in (None, 0) and not beat.measure_number_always_shown:
                    self.set_component_data(
                        beat.id, "measure_number_always_shown", True
                    )
        self.refresh_measures()

    def reset_measure_number(self, measure_index: int) -> None:
        beat = self._get_first_beat_of_measure(measure_index)
        self.set_component_data(beat.id, "measure_number_override", None)
        self.unforce_display_measure_number(measure_index)

    def force_display_measure_number(self, measure_index: int) -> None:
        beat = self._get_first_beat_of_measure(measure_index)
        if not beat.measure_number_always_shown:
            self.set_component_data(beat.id, "measure_number_always_shown", True)

    def unforce_display_measure_number(self, measure_index: int) -> None:
        beat = self._get_first_beat_of_measure(measure_index)
        if beat.measure_number_always_shown:
            self.set_component_data(beat.id, "measure_number_always_shown", False)
        self._post_measures_changed(measure_index)

    def set_beat_amount_in_measure(self, measure_index: int, beat_amount: int) -> None:
        """
        Gives a measure `beat_amount` beats. The measures after it keep their
        number of beats, so their first beats move.
        """
        counts = self.beats_in_measure.copy()
        counts[measure_index] = beat_amount
        self._remeasure(counts, measure_index)

    def _remeasure(self, counts: list[int], from_measure: int) -> None:
        """
        Makes the measures from `from_measure` on hold `counts[from_measure:]`
        beats each. Each keeps its number, display and the beat unit on its
        first beat, by position. Beats left over at the end make measures
        from the beat pattern; measures past the last beat go.
        """
        measures = self.measures
        if not 0 <= from_measure < measures.count:
            return

        beats = self.components
        old_first_beats = [beats[start] for start in measures.starts[from_measure:]]
        kept_data = [
            (
                beat.measure_number_override,
                beat.measure_number_always_shown,
                self.get_beat_unit_on_beat(beat.id),
            )
            for beat in old_first_beats
        ]

        first = measures.starts[from_measure]
        remaining = len(beats) - first
        new_counts = []
        for count in counts[from_measure:]:
            if remaining <= 0:
                break
            new_counts.append(min(count, remaining))
            remaining -= new_counts[-1]
        if remaining:
            pattern = self.beat_pattern_bars
            new_counts += get_extension_from_beat_pattern(
                pattern,
                remaining,
                start_index=(from_measure + len(new_counts)) % len(pattern),
            )
        new_starts = [first] + [
            first + offset for offset in itertools.accumulate(new_counts[:-1])
        ]

        with self.component_manager.bulk():
            # Beat units that move are recreated on their measures' new first
            # beats, as moving them one by one could land one on a beat that
            # still holds another. Those that stay are left in place.
            beat_unit_values: list[tuple[int, str, bool] | None] = []
            for index, (_, _, beat_unit) in enumerate(kept_data):
                new_start = new_starts[index] if index < len(new_starts) else None
                old_first = old_first_beats[index]
                if beat_unit is None:
                    beat_unit_values.append(None)
                    continue
                if new_start is not None and beats[new_start] is old_first:
                    beat_unit_values.append(None)
                    continue
                beat_unit_values.append(
                    (beat_unit.denominator, beat_unit.units, beat_unit.assumed)
                )
                self.component_manager.delete_component(beat_unit)

            new_data = dict(zip(new_starts, kept_data, strict=False))
            new_starts_set = set(new_starts)
            for index in range(first, len(beats)):
                beat = beats[index]
                override, always_shown, _ = new_data.get(index, (None, False, None))
                values = {
                    "is_first_in_measure": index in new_starts_set,
                    "measure_number_override": override,
                    "measure_number_always_shown": always_shown,
                }
                for attr, value in values.items():
                    if getattr(beat, attr) != value:
                        self.set_component_data(beat.id, attr, value)

            for start, values in zip(new_starts, beat_unit_values, strict=False):
                if values is not None:
                    self.put_beat_unit_on_beat(beats[start].id, *values)

        self.refresh_measures()

    def distribute_beats(self, measure_index: int) -> None:
        self.component_manager.distribute_beats(measure_index)

    def refresh_measures(self) -> None:
        """
        Keeps the first beat starting a measure and carrying a beat unit, and
        has the UI relabel every beat. Run this after any bulk operation that
        added or removed beats.
        """
        self.ensure_first_beat_starts_measure()
        self._ensure_first_beat_unit()
        post(Post.BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE, self.id, 0)

    def recalculate_measures(self) -> None:
        self.refresh_measures()

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
        Sets the pattern and remeasures every beat from it, discarding bars
        set by hand. Each measure keeps its number and display by position.
        A pattern with time signatures gives every measure its beat unit; one
        with only numbers of beats leaves each measure the beat unit it had.
        """
        _, success = self.set_data("beat_pattern", pattern)
        if not success:
            return False

        if len(self):
            self._remeasure(
                get_extension_from_beat_pattern(self.beat_pattern_bars, len(self)), 0
            )
            self.lay_planned_beat_units(0)
            self.refresh_measures()
        return True

    def delete_components(self, components: list[TC]) -> None:
        self._validate_delete_components(components)

        manager = self.component_manager
        beat_units = [c for c in components if c.KIND == ComponentKind.BEAT_UNIT]
        # From the last beat back, so each deletion leaves the measures of
        # the beats still to be deleted as they were.
        beats = sorted(
            (c for c in components if c.KIND == ComponentKind.BEAT),
            key=self.get_beat_index,
            reverse=True,
        )
        for component in beat_units + beats:
            manager.delete_component(component)

        if manager.is_restoring or manager.is_bulk:
            return

        # Deleting the first measure's beat unit resets it to the default,
        # rather than copying the next one as a structural change would.
        if beat_units:
            self._ensure_first_beat_unit(copy_next=False)

        self.refresh_measures()

    class FillMethod(Enum):
        BY_AMOUNT = 0
        BY_INTERVAL = 1

    @long_operation("Creating beats...")
    def fill_with_beats(self, method: BeatTimeline.FillMethod, value: int | float):
        duration = get(Get.MEDIA_DURATION)
        if method == BeatTimeline.FillMethod.BY_AMOUNT:
            times = [i * duration / value for i in range(int(value))]
        else:
            times = [i * value for i in range(math.floor(duration / value))]

        counts = get_extension_from_beat_pattern(self.beat_pattern_bars, len(times))
        starts = {0, *itertools.accumulate(counts[:-1])}
        with self.component_manager.bulk():
            for i, time in enumerate(times):
                self.create_component(
                    ComponentKind.BEAT, time, is_first_in_measure=i in starts
                )
                post(Post.LONG_OPERATION, LongOperation.PROGRESS, i + 1, len(times))
            self.lay_planned_beat_units(0)

        self.refresh_measures()

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

        self.create_component(
            ComponentKind.BEAT,
            measure_zero_start,
            is_first_in_measure=True,
            measure_number_override=0,
        )

        return True, ""
