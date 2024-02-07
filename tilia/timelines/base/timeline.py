from __future__ import annotations
import logging
from abc import ABC
from typing import Optional, Any, Callable, TYPE_CHECKING

from tilia.timelines import serialize
from tilia.timelines.component_kinds import ComponentKind, get_component_class_by_kind
from tilia.exceptions import InvalidComponentKindError
from ...requests import get, Get, post, Post, stop_listening_to_all

if TYPE_CHECKING:
    from .component import TimelineComponent

logger = logging.getLogger(__name__)


class Timeline(ABC):
    SERIALIZABLE_BY_VALUE = ["name", "height", "is_visible", "ordinal"]
    DEFAULT_HEIGHT = 1
    KIND = None

    def __init__(
        self,
        component_manager: Optional[TimelineComponentManager] = None,
        name: str = "",
        height: int = 0,
        is_visible: bool = True,
        ordinal: int = None,
        display_position: int = None,  # here for backwards compatibility
    ):
        self.id = get(Get.ID)

        self._name = name
        self.is_visible = is_visible
        self._height = height or self.DEFAULT_HEIGHT

        if display_position:
            self.ordinal = int(display_position) + 1
        else:
            self.ordinal = ordinal or get(Get.ORDINAL_FOR_NEW_TIMELINE)

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

    def __lt__(self, other):
        return self.ordinal < other.ordinal

    @property
    def components(self):
        return self.component_manager.get_components()

    @property
    def height(self):
        return self._height

    @height.setter
    def height(self, value):
        self._height = value
        post(Post.TIMELINE_HEIGHT_CHANGED, self.id)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        post(Post.TIMELINE_NAME_CHANGED, self.id)

    def create_timeline_component(
        self, kind: ComponentKind, *args, **kwargs
    ) -> TimelineComponent:
        """Creates a TimelineComponent of the given kind.
        Get timeline ui to create a ui for the component."""
        component = self.component_manager.create_component(kind, self, *args, **kwargs)

        post(Post.TIMELINE_COMPONENT_CREATED, self.KIND, self.id, component.id)

        return component

    def get_component(self, id: int) -> TimelineComponent:
        return self.component_manager.get_component(id)

    def on_request_to_delete_components(
        self, components: list[TimelineComponent]
    ) -> None:
        self._validate_delete_components(components)

        for component in components:
            self.component_manager.delete_component(component)

    def _validate_delete_components(self, components: list[TimelineComponent]) -> None:
        pass

    def clear(self, record=True):
        logger.debug(f"Clearing timeline '{self}'")

        self.component_manager.clear()

    def delete(self):
        logger.debug(f"Deleting timeline '{self}'")
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
        self.clear(record=False)
        self.component_manager.deserialize_components(state["components"])
        self.height = state["height"]
        self.name = state["name"]


class TimelineComponentManager:
    def __init__(
        self,
        component_kinds: list[ComponentKind],
    ):
        self._components = set()
        self.component_kinds = component_kinds
        self.id_to_component = {}

        self.timeline: Optional[Timeline] = None

    @property
    def component_count(self):
        return len(self._components)

    def associate_to_timeline(self, timeline: Timeline):
        logger.debug(f"Seting {self}.timeline to {timeline}")
        self.timeline = timeline

    def _validate_component_creation(self, *args, **kwargs):
        pass

    def create_component(self, kind: ComponentKind, *args, **kwargs):
        self._validate_component_kind(kind)
        self._validate_component_creation(*args, **kwargs)
        component_class = self._get_component_class_by_kind(kind)
        component = component_class.create(*args, **kwargs)

        self._add_to_components(component)

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

    def get_component(self, id: int) -> TimelineComponent:
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

    def _add_to_components(self, component: TimelineComponent) -> None:
        logger.debug(f"Adding component '{component}' to {self}.")
        self._components.add(component)
        self.id_to_component[component.id] = component

    def _remove_from_components_set(self, component: TimelineComponent) -> None:
        logger.debug(f"Removing component '{component}' from {self}.")
        try:
            self._components.remove(component)
            self.id_to_component.pop(component.id)
        except KeyError:
            raise KeyError(
                f"Can't remove component '{component}' from {self}: not in"
                " self.components."
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
        stop_listening_to_all(component)
        self._remove_from_components_set(component)
        post(
            Post.TIMELINE_COMPONENT_DELETED,
            self.timeline.KIND,
            self.timeline.id,
            component.id,
        )

    def clear(self):
        logger.debug(f"Clearing component manager '{self}'...")
        for component in self._components.copy():
            self.delete_component(component)

    def serialize_components(self):
        logger.debug(f"Serializing components on '{self}.'")
        return serialize.serialize_components(self._components)

    def deserialize_components(self, serialized_components: dict[int, dict[str]]):
        serialize.deserialize_components(self.timeline, serialized_components)

    def post_component_event(self, event: Post, component_id: id, *args, **kwargs):
        post(event, self.timeline.KIND, self.timeline.id, component_id, *args, **kwargs)
