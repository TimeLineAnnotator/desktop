"""
Defines the Marker class, the single TimelineComponent kind of a MarkerTimeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.timelines.base.validators import (
    validate_time,
    validate_color,
    validate_string,
)
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.marker.timeline import MarkerTimeline

from tilia.timelines.base.component import PointLikeTimelineComponent


class Marker(PointLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = ["time", "comments", "label", "color"]
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []
    ORDERING_ATTRS = ("time",)

    KIND = ComponentKind.MARKER

    validators = {
        "timeline": lambda _: False,
        "id": lambda _: False,
        "time": validate_time,
        "label": validate_string,
        "color": validate_color,
        "comments": validate_string,
    }

    def __init__(
        self,
        timeline: MarkerTimeline,
        id: int,
        time: float,
        label="",
        color=None,
        comments="",
        **_,
    ):
        super().__init__(timeline, id)

        self.time = time
        self.label = label
        self.color = color
        self.comments = comments

    def __str__(self):
        return f"Marker({self.time})"

    def __repr__(self):
        return str(dict(self.__dict__.items()))

