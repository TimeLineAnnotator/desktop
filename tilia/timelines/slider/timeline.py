from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.settings import settings
from tilia.timelines.base.timeline import Timeline, TimelineFlag
from tilia.timelines.hash_timelines import hash_function

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent


class SliderTimeline(Timeline):
    SERIALIZABLE = ["is_visible", "ordinal", "height", "measure_table", "fields"]
    FLAGS = [
        TimelineFlag.COMPONENTS_NOT_EDITABLE,
        TimelineFlag.NOT_CLEARABLE,
        TimelineFlag.NOT_DELETABLE,
        TimelineFlag.NOT_DUPLICATABLE,
        TimelineFlag.NOT_EXPORTABLE,
    ]

    @property
    def default_height(self):
        return settings.get("slider_timeline", "default_height")

    @property
    def components(self):
        return []

    @property
    def is_empty(self):
        return True

    def _validate_delete_components(self, component: TimelineComponent):
        """Nothing to do. Must implement abstract method."""

    def get_state(self) -> dict:
        """With a digest of its attributes, as every timeline has: a change to the
        slider alone is an unsaved change, and undo gives it back (FR-021;
        TimeLineAnnotator/project-management#628). It has no components."""
        state = self._get_base_state()
        state["components"] = {}
        state["components_hash"] = hash_function("")
        return state

    def deserialize_components(self, components: dict[str, dict[str]]):
        """Nothing to do."""

    def clear(self, _=True):
        """Nothing to do."""

    def delete(self):
        """Nothing to do."""

    def crop(self, length: float):
        """Nothing to do"""

    def scale(self, length: float):
        """Nothing to do"""
