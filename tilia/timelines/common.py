"""
Classes and functions common to most timelines.
Contains the following interfaces, that should be implemented by specific timelines:
    - Timeline
    - TimelineComponentManager
    - TimelineComponent
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, Optional

import tilia.repr
import tilia.timelines.serialize
from . import serialize
from tilia.timelines.component_kinds import ComponentKind, get_component_class_by_kind
from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from .collection import TimelineCollection

from typing import Callable, Any
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

from tilia import events


class InvalidComponentKindError(Exception):
    pass


class TimelineComponent(ABC):
    """Interface for objects that compose a timeline. E.g. the Hierarchy class
    in HierarchyTimelines."""

    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        self.id = timeline.get_id_for_component()
        self.ui = None

    @classmethod
    @abstractmethod
    def create(cls, *args, **kwargs):
        """Should call the constructor of the appropriate subclass."""

    @abstractmethod
    def receive_delete_request_from_ui(self) -> None:
        """Calls own delete method and ui's delete method.
        May validate delete request prior to performing
        deletion."""

    def __str__(self):
        return tilia.repr.default_str(self)


class TimelineComponentManager:
    def __init__(
        self,
        component_kinds: list[ComponentKind],
    ):
        """Interface for object that composes timeline and creates, handles queries for and interactions between TimelineComponents.
        E.g. The HierarchyTimelineComponentManager is responsible for calling the create() method on the Hierarchy class and also handles splitting, grouping and merging hierarchies.
        """

        self._components = set()
        self.component_kinds = component_kinds

        self.timeline: Optional[Timeline] = None

    @property
    def component_count(self):
        return len(self._components)

    def associate_to_timeline(self, timeline: Timeline):
        logging.debug(f"Seting {self}.timeline to {timeline}")
        self.timeline = timeline

    def _validate_component_creation(self, *args, **kwargs):
        pass

    def create_component(self, kind: ComponentKind, *args, **kwargs):
        self._validate_component_kind(kind)
        self._validate_component_creation(*args, **kwargs)
        component_class = self._get_component_class_by_kind(kind)
        component = component_class.create(*args, **kwargs)

        self._add_to_components_set(component)

        return component

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
        self, condition: Callable[[TimelineComponent], bool], kind: ComponentKind
    ) -> list:
        cmp_set = self._get_component_set_by_kind(kind)
        return [c for c in cmp_set if condition(c)]

    def get_components(self) -> list[TimelineComponent]:
        return list(self._components)

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

    def _add_to_components_set(self, component: TimelineComponent) -> None:
        logger.debug(f"Adding component '{component}' to {self}.")
        self._components.add(component)

    def _remove_from_components_set(self, component: TimelineComponent) -> None:
        logger.debug(f"Removing component '{component}' from {self}.")
        try:
            self._components.remove(component)
        except KeyError:
            raise KeyError(
                f"Can't remove component '{component}' from {self}: not in self.components."
            )

    def find_previous_by_attr(self, attr: str, value, kind="all", custom_list=None):
        """Find object with greatest attribute value smaller than value"""

        if custom_list:
            object_list = custom_list
        elif kind != "all":
            object_list = self.find_by_kind(kind)
        else:
            object_list = self.objects

        if not object_list:
            return None

        object_list.sort(key=lambda x: getattr(x, attr))
        attr_list = [getattr(obj, attr) for obj in object_list]
        attr_list.append(value)
        attr_list.sort()
        index = attr_list.index(value)
        if index > 0:
            return object_list[index - 1]
        else:
            return None

    def find_next_by_attr(self, attr, value, kind="all", custom_list=None):
        """Find object with largest position smaller than pos"""

        if custom_list:
            object_list = custom_list
        elif kind != "all":
            object_list = self.find_by_kind(kind)
        else:
            object_list = self.objects

        if not object_list:
            return None

        return min(
            [obj for obj in object_list if getattr(obj, attr) > value],
            key=lambda x: getattr(x, attr),
            default=None,
        )

    def find_closest_by_attr(self, attr, value, kind="all"):
        """Find object with largest position smaller than pos"""

        if kind != "all":
            object_list = self.find_by_kind(kind)
        else:
            object_list = self.objects

        if not object_list:
            return None

        return min(
            [obj for obj in object_list],
            key=lambda x: abs(getattr(x, attr) - value),
            default=None,
        )

    def delete_component(self, component: TimelineComponent) -> None:
        logger.debug(f"Deleting component '{component}'")

        self.timeline.request_delete_ui_for_component(component)

        events.unsubscribe_from_all(component)

        self._remove_from_components_set(component)

    def clear(self):
        logging.debug(f"Clearing component manager '{self}'...")
        for component in self._components.copy():
            self.delete_component(component)

    def serialize_components(self):
        logger.debug(f"Serializing components on '{self}.'")
        return serialize.serialize_components(self._components)

    def deserialize_components(self, serialized_components: dict[int, dict[str]]):
        serialize.deserialize_components(self.timeline, serialized_components)


class Timeline(ABC):
    """Interface for timelines.
    Is composed of a ComponentManager, which implements most of the timeline component operations and functions
    to pass global information (e.g. media length) to timeline components. Keeps a reference to its ui, which is a
    TimelineUI object."""

    SERIALIZABLE_BY_VALUE = []
    SERIALIZABLE_BY_UI_VALUE = ["height", "is_visible", "display_position"]

    def __init__(
        self,
        collection: TimelineCollection,
        component_manager: TimelineComponentManager | None,
        kind: TimelineKind,
        **_,
    ):
        self.id = collection.get_id()
        self.collection = collection
        self.kind = kind

        self.component_manager = component_manager

        self.ui = None

    def create_timeline_component(
        self, kind: ComponentKind, *args, **kwargs
    ) -> TimelineComponentManager:
        """Creates a TimelineComponent of the given kind. Request timeline ui to create a ui for the component."""
        component = self.component_manager.create_component(kind, self, *args, **kwargs)
        component_ui = self.ui.get_ui_for_component(kind, component, **kwargs)

        self._make_reference_to_ui_in_component(component, component_ui)

        return component

    @staticmethod
    def _make_reference_to_ui_in_component(
        component: TimelineComponent, component_ui: TimelineComponent
    ):
        logger.debug(f"Setting '{component}' ui as {component_ui}.'")
        component.ui = component_ui

    # noinspection PyMethodMayBeStatic

    def on_request_to_delete_components(
        self, components: list[TimelineComponent], record=True
    ) -> None:
        self._validate_delete_components(components)

        for component in components:
            self.component_manager.delete_component(component)

    def request_delete_ui_for_component(self, component: TimelineComponent) -> None:
        self.ui.delete_element(component.ui)

    def _validate_delete_components(self, components: list[TimelineComponent]) -> None:
        pass

    def clear(self, record=True):
        logger.debug(f"Clearing timeline '{self}'")

        self.component_manager.clear()

    def delete(self):
        logger.debug(f"Deleting timeline '{self}'")
        self.component_manager.clear()

    def get_state(self) -> dict:
        """Creates a dict with timeline components and attributes."""
        logger.debug(f"Serializing {self}...")
        state = {}
        for attr in self.SERIALIZABLE_BY_VALUE:
            if isinstance(value := getattr(self, attr), list):
                value = value.copy()
            state[attr] = value

        for attr in self.SERIALIZABLE_BY_UI_VALUE:
            if isinstance(value := getattr(self.ui, attr), list):
                value = value.copy()
            state[attr] = value

        state["components"] = self.component_manager.serialize_components()
        state["kind"] = self.kind.name

        return state

    def restore_state(self, state: dict):
        self.clear(record=False)
        self.component_manager.deserialize_components(state["components"])
        self.ui.height = state["height"]
        self.ui.name = state["name"]

    def get_id_for_component(self) -> int:
        id_ = self.collection.get_id()
        logger.debug(f"Got id {id_} for timeline component.")
        return id_

    def get_media_length(self):
        return self.collection.get_media_length()

    def get_current_playback_time(self):
        return self.collection.get_current_playback_time()

    def __str__(self):
        if self.ui:
            return str(self.ui)
        else:
            return self.__class__.__name__ + f"({id(self)})"


def log_object_creation(func: Callable) -> Callable:
    """Wraps an object's __init__ method to log a "Starting x creation..."
    message after method call and a "Created x." message after method call.
    Where x is the object's __repr__."""

    def wrapper(self, *args, **kwargs):
        logger.debug(f"Creating {self.__class__.__name__} with {args=}, {kwargs=}...")
        result = func(self, *args, **kwargs)
        logger.debug(f"Created {self.__class__.__name__}.")
        return result

    return wrapper


def log_object_deletion(func: Callable) -> Callable:
    """Wraps an object's delete or destroy method to log a "Starting x deletion..."
    message after method call and a "Deleted x." message after method call.
    Where x is the object's __repr__."""

    def wrapper(self, *args, **kwargs):
        logger.debug(f"Deleting {self.__class__.__name__}...")
        result = func(self, *args, **kwargs)
        logger.debug(f"Deleted {self.__class__.__name__}.")
        return result

    return wrapper
