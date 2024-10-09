from __future__ import annotations

import functools
import bisect
from abc import ABC
from enum import StrEnum, auto
from typing import Any, Callable, TYPE_CHECKING, TypeVar, Generic, Set

from tilia.timelines import serialize
from tilia.timelines.component_kinds import ComponentKind, get_component_class_by_kind
from tilia.exceptions import (
    InvalidComponentKindError,
    SetTimelineDataError,
    GetTimelineDataError,
)
from .validators import (
    validate_string,
    validate_read_only,
    validate_bounded_integer,
    validate_boolean,
    validate_positive_integer,
)
from ...requests import get, Get, post, Post, stop_listening_to_all

if TYPE_CHECKING:
    from tilia.timelines.timeline_kinds import TimelineKind

    # noinspection PyUnresolvedReferences
    from .component import TimelineComponent


TC = TypeVar("TC", bound="TimelineComponent")
T = TypeVar("T", bound="Timeline")


class Timeline(ABC, Generic[TC]):
    SERIALIZABLE_BY_VALUE = ["name", "height", "is_visible", "ordinal"]
    KIND: TimelineKind | None = None
    FLAGS = []

    validators = {
        "name": validate_string,
        "id": validate_read_only,
        "height": functools.partial(validate_bounded_integer, lower=10),
        "ordinal": validate_positive_integer,
        "is_visible": validate_boolean,
    }

    def __init__(
        self,
        component_manager: TimelineComponentManager | None = None,
        name: str = "",
        height: int = 0,
        is_visible: bool = True,
        ordinal: int = None,
    ):
        self.id = get(Get.ID)

        self.name = name
        self.is_visible = is_visible
        self.height = height or self.default_height or 1

        self.ordinal = ordinal or get(Get.TIMELINE_ORDINAL_FOR_NEW)

        self.component_manager = component_manager

    def __iter__(self):
        return iter(self.components)

    def __getitem__(self, item):
        return self.components[item]

    def __len__(self):
        return self.component_manager.component_count

    def __bool__(self):
        """Prevents False form being returned when timeline is empty."""
        return True

    def __str__(self):
        return self.__class__.__name__ + f"({id(self)})"

    def __repr__(self):
        return f"{type(self).__name__}(id={self.id}, ordinal={self.ordinal}, name={self.name}))"

    def __lt__(self, other):
        return self.ordinal < other.ordinal

    def __eq__(self, other):
        if self.KIND != other.KIND:
            return False
        for attr in self.SERIALIZABLE_BY_VALUE:
            if self.get_data(attr) != other.get_data(attr):
                return False
        return True

    @property
    def is_empty(self):
        return len(self) == 0

    @property
    def components(self):
        return self.component_manager.get_components()

    @property
    def default_height(self):
        return None

    def validate_set_data(self, attr, value):
        if not hasattr(self, attr):
            raise SetTimelineDataError(
                f"Timeline '{self}' has no attribute named '{attr}'. Can't set to '{value}'."
            )
        try:
            return self.validators[attr](value)
        except KeyError:
            raise KeyError(
                f"{self} has no validator for attribute {attr}. Can't set to '{value}'."
            )

    def set_data(self, attr: str, value: Any):
        if not self.validate_set_data(attr, value):
            return None, False
        setattr(self, attr, value)
        return value, True

    def validate_get_data(self, attr):
        if not hasattr(self, attr):
            raise GetTimelineDataError(
                f"Timeline '{self}' has no attribute named '{attr}'"
            )
        return True

    def get_data(self, attr: str):
        if self.validate_get_data(attr):
            return getattr(self, attr)

    def create_component(
        self, kind: ComponentKind, *args, **kwargs
    ) -> tuple[TC | None, str | None]:
        component_id = get(Get.ID)
        success, component, reason = self.component_manager.create_component(
            kind, self, component_id, *args, **kwargs
        )

        if success:
            post(
                Post.TIMELINE_COMPONENT_CREATED, self.KIND, self.id, kind, component.id
            )
            return component, None
        else:
            return None, reason

    def get_component(self, id: int) -> TC:
        return self.component_manager.get_component(id)

    def get_component_by_attr(self, attr: str, value: Any) -> TC:
        return next((c for c in self if c.get_data(attr) == value), None)

    def get_components_by_attr(self, attr: str, value: Any) -> list[TC]:
        return [c for c in self if c.get_data(attr) == value]

    def get_next_component(self, component: TC) -> TC | None:
        return self.component_manager.get_next_component(component)

    def get_previous_component(self, component: TC) -> TC | None:
        return self.component_manager.get_previous_component(component)

    def get_next_component_by_time(self, time: float) -> TC | None:
        return self.component_manager.get_next_component_by_time(time)

    def get_previous_component_by_time(self, time: float) -> TC | None:
        return self.component_manager.get_previous_component_by_time(time)

    def set_component_data(self, id: int, attr: str, value: Any):
        return self.component_manager.set_component_data(id, attr, value)

    def get_component_data(self, id: int, attr: str):
        return self.component_manager.get_component_data(id, attr)

    def delete_components(self, components: list[TC]) -> None:
        self._validate_delete_components(components)

        for component in components:
            self.component_manager.delete_component(component)

    def _validate_delete_components(self, components: list[TC]) -> None:
        pass

    def clear(self):
        self.component_manager.clear()

    def delete(self):
        self.component_manager.clear()

    def scale(self, factor: float, offset_old: float, offset_new: float) -> None:
        self.component_manager.scale(factor, offset_old, offset_new)

    def crop(self, start: float, end: float) -> None:
        self.component_manager.crop(start, end)

    def deserialize_components(self, components: dict[int, dict[str]]):
        return self.component_manager.deserialize_components(components)

    def get_state(self) -> dict:
        """Creates a dict with timeline components and attributes."""
        state = {}
        for attr in self.SERIALIZABLE_BY_VALUE:
            if isinstance(value := getattr(self, attr), list):
                value = value.copy()
            state[attr] = value

        state["components"] = self.component_manager.serialize_components()
        state["kind"] = self.KIND.name

        return state

    def update_component_order(self, component: TC):
        self.component_manager.update_component_order(component)


