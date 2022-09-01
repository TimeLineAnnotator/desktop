"""SliderTimeline class. Is wat simpler than other timelines so it doesn't need a separate module."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.collection import TimelineCollection
    from tilia.timelines.common import TimelineComponent

from tilia import events, globals_
from tilia.events import Subscriber, EventName
from tilia.timelines.common import Timeline
from tilia.timelines.timeline_kinds import TimelineKind


class SliderTimeline(Timeline):

    SERIALIZABLE_BY_UI_VALUE = []
    SERIALIZABLE_BY_VALUE = []

    KIND = TimelineKind.SLIDER_TIMELINE

    def _validate_delete_component(self, component: TimelineComponent):
        """Nothing to do. Must impement abstract method."""

    def to_dict(self) -> dict:
        return {"components": {}, "kind": self._kind.name}

    def clear(self, _=True):
        """Nothing to do."""

    def delete(self):
        """Nothing to do."""
