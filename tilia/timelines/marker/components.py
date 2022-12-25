"""
Defines the Marker class, the single TimelineComponent kind of a MarkerTimeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import logging

from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.marker.timeline import MarkerTimeline

from tilia.exceptions import AppException

from tilia.timelines.common import (
    TimelineComponent,
)



logger = logging.getLogger(__name__)


class MarkerLoadError(Exception):
    pass


class Marker(TimelineComponent):

    # serializer attributes
    SERIALIZABLE_BY_VALUE = [
        "time",
        "comments",
    ]

    SERIALIZABLE_BY_UI_VALUE = ["label", "color"]
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []

    KIND = ComponentKind.MARKER

    def __init__(
        self,
        timeline: MarkerTimeline,
        time: float,
        comments="",
        **_,
    ):

        super().__init__(timeline)

        self._time = time
        self.comments = comments

    @classmethod
    def create(
        cls, timeline: MarkerTimeline, time: float, **kwargs
    ):
        return Marker(timeline, time, **kwargs)

    def receive_delete_request_from_ui(self) -> None:
        self.timeline.on_request_to_delete_components([self])
        self.ui.delete()

    @property
    def time(self):
        return self._time

    @time.setter
    def time(self, value):
        logger.debug(f"Setting {self} start to {value}")
        self._time = value


    def __str__(self):
        return f"Marker({self.time})"


class MarkerOperationError(AppException):
    pass
