from __future__ import annotations

import bisect
import copy
import functools
import importlib
from abc import ABC
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Generic, Set, TypeVar

from tilia.exceptions import (
    GetTimelineDataError,
    InvalidComponentKindError,
    SetTimelineDataError,
)
from tilia.timelines import serialize
from tilia.timelines.component_kinds import ComponentKind, get_component_class_by_kind
from tilia.utils import get_sibling_packages

from ...requests import Get, Post, get, post, stop_listening_to_all
from ..hash_timelines import hash_function
from .validators import (
    validate_boolean,
    validate_bounded_integer,
    validate_positive_integer,
    validate_pre_validated,
    validate_read_only,
    validate_string,
)

if TYPE_CHECKING:

    # noinspection PyUnresolvedReferences
    from .component import TimelineComponent

TC = TypeVar("TC", bound="TimelineComponent")
T = TypeVar("T", bound="Timeline")


class TimelineFlag(Enum):
    COMPONENTS_COLORED = auto()
    COMPONENTS_IMPORTABLE = auto()
    COMPONENTS_COPYABLE = auto()
    COMPONENTS_NOT_DELETABLE = auto()
    COMPONENTS_NOT_EDITABLE = auto()
    NOT_CLEARABLE = auto()
    NOT_DELETABLE = auto()
    NOT_DUPLICATABLE = auto()
    NOT_EXPORTABLE = auto()


