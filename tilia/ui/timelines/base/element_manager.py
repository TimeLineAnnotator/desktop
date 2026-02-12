from __future__ import annotations

import bisect
from typing import Any, Callable, TYPE_CHECKING, TypeVar, Generic, Iterable

from PySide6.QtWidgets import QGraphicsItem

from tilia.timelines.component_kinds import ComponentKind
from tilia.ui.timelines.element_kinds import get_element_class_by_kind
from tilia.utils import get_tilia_class_string
from tilia.ui.timelines.scene import TimelineScene

from tilia.ui.timelines.base.element import TimelineUIElement

if TYPE_CHECKING:
    from tilia.ui.timelines.base.timeline import TimelineUI


TE = TypeVar("TE", bound=TimelineUIElement)


class ElementManager(Generic[TE]):
    def __init__(self, element_class: type[TE] | list[type[TE]]):
        self._elements: list[TE] = []
        self.id_to_element = {}
        self.element_classes: TE | list[TE] = (
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
        get_data: Callable[[str], Any],
        set_data: Callable[[str, Any], None],
    ):
        if self.is_single_element:
            element = self.element_classes[0](
                id, timeline_ui, scene, get_data, set_data
            )
        else:
            element = get_element_class_by_kind(kind)(
                id, timeline_ui, scene, get_data, set_data
            )

        self._add_to_elements_set(element)

        return element

    def _add_to_elements_set(self, element: TE) -> None:
        bisect.insort_left(self._elements, element)
        self.id_to_element[element.id] = element

    def _remove_from_elements_set(self, element: TE) -> None:
        try:
            self._elements.remove(element)
            del self.id_to_element[element.id]
        except ValueError as e:
            raise ValueError(
                f"Can't remove element '{element}' from {self}: not in self._elements."
            ) from e

    def get_element(self, id: int) -> TE:
        return self.id_to_element[id]

    def get_element_by_attribute(self, attr_name: str, value: Any) -> TE:
        return self._get_element_from_set_by_attribute(self._elements, attr_name, value)

    def get_elements_by_attribute(self, attr_name: str, value: Any) -> list[TE]:
        return self._get_elements_from_set_by_attribute(
            self._elements, attr_name, value
        )

    def get_elements_by_condition(self, condition: Callable[[TE], bool]) -> list[TE]:
        return [e for e in self._elements if condition(e)]

    def get_next_element(self, element: TE) -> TE | None:
        element_idx = self._elements.index(element)
        if element_idx == len(self._elements) - 1:
            return None
        else:
            return self._elements[element_idx + 1]

    def get_previous_element(self, element: TE) -> TE | None:
        element_idx = self._elements.index(element)
        if element_idx == 0:
            return None
        else:
            return self._elements[element_idx - 1]

    def get_next_element_by_time(
        self, time: float, elements: Iterable[TE] | None = None
    ) -> TE | None:
        # Expects elements to be sorted by time
        elements = elements if elements is not None else self.get_elements()
        times = [e.get_data("time") for e in elements]
        idx = bisect.bisect_left(times, time)
        if idx == len(times) - 1:
            return None
        else:
            return elements[idx + 1]

    def get_previous_element_by_time(
        self, time: float, elements: Iterable[TE] | None = None
    ) -> TE | None:
        # Expects elements to be sorted by time
        elements = elements if elements is not None else self.get_elements()
        times = [e.get_data("time") for e in elements]
        idx = bisect.bisect_left(times, time)
        if idx == 0:
            return None
        else:
            return elements[idx - 1]

    def get_element_by_condition(self, condition: Callable[[TE], bool]) -> TE | None:
        return next((e for e in self._elements if condition(e)), None)

    def get_existing_values_for_attribute(self, attr_name: str) -> set:
        return set([getattr(cmp, attr_name) for cmp in self._elements])

    @staticmethod
    def _get_element_from_set_by_attribute(
        cmp_list: list[TE], attr_name: str, value: Any
    ) -> TE | None:
        return next((e for e in cmp_list if getattr(e, attr_name) == value), None)

    @staticmethod
    def _get_elements_from_set_by_attribute(
        cmp_list: list[TE], attr_name: str, value: Any
    ) -> list[TE]:
        return [e for e in cmp_list if getattr(e, attr_name) == value]

    def select_element(self, element: TE) -> bool:
        if element not in self._selected_elements:
            self._add_to_selected_elements_set(element)
            element.on_select()
            return True
        return False

    def deselect_element(self, element: TE) -> bool:
        if element in self._selected_elements:
            self._remove_from_selected_elements_set(element)
            element.on_deselect()
            return True
        return False

    def _deselect_if_selected(self, element: TE):
        if element in self._selected_elements:
            self.deselect_element(element)

    def deselect_all_elements(self):
        for element in self._selected_elements.copy():
            self.deselect_element(element)

    def _add_to_selected_elements_set(self, element: TE) -> None:
        bisect.insort_left(self._selected_elements, element)

    def _remove_from_selected_elements_set(self, element: TE) -> None:
        try:
            self._selected_elements.remove(element)
        except ValueError as e:
            raise ValueError(
                f"Can't remove element '{element}' from selected objects of {self}: not"
                " in self._selected_elements."
            ) from e

    def get_selected_elements(self) -> list[TE]:
        return self._selected_elements

    def delete_element(self, element: TE):
        element.delete()
        self._remove_from_elements_set(element)

    @staticmethod
    def get_child_items_from_elements(
        elements: list[TE],
    ) -> list[int]:
        drawings_ids = []
        for element in elements:
            for id_ in element.child_items():
                drawings_ids.append(id_)

        return drawings_ids

    def __repr__(self) -> str:
        return get_tilia_class_string(self)

    def get_elements(self) -> list[TE]:
        return self._elements

    def update_time_on_elements(self) -> None:
        for element in self._elements:
            element.update_position()

    def update_element_order(self, element: TE):
        self._elements.remove(element)
        bisect.insort_left(self._elements, element)
