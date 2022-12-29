"""
Defines the Beat class, the single TimelineComponent kind of a BeatTimeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import logging

from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.beat.timeline import BeatTimeline

from tilia.exceptions import AppException

from tilia.timelines.common import (
    TimelineComponent,
)


logger = logging.getLogger(__name__)


class BeatLoadError(Exception):
    pass


class Beat(TimelineComponent):

    # serializer attributes
    SERIALIZABLE_BY_VALUE = ["time"]

    SERIALIZABLE_BY_UI_VALUE = []
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []

    KIND = ComponentKind.BEAT

    def __init__(
        self,
        timeline: BeatTimeline,
        time: float,
        comments="",
        **_,
    ):

        super().__init__(timeline)

        self._time = time
        self.comments = comments

    @classmethod
    def create(cls, timeline: BeatTimeline, time: float):
        return Beat(timeline, time)

    def receive_delete_request_from_ui(self) -> None:
        self.timeline.on_request_to_delete_components([self])
        self.ui.delete()

    @property
    def time(self):
        return self._time

    @time.setter
    def time(self, value):
        logger.debug(f"Setting {self} time to {value}")
        self._time = value

    def __str__(self):
        return f"Beat({self.time})"

    def __repr__(self):
        return f"Beat({self.time})"


class BeatOperationError(AppException):
    pass
