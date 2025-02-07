from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.timelines.base.export import get_export_attributes_point_like
from tilia.timelines.base.metric_position import MetricPosition
from tilia.timelines.base.validators import validate_time, validate_bool
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.beat.timeline import BeatTimeline

from tilia.timelines.base.component import PointLikeTimelineComponent


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

        super().__init__(timeline, id)

    def __str__(self):
        return f"Beat({self.time})"

    def __repr__(self):
        return f"Beat({self.time})"

    @property
    def metric_position(self) -> MetricPosition:
        self.timeline: BeatTimeline
        beat_index = self.timeline.get_beat_index(self)
        measure_index, index_in_measure = self.timeline.get_measure_index(beat_index)

        return MetricPosition(
            self.timeline.measure_numbers[measure_index],
            index_in_measure + 1,
            self.timeline.beats_in_measure[measure_index],
        )

    @property
    def measure_number(self):
        return self.metric_position.measure

    @property
    def beat_number(self):
        return self.metric_position.beat

    @classmethod
    def get_export_attributes(cls) -> list[str]:
        return get_export_attributes_point_like(cls)

    def set_data(self, attr, value):
        value, success = super().set_data(attr, value)
        if success:
            self.timeline.update_metric_fraction_dicts()
        return value, success
