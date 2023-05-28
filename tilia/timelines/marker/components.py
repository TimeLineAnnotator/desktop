"""
Defines the Marker class, the single TimelineComponent kind of a MarkerTimeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import logging

from tilia import settings
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.marker.timeline import MarkerTimeline

from tilia.exceptions import TiliaException

from tilia.timelines.base.component import TimelineComponent

logger = logging.getLogger(__name__)


class MarkerLoadError(Exception):
    pass


class Marker(TimelineComponent):
    # serializer attributes
    SERIALIZABLE_BY_VALUE = ["time", "comments", "label", "color"]
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []

    KIND = ComponentKind.MARKER

    def __init__(
        self,
        timeline: MarkerTimeline,
        time: float,
        label="",
        color=settings.get("marker_timeline", "marker_default_color"),
        comments="",
        **_,
    ):
        super().__init__(timeline)

        self.time = time
        self.label = label
        self.color = color
        self.comments = comments

    @classmethod
    def create(cls, *args, **kwargs):
        return Marker(*args, **kwargs)

    def receive_delete_request_from_ui(self) -> None:
        self.timeline.on_request_to_delete_components([self])

    def __str__(self):
        return f"Marker({self.time})"


class MarkerOperationError(TiliaException):
    pass
