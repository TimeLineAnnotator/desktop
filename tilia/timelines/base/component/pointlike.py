from __future__ import annotations

from tilia.requests import get, Get
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.export import get_export_attributes_point_like
from tilia.timelines.base.metric_position import MetricPosition


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
