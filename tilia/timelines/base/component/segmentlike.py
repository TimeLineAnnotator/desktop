from __future__ import annotations

import functools
from typing import Iterable, TypeVar

from tilia.requests import get, Get
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.export import get_export_attributes_extended
from tilia.timelines.base.metric_position import MetricInterval, MetricPosition
from tilia.timelines.base.timeline import TimelineComponentManager

T = TypeVar("T")


class SegmentLikeTimelineComponent(TimelineComponent):
    start: float
    end: float

    @property
    def length(self):
        return self.get_data("end") - self.get_data("start")

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
        return (
            self.start_metric_position.measure if self.start_metric_position else None
        )

    @property
    def start_beat(self) -> int | None:
        return self.start_metric_position.beat if self.start_metric_position else None

    @property
    def end_measure(self) -> int | None:
        return self.end_metric_position.measure if self.end_metric_position else None

    @property
    def end_beat(self) -> int | None:
        return self.end_metric_position.beat if self.end_metric_position else None

    @property
    def loop_start(self) -> float:
        return self.get_data("start")

    @property
    def loop_end(self):
        return self.get_data("end")

    @classmethod
    def get_export_attributes(cls) -> list[str]:
        return get_export_attributes_extended(cls)

    @classmethod
    def validate_creation(
        cls, start: float, end: float, position: T, existing_positions: Iterable[T]
    ) -> tuple[bool, str]:
        return cls.compose_validators(
            [
                functools.partial(cls.validate_times, start, end),
                functools.partial(
                    cls.validate_unique_position, position, existing_positions
                ),
            ]
        )

    @staticmethod
    def validate_times(start: float, end: float) -> tuple[bool, str]:
        media_duration = get(Get.MEDIA_DURATION)
        if start > media_duration:
            return (
                False,
                f"Start time '{start}' is bigger than media time '{media_duration}'",
            )
        elif end > media_duration:
            return (
                False,
                f"End time '{end}' is bigger than media time '{media_duration}'",
            )
        elif end <= start:
            return False, f"End time '{end}' should be bigger than start time '{start}'"
        else:
            return True, ""

    @classmethod
    def validate_unique_position(
        cls, position: T, existing_positions: Iterable[T]
    ) -> tuple[bool, str]:
        """
        Position should be whatever uniquely identifies a component.
        Typically, it will be tuple with start, end and some other attributes.
        For hierarchies, for example, it is (start, end, level).
        """
        if position in existing_positions:
            return (
                False,
                f"There is already a {cls.frontend_name()} component at the selected position.",
            )
        return True, ""


def scale_segmentlike(cm: TimelineComponentManager, factor: float) -> None:
    for component in cm:
        # attributes need to be set directly
        # to override validation
        component.start = component.get_data("start") * factor
        component.end = component.get_data("end") * factor


def crop_segmentlike(cm: TimelineComponentManager, length: float) -> None:
    for component in list(cm).copy():
        start = component.get_data("start")
        end = component.get_data("end")
        if start >= length:
            cm.delete_component(component)
        elif end > length:
            component.set_data("end", length)
