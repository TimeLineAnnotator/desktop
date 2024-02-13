from __future__ import annotations

import logging
from typing import Any, Callable, TYPE_CHECKING, TypeVar, Generic, Set

from PyQt6.QtWidgets import QGraphicsItem

from tilia.timelines.component_kinds import ComponentKind
from tilia.ui.timelines.element_kinds import get_element_class_by_kind
from tilia.utils import get_tilia_class_string
from tilia.ui.timelines.scene import TimelineScene

from tilia.ui.timelines.base.element import TimelineUIElement

if TYPE_CHECKING:
    from tilia.ui.timelines.base.timeline import TimelineUI

    # noinspection PyUnresolvedReferences

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=TimelineUIElement)


class ElementManager(Generic[T]):
    def __init__(self, element_class: type[T] | list[type[T]]):
        self._elements: Set[T] = set()
        self.id_to_element = {}
        self.element_classes: T | list[T] = (
            element_class if isinstance(element_class, list) else [element_class]
        )

        self._selected_elements = []

    @property
    def is_single_element(self):
        return len(self.element_classes) == 1

    @property
    def has_selected_elements(self):
        return bool(self._selected_elements)

    def belongs_to_selection(self, item: QGraphicsItem):
        return any((item in el.selection_triggers() for el in self._selected_elements))

    def create_element(
        self,
        kind: ComponentKind,
        id: int,
        timeline_ui: TimelineUI,
        scene: TimelineScene,
    ):
        if self.is_single_element:
            element = self.element_classes[0](id, timeline_ui, scene)
        else:
            element = get_element_class_by_kind(kind)(id, timeline_ui, scene)

        self._add_to_elements_set(element)

        return element

    def _add_to_elements_set(self, element: T) -> None:
        self._elements.add(element)
        self.id_to_element[element.id] = element

    def _remove_from_elements_set(self, element: T) -> None:
        try:
            self._elements.remove(element)
            del self.id_to_element[element.id]
        except ValueError:
            raise ValueError(
                f"Can't remove element '{element}' from {self}: not in self._elements."
            )

    def get_element(self, id: int) -> T:
        return self.id_to_element[id]

    def get_element_by_attribute(self, attr_name: str, value: Any) -> T:
        return self._get_element_from_set_by_attribute(self._elements, attr_name, value)

    def get_elements_by_attribute(self, attr_name: str, value: Any) -> list[T]:
        return self._get_elements_from_set_by_attribute(
            self._elements, attr_name, value
        )

    def get_elements_by_condition(self, condition: Callable[[T], bool]) -> list[T]:
        return [e for e in self._elements if condition(e)]

    def get_element_by_condition(self, condition: Callable[[T], bool]) -> T | None:
        return next((e for e in self._elements if condition(e)), None)

    def get_existing_values_for_attribute(self, attr_name: str) -> set:
        return set([getattr(cmp, attr_name) for cmp in self._elements])

    @staticmethod
    def _get_element_from_set_by_attribute(
        cmp_list: set, attr_name: str, value: Any
    ) -> T | None:
        return next((e for e in cmp_list if getattr(e, attr_name) == value), None)

    @staticmethod
    def _get_elements_from_set_by_attribute(
        cmp_list: set, attr_name: str, value: Any
    ) -> list[T]:
        return [e for e in cmp_list if getattr(e, attr_name) == value]

    def select_element(self, element: T) -> None:
        if element not in self._selected_elements:
            self._add_to_selected_elements_set(element)
            element.on_select()

    def deselect_element(self, element: T) -> None:
        if element in self._selected_elements:
            self._remove_from_selected_elements_set(element)
            element.on_deselect()

    def _deselect_if_selected(self, element: T):
        if element in self._selected_elements:
            self.deselect_element(element)

    def deselect_all_elements(self):
        for element in self._selected_elements.copy():
            self.deselect_element(element)

    def _add_to_selected_elements_set(self, element: T) -> None:
        self._selected_elements.append(element)

    def _remove_from_selected_elements_set(self, element: T) -> None:
        try:
            self._selected_elements.remove(element)
        except ValueError:
            raise ValueError(
                f"Can't remove element '{element}' from selected objects of {self}: not"
                " in self._selected_elements."
            )

    def get_selected_elements(self) -> list[T]:
        return self._selected_elements

    def delete_element(self, element: T):
        element.delete()
        self._remove_from_elements_set(element)

    @staticmethod
    def get_child_items_from_elements(
        elements: list[T],
    ) -> list[int]:
        drawings_ids = []
        for element in elements:
            for id_ in element.child_items():
                drawings_ids.append(id_)

        return drawings_ids

    def __repr__(self) -> str:
        return get_tilia_class_string(self)

    def get_all_elements(self) -> set:
        return self._elements

    def update_time_on_elements(self) -> None:
        for element in self._elements:
            element.update_position()