class Timeline(ABC, Generic[TC]):
    # `measure_table`, the id of the beat timeline whose measures this timeline was
    # placed with, and `fields`, its metadata, are kept as the file has them.
    SERIALIZABLE = [
        "name",
        "height",
        "is_visible",
        "ordinal",
        "measure_table",
        "fields",
    ]
    NOT_EXPORTABLE_ATTRS = []
    FLAGS = []
    COMPONENT_MANAGER_CLASS = None

    validators = {
        "name": validate_string,
        "id": validate_read_only,
        "height": functools.partial(validate_bounded_integer, lower=10),
        "ordinal": validate_positive_integer,
        "is_visible": validate_boolean,
        "measure_table": validate_pre_validated,
        "fields": validate_pre_validated,
    }

    def __init__(
        self,
        name: str = "",
        height: int = 0,
        is_visible: bool = True,
        ordinal: int | None = None,
        id: str | None = None,
        measure_table: str | None = None,
        fields: dict[str, Any] | None = None,
        **kwargs,  # ignores components_hash
    ):
        self.id = get(Get.ID, id)

        self.name = name
        self.is_visible = is_visible
        self.height = height or self.default_height or 1
        self.measure_table = measure_table
        self.fields = copy.deepcopy(fields) if fields is not None else {}

        self.ordinal = ordinal or get(Get.TIMELINE_ORDINAL_FOR_NEW)
        if self.COMPONENT_MANAGER_CLASS:
            self.component_manager = self.COMPONENT_MANAGER_CLASS(self)
        else:
            self.component_manager = None

        self.ensure_subclasses_are_available()

    def __iter__(self):
        return iter(self.components)

    def __getitem__(self, item):
        return self.components[item]

    def __len__(self):
        # SliderTimeline has no COMPONENT_MANAGER_CLASS, so component_manager
        # is None there and len(slider_tl) would otherwise crash.
        if self.component_manager:
            return self.component_manager.component_count
        else:
            return 0

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
        if type(self) is not type(other):
            return False
        for attr in self.SERIALIZABLE:
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

    SUBCLASSES_ARE_LOADED = False

    @classmethod
    def subclasses(cls):
        if not cls.SUBCLASSES_ARE_LOADED:
            cls.ensure_subclasses_are_available()
        return cls.__subclasses__()

    @classmethod
    def ensure_subclasses_are_available(cls):
        packages = get_sibling_packages(__name__, __file__)
        for pkg in packages:
            try:
                importlib.import_module(pkg + ".timeline")
            except ModuleNotFoundError:
                print(f"Could not find timeline class in {pkg}.")

        cls.SUBCLASSES_ARE_LOADED = True

    @classmethod
    def get_kinds_by_flag(cls, flag: TimelineFlag | list[TimelineFlag]):
        if isinstance(flag, TimelineFlag):
            flag = [flag]
        return [c for c in cls.__subclasses__() if any(f in c.FLAGS for f in flag)]

    @classmethod
    def type_name(cls):
        """
        Returns the name of the Timeline subclass without the 'Timeline' suffix.
        Example: MarkerTimeline -> Marker
        """
        return cls.__name__.replace("Timeline", "")

    @classmethod
    def get_class_by_name(cls, name: str) -> type[Timeline]:
        for c in cls.subclasses():
            if c.type_name().lower() == name.lower():
                return c
        else:
            raise ValueError(f"No timeline class with name {name}")

    def validate_set_data(self, attr, value):
        if not hasattr(self, attr):
            raise SetTimelineDataError(
                f"Timeline '{self}' has no attribute named '{attr}'. Can't set to '{value}'."
            )
        try:
            return self.validators[attr](value)
        except KeyError as e:
            raise KeyError(
                f"{self} has no validator for attribute {attr}. Can't set to '{value}'."
            ) from e

    def set_data(self, attr: str, value: Any):
        if not self.validate_set_data(attr, value):
            return None, False
        setattr(self, attr, value)
        return getattr(self, attr), True

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
        self, kind: ComponentKind, *args, id=None, checked: bool = True, **kwargs
    ) -> tuple[TC | None, str | None]:
        """Creates a component, unless creation's checks refuse it. With
        `checked=False`, it is created as it is: a component that exists already,
        as a file holds it or an undo gives it back."""
        component_id = get(Get.ID, id)
        success, component, reason = self.component_manager.create_component(
            kind, self, component_id, *args, checked=checked, **kwargs
        )

        if success:
            post(
                Post.TIMELINE_COMPONENT_CREATED,
                type(self),
                self.id,
                kind,
                component.id,
                component.get_data,
                functools.partial(self.set_component_data, component.id),
            )
            return component, None
        else:
            return None, reason

    def get_component(self, id: str) -> TC:
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

    def set_component_data(self, id: str, attr: str, value: Any):
        return self.component_manager.set_component_data(id, attr, value)

    def get_component_data(self, id: str, attr: str):
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

    def scale(self, factor: float) -> None:
        self.component_manager.scale(factor)

    def crop(self, length: float) -> None:
        self.component_manager.crop(length)

    def deserialize_components(self, components: dict[str, dict[str]]):
        return self.component_manager.deserialize_components(components)

    @staticmethod
    def update_component_references(
        components: dict[str, dict[str, Any]],
        new_ids: dict[str, str],
    ) -> None:
        """
        Points serialized components that refer to other components by id
        to the ids those components get in `new_ids`, for a copy of the
        timeline whose components get fresh ids.
        """

    def _get_base_state(self) -> dict:
        """Returns a dict with serializable timeline attributes, excluding components."""
        state = {"kind": self.type_name()}

        string_to_hash = self.type_name() + "|"

        for attr in self.SERIALIZABLE:
            if isinstance(value := getattr(self, attr), list):
                value = value.copy()
            elif isinstance(value, dict):
                # Its own, such as the fields: not shared with the timeline, nor
                # with the states undo keeps.
                value = copy.deepcopy(value)
            state[attr] = value
            string_to_hash += str(value) + "|"

            string_to_hash += str(value) + "|"
        state["hash"] = hash_function(f"{state['kind']}|{string_to_hash}")

        return state

    def get_state(self) -> dict:
        """Creates a dict with timeline components and attributes."""
        state = self._get_base_state()
        state["components"] = self.component_manager.serialize_components()
        state["components_hash"] = self.component_manager.hash_components()

        return state

    def get_export_data(self) -> dict[str, Any]:
        result = self._get_base_state()
        result.pop("hash")
        for attr in self.NOT_EXPORTABLE_ATTRS:
            result.pop(attr)

        result["components"] = []
        for component in self.component_manager:
            data = {
                attr: getattr(component, attr)
                for attr in component.get_export_attributes()
            }
            data["kind"] = component.KIND.name
            result["components"].append(data)

        return result

    def update_component_order(self, component: TC):
        self.component_manager.update_component_order(component)


