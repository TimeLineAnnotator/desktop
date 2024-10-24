from __future__ import annotations

import functools

from tilia.settings import settings
from tilia.timelines.base.common import scale_discrete, crop_discrete
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.components import Marker
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager


class MarkerTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: MarkerTimeline):
        super().__init__(timeline, [ComponentKind.MARKER])
        self.scale = functools.partial(scale_discrete, self)
        self.crop = functools.partial(crop_discrete, self)

    def _validate_component_creation(self, _, time, *args, **kwargs):
        return Marker.validate_creation(time, {c.get_data("time") for c in self})


class MarkerTimeline(Timeline):
    KIND = TimelineKind.MARKER_TIMELINE
    COMPONENT_MANAGER_CLASS = MarkerTLComponentManager

    @property
    def default_height(self):
        return settings.get("marker_timeline", "default_height")

    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass
