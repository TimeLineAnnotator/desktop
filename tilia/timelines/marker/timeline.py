"""
Defines a MarkerTimeline and a HierarachyTLComponentManager.
"""

from __future__ import annotations
import logging

from tilia import settings
from tilia.exceptions import CreateComponentError
from tilia.requests import Get, get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.common import (
    log_object_creation,
)
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager

logger = logging.getLogger(__name__)


class MarkerTimeline(Timeline):
    KIND = TimelineKind.MARKER_TIMELINE
    DEFAULT_HEIGHT = settings.get("marker_timeline", "default_height")

    @property
    def ordered_markers(self):
        return sorted(self.component_manager.get_components(), key=lambda m: m.time)

    @property
    def markers(self):
        return self.component_manager.get_components()

    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass

    def scale(self, factor: float) -> None:
        self.component_manager.scale(factor)

    def crop(self, length: float) -> None:
        self.component_manager.crop(length)


class MarkerTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.MARKER]

    @log_object_creation
    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)

    def scale(self, factor: float) -> None:
        logger.debug(f"Scaling markers in {self}...")
        for marker in self._components:
            marker.time *= factor
            marker.ui.update_position()

    def crop(self, length: float) -> None:
        logger.debug(f"Cropping markers in {self}...")
        for marker in self._components.copy():
            if marker.time > length:
                self.delete_component(marker)

    def _validate_component_creation(
        self, timeline: MarkerTimeline, time: float, **_
    ) -> None:
        if time > (media_length := get(Get.MEDIA_DURATION)):
            raise CreateComponentError(
                f"Time '{time}' is bigger than total time '{media_length}'"
            )
