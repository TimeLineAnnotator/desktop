from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from tilia.requests import get, Get
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
    @classmethod
    def get_export_attributes(cls) -> list[str]:
        return get_export_attributes_point_like(cls)

    @property
    def metric_position(self) -> tuple[int | None, int | None]:
        return get(Get.METRIC_POSITION, self.get_data("time"))

    @property
    def measure(self) -> int | None:
        return self.metric_position[0]

    @property
    def beat(self) -> int | None:
        return self.metric_position[1]


class ExtendedTimelineComponent(TimelineComponent):
    start: float
    end: float

    @property
    def length(self):
        return self.get_data('end') - self.get_data('start')

    @property
    def length_in_measures(self):
        start_measure, start_beat = self.start_metric_position
        end_measure, end_beat = self.end_metric_position
        if not start_measure:
            return None, None
        return end_measure - start_measure, end_beat - start_beat

    @property
    def start_metric_position(self) -> tuple[int | None, int | None]:
        return get(Get.METRIC_POSITION, self.get_data("start"))

    @property
    def end_metric_position(self) -> tuple[int | None, int | None]:
        return get(Get.METRIC_POSITION, self.get_data("end"))

    @property
    def start_measure(self) -> int | None:
        return self.start_metric_position[0]

    @property
    def start_beat(self) -> int | None:
        return self.start_metric_position[1]

    @property
    def end_measure(self) -> int | None:
        return self.end_metric_position[0]

    @property
    def end_beat(self) -> int | None:
        return self.end_metric_position[1]

    @classmethod
    def get_export_attributes(cls) -> list[str]:
        return get_export_attributes_extended(cls)

