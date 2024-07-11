from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.requests import Get, get
from tilia.settings import settings
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent


class SliderTimeline(Timeline):
    SERIALIZABLE_BY_VALUE = ["is_visible", "ordinal", "height"]

    KIND = TimelineKind.SLIDER_TIMELINE

    @property
    def default_height(self):
        return settings.get("slider_timeline", "default_height")

    def _validate_delete_components(self, component: TimelineComponent):
        """Nothing to do. Must impement abstract method."""
            
    def get_state(self) -> dict:
        result = {}

        for attr in self.SERIALIZABLE_BY_VALUE:
            result[attr] = getattr(self, attr)

        result["kind"] = self.KIND.name
        result["components"] = {}

        return result

    def deserialize_components(self, components: dict[int, dict[str]]):
        pass

    def clear(self, _=True):
        """Nothing to do."""

    def delete(self):
        """Nothing to do."""

    def crop(self):
        """Nothing to do"""
