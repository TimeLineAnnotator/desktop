from __future__ import annotations

import functools
import importlib
from abc import ABC
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    TypeVar,
)

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QGraphicsItem

from tilia.requests import (
    Get,
    Post,
    get,
    listen,
    post,
    stop_listening,
    stop_listening_to_all,
)
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.component_kinds import ComponentKind
from tilia.ui import commands
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.base.element_manager import ElementManager
from tilia.ui.timelines.copy_paste import (
    CopyAttributes,
    get_copy_data_from_element,
    get_copy_data_from_elements,
)
from tilia.ui.timelines.scene import TimelineScene
from tilia.utils import get_sibling_packages, get_tilia_class_string

from ...coords import time_x_converter
from ...windows import WindowKind
from ..view import TimelineView
from .context_menus import TimelineUIContextMenu

if TYPE_CHECKING:
    from tilia.ui.timelines.collection.collection import TimelineSelector, TimelineUIs

T = TypeVar("T", bound="TimelineUIElement")


def with_elements(func: Callable) -> Callable:
    """Decorator to handle element selection for timeline commands.

    If no elements are provided, uses the timeline's selected elements.
    If no elements are selected, returns False.
    """

    @functools.wraps(func)
    def wrapper(
        self, elements: list[TimelineUIElement] | None = None, *args: Any, **kwargs: Any
    ) -> Any:
        if not elements:
            if not self.selected_elements:
                return False
            elements = self.selected_elements
        return func(self, elements, *args, **kwargs)

    return wrapper


