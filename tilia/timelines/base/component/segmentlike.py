from __future__ import annotations

from tilia.requests import get, Get
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.export import get_export_attributes_extended
from tilia.timelines.base.metric_position import MetricInterval, MetricPosition


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
