from __future__ import annotations

import functools
from typing import Iterable

from tilia.requests import get, Get
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.export import get_export_attributes_point_like
from tilia.timelines.base.metric_position import MetricPosition
from tilia.ui.format import format_media_time


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

    @classmethod
    def validate_creation(
        cls, time: float, existing_times: Iterable[float]
    ) -> tuple[bool, str]:
        """Requires unique times by default. Overwrite this or pass a filtered iterable to allow duplicate times."""
        return cls.compose_validators(
            [
                functools.partial(cls.validate_time_is_inbounds, time),
                functools.partial(cls.validate_unique_position, time, existing_times),
            ]
        )

    @classmethod
    def validate_unique_position(
        cls, time: float, existing_times: Iterable[float]
    ) -> tuple[bool, str]:
        if time in existing_times:
            return (
                False,
                f"There is already a {cls.frontend_name} at '{format_media_time(time)}'.",
            )
        else:
            return True, ""

    @staticmethod
    def validate_time_is_inbounds(time: float) -> tuple[bool, str]:
        media_duration = get(Get.MEDIA_DURATION)
        if time > media_duration:
            return (
                False,
                f"Time '{format_media_time(time)}' is bigger than media time '{format_media_time(media_duration)}'",
            )
        elif time < 0:
            return False, f"Time can't be negative. Got '{format_media_time(time)}'"
        else:
            return True, ""
