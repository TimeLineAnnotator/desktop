from __future__ import annotations
from typing import TYPE_CHECKING
import logging

from tilia import settings
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent


class SliderTimeline(Timeline):
    SERIALIZABLE_BY_VALUE = ["is_visible", "display_position", "height"]

    KIND = TimelineKind.SLIDER_TIMELINE
    DEFAULT_HEIGHT = settings.get("slider_timeline", "default_height")

    def _validate_delete_components(self, component: TimelineComponent):
        """Nothing to do. Must impement abstract method."""

    def get_state(self) -> dict:
        logger.debug(f"Serializing {self}...")
        result = {}

        for attr in self.SERIALIZABLE_BY_VALUE:
            result[attr] = getattr(self, attr)

        result["kind"] = self.kind.name
        result["components"] = {}

        return result

    def clear(self, _=True):
        """Nothing to do."""

    def delete(self):
        """Nothing to do."""

    def restore_state(self, state: dict):
        """Nothing to do"""
