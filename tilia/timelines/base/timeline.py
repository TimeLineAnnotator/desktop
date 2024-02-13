from __future__ import annotations

import functools
import logging
from abc import ABC
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
    validate_timeline_ordinal,
    validate_boolean,
)
from ...requests import get, Get, post, Post, stop_listening_to_all

if TYPE_CHECKING:
    from tilia.timelines.timeline_kinds import TimelineKind

    # noinspection PyUnresolvedReferences
    from .component import TimelineComponent

logger = logging.getLogger(__name__)

TC = TypeVar("TC", bound="TimelineComponent")
T = TypeVar("T", bound="Timeline")


class Timeline(ABC, Generic[TC]):
    SERIALIZABLE_BY_VALUE = ["name", "height", "is_visible", "ordinal"]
    DEFAULT_HEIGHT = 1
    KIND: TimelineKind | None = None

    validators = {
        "name": validate_string,
        "id": validate_read_only,
        "height": functools.partial(validate_bounded_integer, lower=10),
        "ordinal": validate_timeline_ordinal,
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
        self.height = height or self.DEFAULT_HEIGHT

        self.ordinal = ordinal or get(Get.TIMELINE_ORDINAL_FOR_NEW)

        self.component_manager = component_manager

    def __iter__(self):
        return iter(self.components)

    def __getitem__(self, item):
        return sorted(self.components)[item]

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

    @property
    def is_empty(self):
        return len(self) == 0

    @property
    def components(self):
        return self.component_manager.get_components()

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

    def create_timeline_component(
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

    def deserialize_components(self, components: dict[int, dict[str]]):
        return self.component_manager.deserialize_components(components)

    def get_state(self) -> dict:
        """Creates a dict with timeline components and attributes."""
        logger.debug(f"Serializing {self}...")
        state = {}
        for attr in self.SERIALIZABLE_BY_VALUE:
            if isinstance(value := getattr(self, attr), list):
                value = value.copy()
            state[attr] = value

        state["components"] = self.component_manager.serialize_components()
        state["kind"] = self.KIND.name

        return state

    def restore_state(self, state: dict):
        self.clear()
        self.component_manager.deserialize_components(state["components"])
        self.set_data("height", state["height"])
        self.set_data("name", state["name"])


class TimelineComponentManager(Generic[T, TC]):
    def __init__(
        self,
        component_kinds: list[ComponentKind],
    ):
        self._components: Set[TC] = set()
        self.component_kinds = component_kinds
        self.id_to_component: dict[int, TC] = {}

        self.timeline: T | None = None

    def __iter__(self):
        return iter(self._components)

    @property
    def component_count(self):
        return len(self._components)

    def associate_to_timeline(self, timeline: Timeline):
        logger.debug(f"Setting {self}.timeline to {timeline}")
        self.timeline = timeline

    def _validate_component_creation(self, *args, **kwargs):
        return True, ""

    def create_component(
        self, kind: ComponentKind, timeline, id, *args, **kwargs
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

    def get_existing_values_for_attr(self, attr_name: str, kind: ComponentKind) -> set:
        cmp_set = self._get_component_set_by_kind(kind)
        return set([getattr(cmp, attr_name) for cmp in cmp_set])

    def _get_component_set_by_kind(self, kind: ComponentKind) -> set:
        if kind == "all":
            return self._components
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
        self._components.add(component)
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

    def deserialize_components(self, serialized_components: dict[int, dict[str, Any]]):
        serialize.deserialize_components(self.timeline, serialized_components)

    def post_component_event(self, event: Post, component_id: int, *args, **kwargs):
        post(event, self.timeline.KIND, self.timeline.id, component_id, *args, **kwargs)
