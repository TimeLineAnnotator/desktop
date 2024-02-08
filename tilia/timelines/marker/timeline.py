from __future__ import annotations
import logging

from tilia import settings
from tilia.exceptions import CreateComponentError
from tilia.requests import Get, get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager

logger = logging.getLogger(__name__)


class MarkerTimeline(Timeline):
    KIND = TimelineKind.MARKER_TIMELINE
    DEFAULT_HEIGHT = settings.get("marker_timeline", "default_height")

    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass

    def scale(self, factor: float) -> None:
        self.component_manager: MarkerTLComponentManager
        self.component_manager.scale(factor)

    def crop(self, length: float) -> None:
        self.component_manager: MarkerTLComponentManager
        self.component_manager.crop(length)


class MarkerTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.MARKER]

    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)

    def _validate_component_creation(self, _, time, *args, **kwargs):
        media_duration = get(Get.MEDIA_DURATION)
        if time > media_duration:
            return False, f"Time '{time}' is bigger than media time '{media_duration}'"
        elif time < 0:
            return False, f"Time can't be negative. Got '{time}'"
        else:
            return True, ""

    def scale(self, factor: float) -> None:
        for marker in self:
            marker.set_data("time", marker.get_data("time") * factor)

    def crop(self, length: float) -> None:
        for marker in list(self).copy():
            if marker.get_data("time") > length:
                self.delete_component(marker)
