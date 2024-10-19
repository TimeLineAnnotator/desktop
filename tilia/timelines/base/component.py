from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from tilia.requests import get, Get
from tilia.timelines.base.metric_position import MetricPosition, MetricInterval
from tilia.timelines.base.export import get_export_attributes_point_like, get_export_attributes_extended

from tilia.utils import get_tilia_class_string
from tilia.exceptions import SetComponentDataError, GetComponentDataError
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.base.validators import validate_read_only


class TimelineComponent(ABC):
    SERIALIZABLE_BY_VALUE = []
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []
    ORDERING_ATTRS = tuple()

    validators = {
        "timeline": validate_read_only,
        "id": validate_read_only,
    }

    def __init__(self, timeline: Timeline, id: int, *args, **kwargs):
        self.timeline = timeline
        self.id = id

    def __str__(self):
        return get_tilia_class_string(self)

    def __lt__(self, other):
        return self.ordinal < other.ordinal

    @property
    def ordinal(self):
        return tuple(getattr(self, attr) for attr in self.ORDERING_ATTRS)

    def validate_set_data(self, attr, value):
        if not hasattr(self, attr):
            raise SetComponentDataError(
                f"Component '{self}' has no attribute named '{attr}'. Can't set to '{value}'."
            )
        try:
            return self.validators[attr](value)
        except KeyError:
            raise KeyError(
                f"{self} has no validator for attribute {attr}. Can't set to '{value}'."
            )

    def set_data(self, attr: str, value: Any):
        if not self.validate_set_data(attr, value):
            return None, False
        setattr(self, attr, value)
        if attr in self.ORDERING_ATTRS:
            self.timeline.update_component_order(self)
        return value, True

    def validate_get_data(self, attr):
        if not hasattr(self, attr):
            raise GetComponentDataError(
                f"Component '{self}' has no attribute named '{attr}'"
            )
        return True

    def get_data(self, attr: str):
        if self.validate_get_data(attr):
            return getattr(self, attr)


class PointLikeTimelineComponent(TimelineComponent):
    @property
    def metric_position(self) -> MetricPosition | None:
        return get(Get.METRIC_POSITION, self.get_data("time"))

    @property
    def measure(self) -> int | None:
        return self.metric_position.measure if self.metric_position else None

    @property
    def beat(self) -> int | None:
        return self.metric_position.beat if self.metric_position else None

    @classmethod
    def get_export_attributes(cls) -> list[str]:
        return get_export_attributes_point_like(cls)


class SegmentLikeTimelineComponent(TimelineComponent):
    start: float
    end: float

    @property
    def length(self):
        return self.get_data('end') - self.get_data('start')

    @property
    def length_metric(self) -> MetricInterval | None:
        start_metric_position = self.start_metric_position
        end_metric_position = self.end_metric_position
        if not start_metric_position:
            return None
        return end_metric_position - start_metric_position

    @property
    def length_in_measures(self) -> tuple[int, int] | None:
        # A workaround to facilitate exporting.
        # This is only needed because the property name
        # is currently coupled to the name of the
        # attribute in the exported file.
        if not self.length_metric:
            return None
        return self.length_metric.measures, self.length_metric.beats

    @property
    def start_metric_position(self) -> MetricPosition | None:
        return get(Get.METRIC_POSITION, self.get_data("start"))

    @property
    def end_metric_position(self) -> MetricPosition | None:
        return get(Get.METRIC_POSITION, self.get_data("end"))

    @property
    def start_measure(self) -> int | None:
        return self.start_metric_position.measure if self.start_metric_position else None

    @property
    def start_beat(self) -> int | None:
        return self.start_metric_position.beat if self.start_metric_position else None

    @property
    def end_measure(self) -> int | None:
        return self.end_metric_position.measure if self.end_metric_position else None

    @property
    def end_beat(self) -> int | None:
        return self.end_metric_position.beat if self.end_metric_position else None

    @classmethod
    def get_export_attributes(cls) -> list[str]:
        return get_export_attributes_extended(cls)
