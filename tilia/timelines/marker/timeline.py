"""
Defines a MarkerTimeline and a HierarachyTLComponentManager.
"""

from __future__ import annotations

import logging

from tilia.exceptions import CreateComponentError
from tilia.timelines.state_actions import Action
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind

logger = logging.getLogger(__name__)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.collection import TimelineCollection

from tilia.timelines.common import (
    log_object_creation,
    TimelineComponent,
)
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager


class MarkerTimeline(Timeline):
    SERIALIZABLE_BY_VALUE = []
    SERIALIZABLE_BY_UI_VALUE = ["height", "is_visible", "name", "display_position"]

    KIND = TimelineKind.MARKER_TIMELINE

    def __init__(
        self,
        collection: TimelineCollection,
        component_manager: MarkerTLComponentManager,
        **kwargs,
    ):
        super().__init__(
            collection, component_manager, TimelineKind.MARKER_TIMELINE, **kwargs
        )

    @property
    def ordered_markers(self):
        return sorted(self.component_manager.get_components(), key=lambda m: m.time)

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
        if time > (media_length := self.timeline.get_media_length()):
            raise CreateComponentError(
                f"Time '{time}' is bigger than total time '{media_length}'"
            )