class TimelineComponentManager(Generic[T, TC]):
    def __init__(
        self,
        timeline: T,
        component_kinds: list[ComponentKind],
    ):
        self.timeline = timeline
        self.component_kinds = component_kinds

        self._components: list[TC] = []
        self.id_to_component: dict[str, TC] = {}
        # True while making components from values that are already final, as when
        # restoring a state: creating or deleting one must not update the others
        # then (a mode changes the applied_to of the harmonies after it).
        self.is_deserializing = False

    def __iter__(self):
        return iter(self._components)

    @property
    def component_count(self):
        return len(self._components)

    def associate_to_timeline(self, timeline: Timeline):
        self.timeline = timeline

    @staticmethod
    def _compose_validators(
        validators: list[Callable[[], tuple[bool, str]]],
    ) -> tuple[bool, str]:
        """Calls validators in order and returns (False, reason) if any fails."""
        for validator in validators:
            success, reason = validator()
            if not success:
                return False, reason
        return True, ""

    def _validate_component_creation(self, *args, **kwargs):
        return True, ""

    def create_component(
        self, kind: ComponentKind, timeline, id, *args, checked: bool = True, **kwargs
    ) -> tuple[bool, TC | None, str]:
        self._validate_component_kind(kind)
        if checked:
            valid, reason = self._validate_component_creation(kind, *args, **kwargs)
            if not valid:
                return False, None, reason

        component_class = self._get_component_class_by_kind(kind)
        component = component_class(timeline, id, *args, **kwargs)

        self._add_to_components(component)

        return True, component, ""

    def set_component_data(self, id: str, attr: str, value: Any):
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
        return value, success

    def get_component_data(self, id: str, attr: str):
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

    def get_component(self, id: str) -> TC:
        return self.id_to_component[id]

    def get_next_component(self, id: str) -> TC | None:
        component_idx = self._components.index(self.get_component(id))
        if component_idx == len(self._components) - 1:
            return None
        else:
            return self._components[component_idx + 1]

    def get_previous_component(self, id: str) -> TC | None:
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
        except KeyError as e:
            raise KeyError(
                f"Can't remove component '{component}' from {self}: not in"
                " self.components."
            ) from e

    def update_component_order(self, component: TC):
        self._components.remove(component)
        bisect.insort_left(self._components, component)

    def delete_component(self, component: TC) -> None:
        stop_listening_to_all(component)
        self._remove_from_components_set(component)
        post(
            Post.TIMELINE_COMPONENT_DELETED,
            type(self.timeline),
            self.timeline.id,
            component.id,
        )

    def clear(self):
        for component in self._components.copy():
            self.delete_component(component)

    def hash_components(self):
        # Sorted, as the list can hold the same components in another order after
        # a restore: those that tie, such as score annotations, are in the order
        # they were inserted. That isn't a change.
        str_to_hash = ""
        for hash in sorted(component.hash for component in self._components):
            str_to_hash += hash + "|"

        return hash_function(str_to_hash)

    def serialize_components(self):
        return serialize.serialize_components(self._components)

    def deserialize_components(self, serialized_components: dict[str, dict[str, Any]]):
        # Their values are final, as when restoring a state.
        self.is_deserializing = True
        try:
            serialize.deserialize_components(self.timeline, serialized_components)
        finally:
            self.is_deserializing = False

    def matches_state(self, state: dict[str, dict[str, Any]]) -> bool:
        """Whether the components are those of `state`: the same ids, each with
        the same values. `components_hash` can't tell, as it doesn't know whose
        values they are.
        """
        return {c.id: c.hash for c in self._components} == {
            id: data["hash"] for id, data in state.items()
        }

    def restore_state(self, prev_state: dict[str, dict[str, Any]]) -> None:
        """Makes the components those of `prev_state`, matching them by id, so
        that a restored component keeps its id and components with the same
        values stay apart.

        Ids go in order, so that restoring doesn't depend on the iteration order
        of a set, which depends on PYTHONHASHSEED, and so that a component is
        created after those it needs (e.g. a staff before its notes).
        """
        current = self.id_to_component
        changed = {
            id
            for id in current.keys() & prev_state.keys()
            if current[id].hash != prev_state[id]["hash"]
        }
        ids_to_delete = (current.keys() - prev_state.keys()) | changed
        ids_to_create = (prev_state.keys() - current.keys()) | changed

        self.is_deserializing = True
        try:
            self.timeline.delete_components(
                [current[id] for id in sorted(ids_to_delete, key=serialize.id_order)]
            )

            for id in sorted(ids_to_create, key=serialize.id_order):
                component_data = prev_state[id].copy()
                kind = ComponentKind[component_data.pop("kind")]

                # As it was, even if creation would refuse it now.
                self.timeline.create_component(
                    kind, id=id, checked=False, **component_data
                )
        finally:
            self.is_deserializing = False

    def post_component_event(self, event: Post, component_id: str, *args, **kwargs):
        post(
            event, type(self.timeline), self.timeline.id, component_id, *args, **kwargs
        )

    def crop(self, length: float) -> None:
        raise NotImplementedError

    def scale(self, length: float) -> None:
        raise NotImplementedError
