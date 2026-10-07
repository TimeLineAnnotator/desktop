from __future__ import annotations

import math
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from tilia.timelines.base.metric_position import MetricPosition
from tilia.timelines.base.validators import (
    validate_bool,
    validate_read_only,
    validate_time,
)
from tilia.timelines.beat.units import (
    DEFAULT_DENOMINATOR,
    DEFAULT_UNITS,
    format_units,
    parse_units,
    validate_denominator,
)
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.beat.timeline import BeatTimeline

from tilia.timelines.base.component import (
    PointLikeTimelineComponent,
    TimelineComponent,
)


class Beat(PointLikeTimelineComponent):
    SERIALIZABLE = ["time"]
    ORDERING_ATTRS = ("time",)
    KIND = ComponentKind.BEAT

    validators = {"time": validate_time, "is_first_in_measure": validate_bool}

    def __init__(
        self,
        timeline: BeatTimeline,
        id: int,
        time: float,
        comments="",
        **_,
    ):
        self.time = time
        self.comments = comments
        self.is_first_in_measure = False
        self._cached_metric_position = None

        super().__init__(timeline, id)

    def __str__(self):
        return f"Beat({self.time})"

    def __repr__(self):
        return f"Beat({self.time})"

    def clear_cached_metric_position(self):
        self._cached_metric_position = None

    @property
    def metric_position(self) -> MetricPosition:
        if self._cached_metric_position is None:
            self.timeline: BeatTimeline
            beat_index = self.timeline.get_beat_index(self)
            measure_index, index_in_measure = self.timeline.get_measure_index(
                beat_index
            )

            self._cached_metric_position = MetricPosition(
                self.timeline.measure_numbers[measure_index],
                index_in_measure + 1,
                self.timeline.beats_in_measure[measure_index],
            )

        return self._cached_metric_position

    @property
    def measure_number(self):
        return self.metric_position.measure

    @property
    def beat_number(self):
        return self.metric_position.beat


def validate_units(value: str) -> bool:
    return isinstance(value, str) and parse_units(value).is_valid


def validate_component_id(value: int | str) -> bool:
    # Ids come from Get.ID as strings; tests and old code also use ints.
    return isinstance(value, (int, str))


class BeatUnit(TimelineComponent):
    """
    What one tapped beat is worth in notation, from the start of the measure
    containing the beat it is attached to until the next beat unit. See
    `tilia.timelines.beat.units`.

    `assumed` marks values TiLiA filled in rather than the user, such as
    the 4 / 1 given to the first beat: tapping can't tell 6/8 in two from
    2/4. Setting the beat unit explicitly clears it.
    """

    SERIALIZABLE = ["beat_id", "denominator", "units", "assumed"]
    ORDERING_ATTRS = ("id",)
    KIND = ComponentKind.BEAT_UNIT

    validators = {
        "timeline": validate_read_only,
        "id": validate_read_only,
        "beat_id": validate_component_id,
        "denominator": validate_denominator,
        "units": validate_units,
        "assumed": validate_bool,
    }

    def __init__(
        self,
        timeline: BeatTimeline,
        id: int,
        beat_id: int | str,
        denominator: int = DEFAULT_DENOMINATOR,
        units: str = DEFAULT_UNITS,
        assumed: bool = False,
        **_,
    ) -> None:
        self.beat_id = beat_id
        self.denominator = denominator
        self.assumed = assumed
        # Stored in canonical text form ("2+3") so it serializes and hashes
        # as a string.
        self.units = format_units(parse_units(units).units)

        super().__init__(timeline, id)

    def __str__(self) -> str:
        assumed = ", assumed" if self.assumed else ""
        return (
            f"BeatUnit({self.denominator} / {self.units} on beat {self.beat_id}"
            f"{assumed})"
        )

    def __repr__(self) -> str:
        return str(self)

    def set_data(self, attr: str, value: Any) -> tuple[Any, bool]:
        if attr == "units" and validate_units(value):
            value = format_units(parse_units(value).units)
        return super().set_data(attr, value)

    @classmethod
    def get_export_attributes(cls) -> list[str]:
        # Like Staff, a beat unit has no time of its own to export.
        return cls.SERIALIZABLE

    @property
    def ordinal(self) -> tuple[float, str]:
        # Sorts after every beat (whose ordinal is its time), so beat units
        # never sit between beats in the timeline UI's element list.
        return math.inf, str(self.id)

    @property
    def unit_values(self) -> list[Fraction]:
        return parse_units(self.units).units

    @classmethod
    def validate_creation(
        cls,
        beat_id: int,
        denominator: int = DEFAULT_DENOMINATOR,
        units: str = DEFAULT_UNITS,
        *,
        beat_ids: set[int],
        taken_beat_ids: set[int],
        **_,
    ) -> tuple[bool, str]:
        if beat_id not in beat_ids:
            return False, f"No beat with id {beat_id}."
        if beat_id in taken_beat_ids:
            return False, f"Beat {beat_id} already has a beat unit."
        if not validate_denominator(denominator):
            return False, f"Invalid denominator: {denominator}."
        if not validate_units(units):
            return False, f"Invalid units: {units}."
        return True, ""
