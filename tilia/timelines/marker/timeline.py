from __future__ import annotations

import functools

from tilia.settings import settings
from tilia.requests import Get, get
from tilia.timelines.base.common import scale_discrete, crop_discrete
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager


class MarkerTimeline(Timeline):
    KIND = TimelineKind.MARKER_TIMELINE

    @property
    def default_height(self):
        return settings.get("marker_timeline", "default_height")
    
    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass


class MarkerTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.MARKER]

    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)
        self.scale = functools.partial(scale_discrete, self)
        self.crop = functools.partial(crop_discrete, self)

    def _validate_component_creation(self, _, time, *args, **kwargs):
        media_duration = get(Get.MEDIA_DURATION)
        if time > media_duration:
            return False, f"Time '{time}' is bigger than media time '{media_duration}'"
        elif time < 0:
            return False, f"Time can't be negative. Got '{time}'"
        else:
            return True, ""
