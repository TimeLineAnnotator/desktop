from __future__ import annotations

from bisect import bisect

import music21

from tilia.requests import Get, get, post, Post
from tilia.timelines.base.validators import validate_positive_integer
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.validators import validate_level_count
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager, TC


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

    def modes(self):
        return self.component_manager.get_components_by_condition(
            lambda _: True, ComponentKind.MODE
        )

    def harmonies(self):
        return self.component_manager.get_components_by_condition(
            lambda _: True, ComponentKind.HARMONY
        )

    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass

    def get_key_by_time(self, time: float) -> music21.key.Key:
        modes = sorted(self.modes())
        idx = bisect([mode.get_data("time") for mode in modes], time)
        if not idx:
            return music21.key.Key("CM")
        elif idx == len(modes):
            idx = 0

        return modes[idx - 1].key

    def scale(self, factor: float) -> None:
        self.component_manager: HarmonyTLComponentManager
        self.component_manager.scale(factor)

    def crop(self, length: float) -> None:
        self.component_manager: HarmonyTLComponentManager
        self.component_manager.crop(length)

    def deserialize_components(self, components: dict[int, dict[str]]):
        super().deserialize_components(components)
        post(Post.HARMONY_TIMELINE_COMPONENTS_DESERIALIZED, self.id)


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
            components_at_same_time = self.timeline.get_components_by_attr("time", time)
            for component in components_at_same_time:
                if type(component) is self._get_component_class_by_kind(kind):
                    kind_name = "harmony" if kind == ComponentKind.HARMONY else "key"
                    return (
                        False,
                        f"Can't create {kind_name}.\nThere is already a {kind_name} at time='{time}'.",
                    )

        return True, ""

    def scale(self, factor: float) -> None:
        for component in self:
            component.set_data("time", component.get_data("time") * factor)

    def crop(self, length: float) -> None:
        for component in list(self).copy():
            if component.get_data("time") > length:
                self.delete_component(component)
