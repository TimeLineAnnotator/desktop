from __future__ import annotations

from tilia.settings import settings
from tilia.requests import Get, get
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

    def scale(self, offset: float, factor: float) -> None:
        self.component_manager: MarkerTLComponentManager
        self.component_manager.scale(offset, factor)

    def crop(self, start: float, end: float) -> None:
        self.component_manager: MarkerTLComponentManager
        self.component_manager.crop(start, end)


class MarkerTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.MARKER]

    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)

    def _validate_component_creation(self, _, time, *args, **kwargs):
        playback_time = get(Get.MEDIA_TIMES_PLAYBACK)
        media_duration = get(Get.MEDIA_DURATION)
        if playback_time.end != 0 and time > playback_time.end:
            return (
                False,
                f"Time '{time}' is greater than current media time '{playback_time.end}'",
            )
        elif playback_time.end == 0 and time > media_duration:
            return (
                False,
                f"Time '{time}' is greater than current media time '{media_duration}'",
            )
        elif time < playback_time.start:
            return (
                False,
                f"Time '{time}' is less than current media start time '{playback_time.start}",
            )
        else:
            return True, ""

    def scale(self, offset: float, factor: float) -> None:
        for marker in self:
            marker.set_data("time", marker.get_data("time") * factor + offset)

    def crop(self, start: float, end: float) -> None:
        for marker in list(self).copy():
            if not start <= marker.get_data("time") <= end:
                self.delete_component(marker)
