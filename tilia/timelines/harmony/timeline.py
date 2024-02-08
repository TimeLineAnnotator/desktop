from __future__ import annotations
import logging
from typing import Self

from tilia import settings
from tilia.exceptions import CreateComponentError
from tilia.requests import Get, get, post, Post
from tilia.timelines.base.validators import validate_positive_integer
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.validators import validate_level_count
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager

logger = logging.getLogger(__name__)


class HarmonyTimeline(Timeline):
    KIND = TimelineKind.HARMONY_TIMELINE
    DEFAULT_LEVEL_HEIGHT = 35
    SERIALIZABLE_BY_VALUE = [
        "level_count",
        "level_height",
        "is_visible",
        "name",
        "ordinal",
        "visible_level_count",
    ]

    def __init__(
        self,
        component_manager: HarmonyTLComponentManager,
        name: str = "",
        level_count: int = 1,
        level_height: int = DEFAULT_LEVEL_HEIGHT,
        visible_level_count: int = 2,
        **kwargs,
    ):
        self.level_count = level_count
        self.level_height = level_height
        self.visible_level_count = visible_level_count
        self.validators = self.validators | {
            "level_count": validate_level_count,
            "level_height": validate_positive_integer,
            "visible_level_count": validate_level_count,
        }

        super().__init__(
            name=name,
            height=visible_level_count * level_height,
            component_manager=component_manager,
            **kwargs,
        )

    @property
    def height(self):
        return self.get_data("visible_level_count") * self.get_data("level_height")

    @height.setter
    def height(self, value):
        self.set_data(
            "level_height", value / self.visible_level_count
        )  # should we set level_height to value instead?

    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass

    def scale(self, factor: float) -> None:
        self.component_manager: HarmonyTLComponentManager
        self.component_manager.scale(factor)

    def crop(self, length: float) -> None:
        self.component_manager: HarmonyTLComponentManager
        self.component_manager.crop(length)

    def restore_state(self, state: dict):
        self.clear()
        self.set_data("name", state["name"])
        self.set_data("level_count", state["level_count"])
        self.set_data("level_height", state["level_height"])
        self.component_manager.deserialize_components(state["components"])


class HarmonyTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.HARMONY, ComponentKind.MODE]

    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)

    def _validate_component_creation(
        self,
        kind: ComponentKind,
        time: float,
        *_,
        **__,
    ):
        media_duration = get(Get.MEDIA_DURATION)
        if time > media_duration:
            return False, f"Time '{time}' is bigger than media time '{media_duration}'"
        if time < 0:
            return False, f"Time can't be negative. Got '{time}'"
        if time in [h.get_data("time") for h in self.timeline]:
            component_at_same_time = self.timeline.get_component_by_attr('time', time)
            if type(component_at_same_time) == self._get_component_class_by_kind(kind):
                return (
                    False,
                    f"Can't create harmony.\nThere is already a harmony at time='{time}'.",
                )

        return True, ""

    def scale(self, factor: float) -> None:
        for component in self:
            component.set_data("time", component.get_data("time") * factor)

    def crop(self, length: float) -> None:
        for component in list(self).copy():
            if component.get_data("time") > length:
                self.delete_component(component)
