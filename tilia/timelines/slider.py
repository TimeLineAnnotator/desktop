"""SliderTimeline class. Is wat simpler than other timelines so it doesn't need a separate module."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.collection import TimelineCollection
    from tilia.timelines.common import TimelineComponent

from tilia import events, globals_
from tilia.events import Event
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind

import logging

logger = logging.getLogger(__name__)


class SliderTimeline(Timeline):
    SERIALIZABLE_BY_UI_VALUE = ["is_visible", "display_position", "height"]
    SERIALIZABLE_BY_VALUE = []

    KIND = TimelineKind.SLIDER_TIMELINE

    def _validate_delete_components(self, component: TimelineComponent):
        """Nothing to do. Must impement abstract method."""

    def get_state(self) -> dict:
        logger.debug(f"Serializing {self}...")
        result = {}

        for attr in self.SERIALIZABLE_BY_UI_VALUE:
            result[attr] = getattr(self.ui, attr)

        result["kind"] = self.kind.name
        result["components"] = {}

        return result

    def clear(self, _=True):
        """Nothing to do."""

    def delete(self):
        """Nothing to do."""

    def restore_state(self, state: dict):
        """Nothing to do"""
