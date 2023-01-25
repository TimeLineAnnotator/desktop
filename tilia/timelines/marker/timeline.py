"""
Defines a MarkerTimeline and a HierarachyTLComponentManager.
"""

from __future__ import annotations

import logging

from tilia.timelines.state_actions import Action
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind

logger = logging.getLogger(__name__)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.collection import TimelineCollection

from tilia.timelines.common import (
    Timeline,
    TimelineComponentManager,
    log_object_creation,
    TimelineComponent,
)


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
