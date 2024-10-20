from __future__ import annotations

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


def validate_pointlike_component_creation(time: float) -> tuple[bool, str]:
    media_duration = get(Get.MEDIA_DURATION)
    if time > media_duration:
        return False, f"Time '{format_media_time(time)}' is bigger than media time '{format_media_time(media_duration)}'"
    elif time < 0:
        return False, f"Time can't be negative. Got '{format_media_time(time)}'"
    else:
        return True, ""


def validate_unique_position_pointlike_component(time: float, components: list[PointLikeTimelineComponent]) -> tuple[bool, str]:
    if time in [c.get_data("time") for c in components]:
        return False, f"There is already a {components[0].user_friendly_name} at '{format_media_time(time)}'."
    else:
        return True, ""
