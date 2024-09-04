from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.settings import settings
from tilia.timelines.base.timeline import Timeline, TimelineFlag
from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent


class SliderTimeline(Timeline):
    SERIALIZABLE_BY_VALUE = ["is_visible", "ordinal", "height"]
    KIND = TimelineKind.SLIDER_TIMELINE
    FLAGS = [TimelineFlag.NOT_CLEARABLE, TimelineFlag.NOT_DELETABLE]

    @property
    def default_height(self):
        return settings.get("slider_timeline", "default_height")

    def get_state(self) -> dict:
        result = {}

        for attr in self.SERIALIZABLE_BY_VALUE:
            result[attr] = getattr(self, attr)

        result["kind"] = self.KIND.name
        result["components"] = {}

        return result

    def _validate_delete_components(self, component: TimelineComponent):
        """Nothing to do."""

    def deserialize_components(self, components: dict[int, dict[str]]):
        """Nothing to do."""

    def clear(self, _=True):
        """Nothing to do."""

    def delete(self):
        """Nothing to do."""

    def crop(self, length: float):
        """Nothing to do"""

    def scale(self, length: float):
        """Nothing to do"""