class TimelineComponentManager(Generic[T, TC]):
    def __init__(
        self,
        component_kinds: list[ComponentKind],
    ):
        self._components: list[TC] = []
        self.component_kinds = component_kinds
        self.id_to_component: dict[int, TC] = {}

        self.timeline: T | None = None

    def __iter__(self):
        return iter(self._components)

    @property
    def component_count(self):
        return len(self._components)

    def associate_to_timeline(self, timeline: Timeline):
        self.timeline = timeline

    def _validate_component_creation(self, *args, **kwargs):
        return True, ""

    def create_component(
        self, kind: ComponentKind | None, timeline, id, *args, **kwargs
    ) -> tuple[bool, TC | None, str]:
        self._validate_component_kind(kind)
        valid, reason = self._validate_component_creation(kind, *args, **kwargs)
        if not valid:
            return False, None, reason

        component_class = self._get_component_class_by_kind(kind)
        component = component_class(timeline, id, *args, **kwargs)

        self._add_to_components(component)

        return True, component, ""

    def set_component_data(self, id: int, attr: str, value: Any):
        value, success = self.get_component(id).set_data(attr, value)
        if success:
            post(
                Post.TIMELINE_COMPONENT_SET_DATA_DONE, self.timeline.id, id, attr, value
            )
        if not success:
            post(
                Post.TIMELINE_COMPONENT_SET_DATA_FAILED,
                self.timeline.id,
                id,
                attr,
                value,
            )

    def get_component_data(self, id: int, attr: str):
        return self.get_component(id).get_data(attr)

    def get_component_by_attribute(
        self, attr_name: str, value: Any, kind: ComponentKind
    ):
        cmp_set = self._get_component_set_by_kind(kind)
        return self._get_component_from_set_by_attribute(cmp_set, attr_name, value)

    def get_components_by_attribute(
        self, attr_name: str, value: Any, kind: ComponentKind
    ) -> list:
        cmp_set = self._get_component_set_by_kind(kind)
        return self._get_components_from_set_by_attribute(cmp_set, attr_name, value)

    def get_components_by_condition(
        self, condition: Callable[[TC], bool], kind: ComponentKind
    ) -> list:
        cmp_set = self._get_component_set_by_kind(kind)
        return [c for c in cmp_set if condition(c)]

    def get_components(self) -> list[TC]:
        return list(self._components)

    def get_component(self, id: int) -> TC:
        return self.id_to_component[id]

    def get_next_component(self, id: int) -> TC | None:
        component_idx = self._components.index(self.get_component(id))
        if component_idx == len(self._components) - 1:
            return None
        else:
            return self._components[component_idx + 1]

    def get_previous_component(self, id: int) -> TC | None:
        component_idx = self._components.index(self.get_component(id))
        if component_idx == 0:
            return None
        else:
            return self._components[component_idx - 1]

    def get_previous_component_by_time(self, time: float) -> TC | None:
        times = [cmp.get_data("time") for cmp in self]
        component_idx = bisect.bisect_right(times, time)
        if component_idx == 0:
            return None
        else:
            return self._components[component_idx - 1]

    def get_next_component_by_time(self, time: float) -> TC | None:
        times = [cmp.get_data("time") for cmp in self]
        component_idx = bisect.bisect_right(times, time)
        if component_idx == len(self._components):
            return None
        else:
            return self._components[component_idx]

    def get_existing_values_for_attr(self, attr_name: str, kind: ComponentKind) -> set:
        cmp_set = self._get_component_set_by_kind(kind)
        return set([getattr(cmp, attr_name) for cmp in cmp_set])

    def _get_component_set_by_kind(self, kind: ComponentKind) -> Set[TC]:
        if kind == "all":
            return set(self._components)
        cmp_class = self._get_component_class_by_kind(kind)

        return {cmp for cmp in self._components if isinstance(cmp, cmp_class)}

    def _get_component_class_by_kind(
        self, kind: ComponentKind
    ) -> type[TimelineComponent]:
        self._validate_component_kind(kind)
        return get_component_class_by_kind(kind)

    def _validate_component_kind(self, kind: ComponentKind):
        if kind not in self.component_kinds:
            raise InvalidComponentKindError(f"Got invalid component kind {kind}")

    @staticmethod
    def _get_component_from_set_by_attribute(
        cmp_list: set, attr_name: str, value: Any
    ) -> Any | None:
        return next((c for c in cmp_list if getattr(c, attr_name) == value), None)

    @staticmethod
    def _get_components_from_set_by_attribute(
        cmp_list: set, attr_name: str, value: Any
    ) -> list:
        return [c for c in cmp_list if getattr(c, attr_name) == value]

    def _add_to_components(self, component: TC) -> None:
        bisect.insort_left(self._components, component)
        self.id_to_component[component.id] = component

    def _remove_from_components_set(self, component: TC) -> None:
        try:
            self._components.remove(component)
            self.id_to_component.pop(component.id)
        except KeyError:
            raise KeyError(
                f"Can't remove component '{component}' from {self}: not in"
                " self.components."
            )

    def update_component_order(self, component: TC):
        self._components.remove(component)
        bisect.insort_left(self._components, component)

    def delete_component(self, component: TC) -> None:
        stop_listening_to_all(component)
        self._remove_from_components_set(component)
        post(
            Post.TIMELINE_COMPONENT_DELETED,
            self.timeline.KIND,
            self.timeline.id,
            component.id,
        )

    def clear(self):
        for component in self._components.copy():
            self.delete_component(component)

    def serialize_components(self):
        return serialize.serialize_components(self._components)

    def deserialize_components(
        self, serialized_components: dict[int | str, dict[str, Any]]
    ):
        serialize.deserialize_components(self.timeline, serialized_components)

    def post_component_event(self, event: Post, component_id: int, *args, **kwargs):
        post(event, self.timeline.KIND, self.timeline.id, component_id, *args, **kwargs)

    def crop(self, start: float, end: float) -> None:
        raise NotImplementedError

    def scale(self, factor: float, offset_old: float, offset_new: float) -> None:
        raise NotImplementedError


class TimelineFlag(StrEnum):
    NOT_CLEARABLE = auto()
    NOT_DELETABLE = auto()