class TimelineUI(ABC):  # noqa: B024
    TIMELINE_KIND = None
    TOOLBAR_CLASS = None
    COPY_PASTE_MANGER_CLASS = None
    DEFAULT_COPY_ATTRIBUTES = CopyAttributes([], [])
    ELEMENT_CLASS: type[TimelineUIElement] = TimelineUIElement
    UPDATE_TRIGGERS = ["name", "height", "is_visible", "ordinal"]
    CONTEXT_MENU_CLASS: type[TimelineUIContextMenu] = TimelineUIContextMenu
    ACCEPTS_VERTICAL_ARROWS = False
    ACCEPTS_HORIZONTAL_ARROWS = False

    def __init__(
        self,
        id: int,
        collection: TimelineUIs,
        element_manager: ElementManager,
        scene: TimelineScene,
        view: TimelineView,
    ):
        super().__init__()
        self.id = id
        self.collection = collection
        self.scene = scene
        self.view = view

        self.element_manager = element_manager

        self._setup_visibility()
        self._setup_collection_requests()

        listen(self, Post.WINDOW_OPEN_DONE, self.on_window_open_done)

    def __iter__(self):
        return iter(self.elements)

    def __getitem__(self, item):
        return self.elements[item]

    def __len__(self):
        return len(self.elements)

    def __bool__(self):
        """Prevents False form being returned when timeline is empty."""
        return True

    def __lt__(self, other):
        return self.get_data("ordinal") < other.get_data("ordinal")

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
            importlib.import_module(pkg)

        cls.SUBCLASSES_ARE_LOADED = True

    @property
    def is_empty(self):
        return self.timeline.is_empty

    @property
    def timeline(self):
        return get(Get.TIMELINE, self.id)

    @property
    def elements(self):
        return self.element_manager.get_elements()

    @property
    def id_to_element(self):
        return self.element_manager.id_to_element

    @property
    def selected_elements(self):
        return self.element_manager.get_selected_elements()

    @property
    def selected_components(self):
        return [element.tl_component for element in self.selected_elements]

    @property
    def has_selected_elements(self):
        return self.element_manager.has_selected_elements

    @property
    def playback_line(self):
        return self.scene.playback_line

    @property
    def displayed_name(self):
        return self.scene.text.toPlainText()

    @classmethod
    def register_timeline_command(
        cls,
        collection: TimelineUIs,
        name: str,
        callback: Callable,
        selector: TimelineSelector,
        *args,
        **kwargs,
    ):
        """
        Register a command named "timeline.{timeline_kind}.{name}" for this timeline kind
        with TimelineUIs.on_timeline_command() as a wrapper for the callback.
        """
        kind_shortname = cls.TIMELINE_KIND.name.lower().replace("_timeline", "")

        commands.register(
            f"timeline.{kind_shortname}.{name}",
            functools.partial(
                collection.on_timeline_command, cls.TIMELINE_KIND, callback, selector
            ),
            *args,
            **kwargs,
        )

    @classmethod  # noqa: B027
    def register_commands(cls, collection: TimelineUIs):
        """
        Override to register commands for this timeline kind.
        This will be called by TimelineUIs.register_commands() on launch.
        """

    def get_data(self, attr: str):
        return self.timeline.get_data(attr)

    def set_data(self, attr: str, value: Any):
        return self.timeline.set_data(attr, value)

    def get_height(self):
        return self.get_data("height")

    def _setup_visibility(self):
        self.view.set_is_visible(self.get_data("is_visible"))

    def update(self, attr):
        if attr not in self.UPDATE_TRIGGERS:
            return

        update_func_name = "update_" + attr
        if not hasattr(self, update_func_name):
            raise ValueError(f"{self} has no updater function for attribute '{attr}'")

        getattr(self, update_func_name)()

    def update_is_visible(self):
        self.view.set_is_visible(self.get_data("is_visible"))
        self.collection.update_timeline_uis_position()
        self.collection.update_toolbar_visibility()

    def update_height(self):
        height = self.get_data("height")
        self.scene.set_height(height)
        self.view.set_height(height)
        self.element_manager.update_time_on_elements()

    def update_name(self):
        self.scene.set_text(self.get_data("name"))

    def set_width(self, width):
        self.scene.set_width(int(width))
        self.view.setFixedWidth(int(width))
        self.element_manager.update_time_on_elements()
        self.scene.set_playback_line_pos(
            time_x_converter.get_x_by_time(get(Get.SELECTED_TIME))
        )
        (loop_start, loop_end) = get(Get.LOOP_TIME)
        self.scene.set_loop_box_position(
            time_x_converter.get_x_by_time(loop_start),
            time_x_converter.get_x_by_time(loop_end),
        )

    def update_ordinal(self):
        self.collection.update_timeline_ui_ordinal()

    def get_element(self, id: int) -> T:
        return self.element_manager.get_element(id)

    def get_elements_by_attr(self, attr: str, value: Any) -> list[T]:
        return [el for el in self.elements if getattr(el, attr) == value]

    @staticmethod
    def set_elements_attr(elements: list[T], attr: str, value: Any):
        for elm in elements:
            elm.set_data(attr, value)

    def get_timeline_component(self, id: int):
        return self.timeline.get_component(id)

    def get_component_ui(self, component: TimelineComponent):
        return self.id_to_element[component.id]

    def _setup_collection_requests(self):
        self.request_to_callback = {}

    def on_timeline_component_created(
        self, kind: ComponentKind, id: int, get_data, set_data
    ):
        return self.element_manager.create_element(
            kind, id, self, self.scene, get_data, set_data
        )

    def on_timeline_component_deleted(self, id: int):
        self.delete_element(self.id_to_element[id])

    def update_selection_on_right_click(
        self,
        elements: list[T],
        item: QGraphicsItem,
        modifier: Qt.KeyboardModifier,
    ):
        if (
            modifier == Qt.KeyboardModifier.NoModifier
            and not self.belongs_to_selection(item)
        ):
            self.deselect_all_elements(excluding=elements)
        if not self.has_selected_elements and elements:
            for elm in elements:
                self.select_element(elm)

    def on_right_click(
        self,
        x: int,
        y: int,
        item: QGraphicsItem,
        modifier: Qt.KeyboardModifier,
    ) -> None:
        elements = self.get_item_owner(item)

        self.update_selection_on_right_click(elements, item, modifier)

        if not item:
            self.display_timeline_context_menu(x, y)

        for elm in elements:  # clicked item might be owned by more than on element
            elm.on_right_click(x, y, item)

    @staticmethod
    def should_select(element: TimelineUIElement, item: QGraphicsItem) -> bool:
        return item in element.selection_triggers() and hasattr(element, "on_select")

    def on_left_click(
        self,
        item: QGraphicsItem,
        modifier: Qt.KeyboardModifier,
        double: bool,
        x: int,
        y: int,
    ) -> None:
        """Handles element selection and triggers left click side effects."""
        elements_with_side_effects = self.get_item_owner(item)

        # do not deselect if control or shift are pressed
        if (
            Qt.KeyboardModifier.ControlModifier not in modifier
            and Qt.KeyboardModifier.ShiftModifier not in modifier
        ):
            self.deselect_all_elements()

        if not elements_with_side_effects:
            return

        clicked_element = elements_with_side_effects[
            0
        ]  # other elements are only relevant for side effects
        should_select = self.should_select(clicked_element, item)

        if should_select:
            if Qt.KeyboardModifier.ControlModifier in modifier:
                self.toggle_element_selection(clicked_element)
            else:
                self.select_element(clicked_element)

        if Qt.KeyboardModifier.AltModifier not in modifier:
            self._seek_to_element(clicked_element)

        # clicked item might trigger side effects in multiple elements
        # e.g. hierarchy frame handles trigger drag in branch
        for elm in elements_with_side_effects:
            if not double:
                self._trigger_left_click_side_effects(elm, item)
            else:
                was_double_clicked = self._on_element_double_left_click(elm, item)
                if not was_double_clicked:  # consider as single click
                    self._trigger_left_click_side_effects(elm, item)

    def get_item_owner(self, item: QGraphicsItem) -> list[T]:
        """Returns the element that owns the item with the given id"""
        clicked_elements = self.element_manager.get_elements_by_condition(
            lambda e: item in e.child_items()
        )

        return clicked_elements

    @staticmethod
    def _seek_to_element(element: T) -> None:
        if hasattr(element, "seek_time"):
            post(Post.PLAYER_SEEK_IF_NOT_PLAYING, element.seek_time)

    @staticmethod
    def _trigger_left_click_side_effects(element: T, item: QGraphicsItem) -> None:
        if hasattr(element, "on_left_click") and item in element.left_click_triggers():
            element.on_left_click(item)

    @staticmethod
    def _on_element_double_left_click(element: T, item: QGraphicsItem) -> None | bool:
        if (
            hasattr(element, "on_double_left_click")
            and item in element.double_left_click_triggers()
        ):
            element.on_double_left_click(item)
            return True
        else:
            return False

    def _deselect_all_but_last(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def _deselect_all_but_first(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[1:]:
                self.element_manager.deselect_element(element)

    def on_horizontal_arrow_press(self, arrow: str):
        if not self.has_selected_elements:
            return

        if arrow not in ["right", "left"]:
            raise ValueError(f"Invalid arrow '{arrow}'.")

        if arrow == "right":
            self._deselect_all_but_last()
        else:
            self._deselect_all_but_first()

        selected_element = self.element_manager.get_selected_elements()[0]
        elements_of_kind = self.element_manager.get_elements_by_attribute(
            "kind", selected_element.get_data("KIND")
        )
        time = selected_element.get_data("time")
        if arrow == "right":
            element_to_select = self.element_manager.get_next_element_by_time(
                time, elements_of_kind
            )
        else:
            element_to_select = self.element_manager.get_previous_element_by_time(
                time, elements_of_kind
            )

        if element_to_select:
            self.deselect_element(selected_element)
            self.select_element(element_to_select)

    def select_element(self, element):
        success = self.element_manager.select_element(element)

        if hasattr(element, "INSPECTOR_FIELDS") and success:
            self.post_inspectable_selected_event(element)

            listen(
                element,
                Post.INSPECTOR_FIELD_EDITED,
                functools.partial(self.on_inspector_field_edited, element),
            )

        return success

    def select_all_elements(self):
        for element in self:
            self.select_element(element)

    def deselect_element(self, element):
        success = self.element_manager.deselect_element(element)

        if hasattr(element, "INSPECTOR_FIELDS") and success:
            stop_listening(element, Post.INSPECTOR_FIELD_EDITED)

            post(Post.INSPECTABLE_ELEMENT_DESELECTED, element.id)

        return success

    def deselect_all_elements(self, excluding: list[T] | None = None):
        if excluding is None:
            excluding = []

        for element in self.selected_elements.copy():
            if element in excluding:
                continue
            self.deselect_element(element)

    def toggle_element_selection(self, element: TimelineUIElement) -> None:
        if element in self.selected_elements:
            self.deselect_element(element)
        else:
            self.select_element(element)

    def get_next_element(self, element: T) -> T | None:
        return self.element_manager.get_next_element(element)

    def get_previous_element(self, element: T) -> T | None:
        return self.element_manager.get_previous_element(element)

    def display_timeline_context_menu(self, x: int, y: int):
        if not self.CONTEXT_MENU_CLASS:
            return
        self.CONTEXT_MENU_CLASS(self).exec(QPoint(x, y))

    def on_window_open_done(self, kind: WindowKind):
        if kind != WindowKind.INSPECT:
            return
        for element in self.selected_elements:
            self.post_inspectable_selected_event(element)

    @staticmethod
    def post_inspectable_selected_event(element):
        if not hasattr(element, "INSPECTOR_FIELDS") or not hasattr(
            element, "get_inspector_dict"
        ):
            raise ValueError(
                f"Can't inspect {element}, necessary attributes not found."
            )

        post(
            Post.INSPECTABLE_ELEMENT_SELECTED,
            type(element),
            element.INSPECTOR_FIELDS,
            element.get_inspector_dict(),
            element.id,
        )

    @staticmethod
    def on_inspector_field_edited(
        element: T, field_name: str, value: str, inspected_id: int, inspector_id: int
    ) -> None:
        if not inspected_id == element.id:
            return

        attr = element.FIELD_NAMES_TO_ATTRIBUTES[field_name]

        if value == element.get_data(attr):
            return

        element.set_data(attr, value)

        post(
            Post.APP_STATE_RECORD,
            "attribute edit via inspect",
            no_repeat=True,
            repeat_identifier=f"{attr}_{element.id}_{inspector_id}",
        )

    def delete_element(self, element: T):
        if element in self.selected_elements:
            try:
                self.deselect_element(element)
            except KeyError:
                # can't access component, as it is already deleted
                pass

        self.element_manager.delete_element(element)

    def get_copy_data_from_selected_elements(self) -> list[dict]:
        return get_copy_data_from_elements(
            [
                (el, el.DEFAULT_COPY_ATTRIBUTES)
                for el in self.selected_elements
                # if isinstance(el, Copyable)
            ]
        )

    def belongs_to_selection(self, item: QGraphicsItem):
        return self.element_manager.belongs_to_selection(item)

    def delete(self):
        stop_listening_to_all(self)
        stop_listening_to_all(self.scene)
        self.scene.destroy()

    def __repr__(self):
        return get_tilia_class_string(self)

    def __str__(self):
        return (
            f"{self.get_data('name') if self.timeline else '<unavailable>'} |"
            f" {self.TIMELINE_KIND.value.capitalize().split('_')[0]} Timeline"
        )

    def update_element_order(self, element: T):
        self.element_manager.update_element_order(element)

    @staticmethod
    def elements_to_components(
        elements: list[TimelineUIElement],
    ) -> list[TimelineComponent]:
        return [e.tl_component for e in elements]

    @with_elements
    def on_delete_component(self, elements: list[TimelineUIElement]) -> bool:
        self.timeline.delete_components(self.elements_to_components(elements))
        return True

    @with_elements
    def on_copy_element(self, elements: list[TimelineUIElement]) -> bool:
        component_data = [
            get_copy_data_from_element(e, e.DEFAULT_COPY_ATTRIBUTES) for e in elements
        ]

        if not component_data:
            return False

        post(
            Post.TIMELINE_ELEMENT_COPY_DONE,
            {"components": component_data, "timeline_kind": self.timeline.KIND},
        )
        return True

    def on_paste_element(self, clipboard_contents: dict):
        components = clipboard_contents["components"]
        cardinality = "multiple" if len(components) > 1 else "single"

        if self.has_selected_elements:
            method_name = f"paste_{cardinality}_into_selected_elements"
        else:
            method_name = f"paste_{cardinality}_into_timeline"

        if hasattr(self, method_name):
            getattr(self, method_name)(components)
            return True
        else:
            return False
