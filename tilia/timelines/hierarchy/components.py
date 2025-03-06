from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.requests import get, Get
from tilia.timelines.base.validators import (
    validate_time,
    validate_string,
    validate_color,
    validate_read_only,
    validate_pre_validated,
)
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.base.component import SegmentLikeTimelineComponent

if TYPE_CHECKING:
    from tilia.timelines.hierarchy.timeline import HierarchyTimeline


class HierarchyLoadError(Exception):
    pass


class Hierarchy(SegmentLikeTimelineComponent):
    SERIALIZABLE = [
        "start",
        "pre_start",
        "end",
        "post_end",
        "level",
        "label",
        "color",
        "formal_type",
        "formal_function",
        "comments",
    ]

    validators = {
        "timeline": validate_read_only,
        "id": validate_read_only,
        "start": validate_time,
        "end": validate_time,
        "pre_start": validate_time,
        "post_end": validate_time,
        "label": validate_string,
        "color": validate_color,
        "comments": validate_string,
        "level": validate_pre_validated,
        "formal_type": validate_string,
        "formal_function": validate_string,
    }

    KIND = ComponentKind.HIERARCHY
    ORDERING_ATTRS = ("level", "start")

    def __init__(
        self,
        timeline: HierarchyTimeline,
        id: int,
        start: float,
        end: float,
        level: int,
        label: str = "",
        comments="",
        pre_start=None,
        post_end=None,
        color="",
        formal_type="",
        formal_function="",
        **_,
    ):

        self._start = start
        self._end = end
        self.level = level
        self.label = label
        self.comments = comments
        self.color = color

        self.formal_type = formal_type
        self.formal_function = formal_function

        self.pre_start = pre_start if pre_start is not None else self.start
        self.post_end = post_end if post_end is not None else self.end

        super().__init__(timeline, id)

    @property
    def parent(self):
        return self.timeline.component_manager.get_parent(self)

    @property
    def children(self):
        return self.timeline.component_manager.get_children(self)

    @property
    def start(self):
        return self._start

    @start.setter
    def start(self, value):
        prev_start = self._start
        self._start = value
        if self.pre_start > value or self.pre_start == prev_start:
            self.pre_start = value

    @property
    def end(self):
        return self._end

    @end.setter
    def end(self, value):
        prev_end = self._end
        self._end = value
        if self.post_end < value or self.post_end == prev_end:
            self.post_end = value

    @property
    def loop_start(self) -> float:
        return self.pre_start

    @property
    def loop_end(self) -> float:
        return self.post_end

    @property
    def pre_start_metric_position(self):
        return get(Get.METRIC_POSITION, self.pre_start)

    @property
    def post_end_metric_position(self):
        return get(Get.METRIC_POSITION, self.post_end)

    @property
    def pre_start_measure(self):
        return self.pre_start_metric_position.measure

    @property
    def pre_start_beat(self):
        return self.pre_start_metric_position.beat

    @property
    def post_end_measure(self):
        return self.post_end_metric_position.measure

    @property
    def post_end_beat(self):
        return self.post_end_metric_position.beat

    def __repr__(self):
        repr_ = f"Hierarchy({self.start}, {self.end}, {self.level}"
        try:
            if self.label:
                repr_ += f", {self.label}"
        except AttributeError:
            pass  # UI has not been created yet
        repr_ += ")"
        return repr_
