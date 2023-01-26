from __future__ import annotations

import functools
import logging
import tkinter as tk
from abc import ABC
from enum import Enum, auto

from typing import runtime_checkable, Protocol, Any, Callable, TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from tilia.ui.timelines.collection import TimelineUICollection

from tilia import events
from tilia.events import Event, unsubscribe, unsubscribe_from_all, subscribe
from tilia.misc_enums import Side
from tilia.repr import default_str
from tilia.timelines.common import (
    TimelineComponent,
    log_object_creation,
    InvalidComponentKindError,
)
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.state_actions import Action
from tilia.ui.common import ask_for_int, ask_for_string
from tilia.ui.element_kinds import UIElementKind
from tilia.ui.modifier_enum import ModifierEnum
from tilia.ui.timelines.common import TimelineUIElement, TimelineCanvas, TimelineToolbar
from tilia.ui.timelines.copy_paste import (
    CopyAttributes,
    get_copy_data_from_elements,
    Copyable,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class Inspectable(Protocol):
    """Protocol for timeline elements that may be inspected by the inspector window.
    When selected, they must pass a dict with the attributes to be displayed via an event."""

    id: int
    timeline_ui: TimelineUI
    INSPECTOR_FIELDS: list[tuple[str, str]]
    FIELD_NAMES_TO_ATTRIBUTES: dict[str, str]

    def get_inspector_dict(self) -> dict[str:Any]:
        ...


@runtime_checkable
class Selectable(Protocol):
    """
    Interface for objects that can be selected.
    Selectables must 'selection_triggers', a list of the canvas drawing ids
    that count for selecting it.
    Obs.: selection triggers may not coincide with all the elements canvas drawings,
    as in the case of HierarchyUnitTkUI.
    """

    selection_triggers: tuple[int, ...]

    def on_select(self) -> None:
        ...


@runtime_checkable
class LeftClickable(Protocol):
    """
    Interface for objects that respond to left clicks (independent of selection).
    Used, for instance, to trigger dragging of a hierarchy ui boundary marker.
    Left clickable must have the property 'left_click_triggers',
    a list of the canvas drawing ids that count for triggering its on_left_click method.
    """

    left_click_triggers: tuple[int, ...]

    def on_left_click(self, clicked_item_id: int) -> None:
        ...


@runtime_checkable
class RightClickable(Protocol):
    """
    Interface for objects that respond to right clicks
    Used, for instance, to display a right click menu.
    """

    right_click_triggers: tuple[int, ...]

    def on_right_click(self, x: float, y: float, clicked_item_id: int) -> None:
        ...


@runtime_checkable
class DoubleLeftClickable(Protocol):
    """
    Interface for objects that respond to double left clicks (independent of selection).
    Used, for instance, to trigger dragging of a hierarchy ui boundary marker.
    Left clickable must 'double_left_cilck_triggers', a list of the canvas drawing ids
    that count for triggering its on_double_left_click method.
    """

    double_left_click_triggers: tuple[int, ...]

    def on_double_left_click(self, clicked_item_id: int) -> None:
        ...


@runtime_checkable
class CanSeekTo(Protocol):
    seek_time: float


class TimelineUI(ABC):
    """
    Interface for the ui of a Timeline object.
    Is composed of:
        - a tk.Canvas;
        - a TimelineToolbar (which is shared between other uis of the same class);
        - a TimelineUiElementManager;

    Keeps a reference to the main TimelineUICollection object.

    Is responsible for processing tkinter events send to the timeline via TimelineUICollection.

    """

    TIMELINE_KIND = None
    TOOLBAR_CLASS = None
    COPY_PASTE_MANGER_CLASS = None
    DEFAULT_COPY_ATTRIBUTES = CopyAttributes([], [], [], [])

    def __init__(
        self,
        *args,
        timeline_ui_collection: TimelineUICollection,
        timeline_ui_element_manager: TimelineUIElementManager,
        component_kinds_to_classes: dict[UIElementKind : type(TimelineUIElement)],
        component_kinds_to_ui_element_kinds: dict[ComponentKind:UIElementKind],
        canvas: TimelineCanvas,
        toolbar: TimelineToolbar | None,
        name: str,
        height: int,
        is_visible: bool,
        **kwargs,
    ):
        super().__init__()

        self.timeline_ui_collection = timeline_ui_collection
        self.canvas = canvas
        self._timeline = None

        self._name = name
        self.visible = is_visible
        self._height = height
        self.canvas.update_height(
            height
        )  # can't call height setter as some attributes have not yet been set

        self.component_kinds_to_ui_element_kinds = component_kinds_to_ui_element_kinds
        self.element_manager = timeline_ui_element_manager
        self.component_kinds_to_classes = component_kinds_to_classes
        self.toolbar = toolbar

        self.right_clicked_element = None

        self._setup_visiblity(is_visible)

        subscribe(self, Event.INSPECTOR_WINDOW_OPENED, self.on_inspector_window_opened)

    @property
    def timeline(self):
        return self._timeline

    @timeline.setter
    def timeline(self, value):
        logger.debug(f"Setting {self} timeline as {value}")
        self._timeline = value

    @property
    def display_position(self):
        return self.timeline_ui_collection.get_timeline_display_position(self)

    def get_id(self) -> str:
        return self.timeline_ui_collection.get_id()

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        self.canvas.update_label(value)

    @property
    def height(self):
        return self._height

    @height.setter
    def height(self, value):
        self._height = value
        self.canvas.update_height(value)
        self.update_elements_position()

    @property
    def elements(self):
        return list(self.element_manager.get_all_elements())

    @property
    def selected_elements(self):
        return self.element_manager.get_selected_elements()

    @property
    def selected_components(self):
        return [element.tl_component for element in self.selected_elements]

    # noinspection PyUnresolvedReferences
    def _setup_visiblity(self, is_visible: bool):
        self.is_visible = is_visible

        if not self.is_visible:
            self.timeline_ui_collection.hide_timeline_ui(self)

    def get_ui_for_component(
        self, component_kind: ComponentKind, component: TimelineComponent, **kwargs
    ):
        return self.element_manager.create_element(
            self.component_kinds_to_ui_element_kinds[component_kind],
            component,
            self,
            self.canvas,
            **kwargs,
        )

    def on_click(
        self,
        x: int,
        y: int,
        item_id: int,
        button: Side,
        modifier: ModifierEnum,
        double: bool,
        root_x: int = None,
        root_y: int = None,
    ) -> None:

        logger.debug(f"Processing click on {self}...")

        if not item_id:
            if button == Side.LEFT:
                logger.debug(f"No canvas item was clicked.")
            else:
                self.display_right_click_menu_for_timeline(x, y)
            return

        clicked_elements = self.get_clicked_element(item_id)

        if not clicked_elements:
            logger.debug(f"No ui element was clicked.")
            return

        for (
            elm
        ) in clicked_elements:  # clicked item might be owned by more than on element
            if button == Side.LEFT:
                if not double:
                    self._process_ui_element_left_click(elm, item_id)
                else:
                    double_clicked = self._process_ui_element_double_left_click(
                        elm, item_id
                    )
                    if not double_clicked:  # consider as single click
                        self._process_ui_element_left_click(elm, item_id)
            elif button == Side.RIGHT:
                self._process_ui_element_right_click(root_x, root_y, elm, item_id)

        logger.debug(f"Processed click on {self}.")

    def get_clicked_element(self, clicked_item_id: int) -> list[TimelineUIElement]:

        owns_clicked_item = lambda e: clicked_item_id in e.canvas_drawings_ids

        clicked_elements = self.element_manager.get_elements_by_condition(
            owns_clicked_item, kind=UIElementKind.ANY
        )

        return clicked_elements

    def select_element_if_appropriate(
        self, element: TimelineUIElement, canvas_item_id: int
    ) -> bool:
        if (
            isinstance(element, Selectable)
            and canvas_item_id in element.selection_triggers
        ):
            self.select_element(element)
            return True
        else:
            logger.debug(f"Element is not selectable.")
            return False

    def _process_ui_element_left_click(
        self, clicked_element: TimelineUIElement, clicked_item_id: int
    ) -> None:

        logger.debug(f"Processing left click on ui element '{clicked_element}'...")

        was_selected = self.select_element_if_appropriate(
            clicked_element, clicked_item_id
        )
        if was_selected and isinstance(clicked_element, CanSeekTo):
            events.post(
                Event.PLAYER_REQUEST_TO_SEEK_IF_NOT_PLAYING, clicked_element.seek_time
            )

        if (
            isinstance(clicked_element, LeftClickable)
            and clicked_item_id in clicked_element.left_click_triggers
        ):
            clicked_element.on_left_click(clicked_item_id)
        else:
            logger.debug(f"Element is not left clickable.")

        logger.debug(f"Processed click on ui element '{clicked_element}'.")

    def _process_ui_element_double_left_click(
        self, clicked_element: TimelineUIElement, clicked_item_id: int
    ) -> None | bool:

        logger.debug(f"Processing double click on ui element '{clicked_element}'...")

        was_selected = self.select_element_if_appropriate(
            clicked_element, clicked_item_id
        )
        if was_selected and isinstance(clicked_element, CanSeekTo):
            events.post(
                Event.PLAYER_REQUEST_TO_SEEK_IF_NOT_PLAYING, clicked_element.seek_time
            )

        if (
            isinstance(clicked_element, DoubleLeftClickable)
            and clicked_item_id in clicked_element.double_left_click_triggers
        ):
            clicked_element.on_double_left_click(clicked_item_id)
            return True
        else:
            logger.debug(f"Element is not double clickable.")
            return False

    def _process_ui_element_right_click(
        self,
        root_x: int,
        root_y: int,
        clicked_element: TimelineUIElement,
        clicked_item_id: int,
    ) -> None:

        if (
            isinstance(clicked_element, RightClickable)
            and clicked_item_id in clicked_element.right_click_triggers
        ):
            events.subscribe(
                self,
                Event.RIGHT_CLICK_MENU_OPTION_CLICK,
                self.on_right_click_menu_option_click,
            )
            clicked_element.on_right_click(root_x, root_y, clicked_item_id)
        else:
            logger.debug(f"Element is not right clickable.")

    def select_element(self, element: Selectable):

        self.element_manager.select_element(element)

        if isinstance(element, Inspectable):
            logger.debug(f"Element is inspectable. Sending data to inspector.")
            self.post_inspectable_selected_event(element)

            events.subscribe(
                element,
                Event.INSPECTOR_FIELD_EDITED,
                functools.partial(on_inspector_field_edited, element),
            )

    def deselect_element(self, element: Selectable):
        self.element_manager.deselect_element(element)

        if isinstance(element, Inspectable):
            events.unsubscribe(element, Event.INSPECTOR_FIELD_EDITED)

            events.post(Event.INSPECTABLE_ELEMENT_DESELECTED, element.id)

    def deselect_all_elements(self):
        for element in self.selected_elements.copy():
            self.deselect_element(element)

    def on_right_click_menu_option_click(self, option: RightClickOption):
        ...

    def on_right_click_menu_new(self) -> None:
        unsubscribe(self, Event.RIGHT_CLICK_MENU_OPTION_CLICK)
        unsubscribe(self, Event.RIGHT_CLICK_MENU_NEW)

    def listen_for_uielement_rightclick_options(
        self, element: TimelineUIElement
    ) -> None:
        self.right_clicked_element = element
        logger.debug(f"{self} is listening for right menu option clicks...")

    def display_right_click_menu_for_element(
        self,
        root_x: int,
        root_y: int,
        options: list[tuple[str, RightClickOption]],
    ):
        events.post(Event.RIGHT_CLICK_MENU_NEW)
        events.subscribe(
            self,
            Event.RIGHT_CLICK_MENU_OPTION_CLICK,
            self.on_right_click_menu_option_click,
        )

        display_right_click_menu(
            root_x,
            root_y,
            options,
        )

        events.subscribe(self, Event.RIGHT_CLICK_MENU_NEW, self.on_right_click_menu_new)

    def display_right_click_menu_for_timeline(self, canvas_x: float, canvas_y: float):
        RIGHT_CLICK_OPTIONS = [
            ("Change timeline name...", RightClickOption.CHANGE_TIMELINE_NAME),
            ("Change timeline height...", RightClickOption.CHANGE_TIMELINE_HEIGHT),
        ]

        events.post(Event.RIGHT_CLICK_MENU_NEW)
        events.subscribe(
            self,
            Event.RIGHT_CLICK_MENU_OPTION_CLICK,
            self.on_right_click_menu_option_click,
        )

        display_right_click_menu(
            self.canvas.winfo_rootx() + int(canvas_x),
            self.canvas.winfo_rooty() + int(canvas_y),
            RIGHT_CLICK_OPTIONS,
        )

        events.subscribe(self, Event.RIGHT_CLICK_MENU_NEW, self.on_right_click_menu_new)

    def right_click_menu_change_timeline_height(self) -> None:
        height = ask_for_int(
            "Change timeline height",
            "Insert new timeline height",
            initialvalue=self.height,
        )
        if height:
            logger.debug(f"User requested new timeline height of '{height}'")
            self.height = height
            self.timeline_ui_collection.after_height_change(self)

        events.post(Event.REQUEST_RECORD_STATE, Action.TIMELINE_HEIGHT_CHANGE)

    def right_click_menu_change_timeline_name(self) -> None:
        name = ask_for_string(
            "Change timeline name", "Insert new timeline name", initialvalue=self.name
        )
        if name:
            logger.debug(f"User requested new timeline name of '{name}'")
            self.name = name

        events.post(Event.REQUEST_RECORD_STATE, Action.TIMELINE_NAME_CHANGE)

    def on_inspector_window_opened(self):
        for element in self.selected_elements:
            logger.debug(
                f"Notifying inspector of previsously selected elements on {self}..."
            )
            self.post_inspectable_selected_event(element)

    @staticmethod
    def post_inspectable_selected_event(element: Inspectable):
        events.post(
            Event.INSPECTABLE_ELEMENT_SELECTED,
            type(element),
            element.INSPECTOR_FIELDS,
            element.get_inspector_dict(),
            element.id,
        )

    def update_elements_position(self) -> None:
        self.element_manager.update_elements_postion()

    def on_delete_press(self):
        self.timeline.on_request_to_delete_components(self.selected_components)

    def delete_selected_elements(self):
        if not self.selected_elements:
            return

        for component in self.selected_components:
            self.timeline.on_request_to_delete_components([component])

    def delete_element(self, element: TimelineUIElement):
        if element in self.selected_elements:
            self.deselect_element(element)

        self.element_manager.delete_element(element)

    def debug_selected_elements(self):
        logger.debug(f"========== {self} ==========")
        for element in self.selected_elements.copy():
            from pprint import pprint

            logger.debug(f"----- {element} -----")
            logger.debug("--- UIElement attributes ---")
            pprint(element.__dict__)
            logger.debug("--- Component attributes ---")
            pprint(element.tl_component.__dict__)

    def validate_copy(self, elements: list[TimelineUIElement]) -> None:
        """Can be overwritten by subcalsses to implement validation"""
        pass

    def validate_paste(
        self, paste_data: dict, elements_to_receive_paste: list[TimelineUIElement]
    ) -> None:
        """Can be overwritten by subcalsses to implement validation"""
        pass

    def get_copy_data_from_selected_elements(self) -> list[dict]:
        self.validate_copy(self.selected_elements)

        return get_copy_data_from_elements(
            [
                (el, el.DEFAULT_COPY_ATTRIBUTES)
                for el in self.selected_elements
                if isinstance(el, Copyable)
            ]
        )

    # noinspection PyUnresolvedReferences
    def get_left_margin_x(self):
        return self.timeline_ui_collection.left_margin_x

    # noinspection PyUnresolvedReferences
    def get_right_margin_x(self):
        return self.timeline_ui_collection.right_margin_x

    # noinspection PyUnresolvedReferences
    def get_timeline_width(self):
        return self.timeline_ui_collection.timeline_width

    # noinspection PyUnresolvedReferences
    def get_time_by_x(self, x: float) -> float:
        return self.timeline_ui_collection.get_time_by_x(x)

    # noinspection PyUnresolvedReferences
    def get_x_by_time(self, time: float) -> float:
        return self.timeline_ui_collection.get_x_by_time(time)

    def get_id_for_element(self):
        return self.timeline_ui_collection.get_id()

    @property
    def has_selected_elements(self):
        return self.element_manager.has_selected_elements

    def delete_workaround_with_grid_forget(self):
        """
        For some unkwon reason, calling self.canvas.destroy()
        when undoing timeline creation is causing the app
        to not respond to keyboard shortcuts. This workaround
        uses grid_forget() instead, which causes small memory leaks.
        """
        unsubscribe_from_all(self)
        self.canvas.grid_forget()
        if self.toolbar:
            self.toolbar.on_timeline_delete()

    def delete(self):
        logger.info(f"Deleting timeline ui {self}...")

        unsubscribe_from_all(self)
        unsubscribe_from_all(self.canvas)
        self.canvas.destroy()
        if self.toolbar:
            self.toolbar.on_timeline_delete()

    def __repr__(self):
        return default_str(self)

    def __str__(self):
        return f"{self.name} | {self.TIMELINE_KIND.value.capitalize().split('_')[0]} Timeline"


class RightClickOption(Enum):
    RESET_MEASURE_NUMBER = auto()
    CHANGE_BEATS_IN_MEASURE = auto()
    DISTRIBUTE_BEATS = auto()
    CHANGE_MEASURE_NUMBER = auto()
    INSPECT = auto()
    EXPORT_TO_AUDIO = auto()
    CHANGE_TIMELINE_NAME = auto()
    CHANGE_TIMELINE_HEIGHT = auto()
    RESET_COLOR = auto()
    SEPARATOR = auto()
    PASS = auto()
    INCREASE_LEVEL = auto()
    DECREASE_LEVEL = auto()
    CREATE_UNIT_BELOW = auto()
    CHANGE_COLOR = auto()
    EDIT = auto()
    COPY = auto()
    PASTE = auto()
    PASTE_WITH_ALL_ATTRIBUTES = auto()
    DELETE = auto()


def display_right_click_menu(
    x: int, y: int, options: list[tuple[str, RightClickOption]]
) -> None:
    class RightClickMenu:
        def __init__(self, x: int, y: int, options: list[tuple[str, RightClickOption]]):
            self.tk_menu = tk.Menu(tearoff=False)
            self.register_options(options)
            self.tk_menu.tk_popup(x, y)

        def register_options(self, options: list[tuple[str, RightClickOption]]):

            for option in options:
                if option[1] == RightClickOption.SEPARATOR:
                    self.tk_menu.add_separator()
                else:
                    self.tk_menu.add_command(
                        label=option[0],
                        command=lambda _option=option[1]: events.post(
                            Event.RIGHT_CLICK_MENU_OPTION_CLICK, _option
                        ),
                    )

    RightClickMenu(x, y, options)


def on_inspector_field_edited(
    element: Inspectable, field_name: str, value: str, inspected_id: int
) -> None:

    if not inspected_id == element.id:
        return

    attr = element.FIELD_NAMES_TO_ATTRIBUTES[field_name]
    logger.debug(f"Processing inspector field edition for {element}...")

    logger.debug(f"Attribute edited is '{attr}'.")

    if value == getattr(element, attr):
        logger.debug(f"'{element}' already has '{attr}' = '{value}'. Nothing to do.")
        return

    setattr(element, attr, value)
    logger.debug(f"New value is '{value}'.")

    events.post(
        Event.REQUEST_RECORD_STATE,
        Action.ATTRIBUTE_EDIT_VIA_INSPECTOR,
        no_repeat=True,
        repeat_identifier=f"{attr}_{element.id}",
    )


class TimelineUIElementManager:
    """
    Composes a TimelineUI object.
    Is responsible for:
        - Creating timeline elements;
        - Querying timeline ui elements and its attributes (e.g. to know which one was clicked);
        - Handling selections and deselections;
        - Deleting timeline elements;
    """

    SomeTimelineUIElement = TypeVar("SomeTimelineUIElement", bound="TimelineUIElement")

    @log_object_creation
    def __init__(
        self, element_kinds_to_classes: dict[UIElementKind : type(TimelineUIElement)]
    ):

        self._elements = set()
        self._element_kinds_to_classes = element_kinds_to_classes

        self._selected_elements = []

    @property
    def has_selected_elements(self):
        return bool(self._selected_elements)

    @property
    def element_kinds(self):
        return [kind for kind, _ in self._element_kinds_to_classes.items()]

    @property
    def ordered_elements(self):
        return sorted(self._elements, key=lambda e: (e.level, e.start))

    def create_element(
        self,
        kind: UIElementKind,
        component: TimelineComponent,
        timeline_ui: TimelineUI,
        canvas: TimelineCanvas,
        *args,
        **kwargs,
    ):
        self._validate_element_kind(kind)
        element_class = self._get_element_class_by_kind(kind)
        element = element_class.create(component, timeline_ui, canvas, *args, **kwargs)

        self._add_to_elements_set(element)

        return element

    def _add_to_elements_set(self, element: SomeTimelineUIElement) -> None:
        logger.debug(f"Adding element '{element}' to {self}.")
        self._elements.add(element)

    def _remove_from_elements_set(self, element: SomeTimelineUIElement) -> None:
        logger.debug(f"Removing element '{element}' from {self}.")
        try:
            self._elements.remove(element)
        except ValueError:
            raise ValueError(
                f"Can't remove element '{element}' from {self}: not in self._elements."
            )

    def get_element_by_attribute(self, attr_name: str, value: Any, kind: UIElementKind):
        element_set = self._get_element_set_by_kind(kind)
        return self._get_element_from_set_by_attribute(element_set, attr_name, value)

    def get_elements_by_attribute(
        self, attr_name: str, value: Any, kind: UIElementKind
    ) -> list:
        element_set = self._get_element_set_by_kind(kind)
        return self._get_elements_from_set_by_attribute(element_set, attr_name, value)

    def get_elements_by_condition(
        self, condition: Callable[[SomeTimelineUIElement], bool], kind: UIElementKind
    ) -> list:
        element_set = self._get_element_set_by_kind(kind)
        return [e for e in element_set if condition(e)]

    def get_element_by_condition(
        self, condition: Callable[[SomeTimelineUIElement], bool], kind: UIElementKind
    ) -> SomeTimelineUIElement:
        element_set = self._get_element_set_by_kind(kind)
        return next((e for e in element_set if condition(e)), None)

    def get_existing_values_for_attribute(
        self, attr_name: str, kind: UIElementKind
    ) -> set:
        element_set = self._get_element_set_by_kind(kind)
        return set([getattr(cmp, attr_name) for cmp in element_set])

    def _get_element_set_by_kind(self, kind: UIElementKind) -> set:
        if kind == UIElementKind.ANY:
            return self._elements
        cmp_class = self._get_element_class_by_kind(kind)

        return {elmt for elmt in self._elements if isinstance(elmt, cmp_class)}

    def _get_element_class_by_kind(
        self, kind: UIElementKind
    ) -> type(SomeTimelineUIElement):
        self._validate_element_kind(kind)
        return self._element_kinds_to_classes[kind]

    def _validate_element_kind(self, kind: UIElementKind):
        if kind not in self.element_kinds:
            raise InvalidComponentKindError(f"Got invalid element kind {kind}")

    @staticmethod
    def _get_element_from_set_by_attribute(
        cmp_list: set, attr_name: str, value: Any
    ) -> Any | None:
        return next((e for e in cmp_list if getattr(e, attr_name) == value), None)

    @staticmethod
    def _get_elements_from_set_by_attribute(
        cmp_list: set, attr_name: str, value: Any
    ) -> list:
        return [e for e in cmp_list if getattr(e, attr_name) == value]

    def select_element(self, element: SomeTimelineUIElement) -> None:
        logger.debug(f"Selecting element '{element}'")
        if element not in self._selected_elements:
            self._add_to_selected_elements_set(element)
            element.on_select()
        else:
            logger.debug(f"Element '{element}' is already selected.")

    def deselect_element(self, element: SomeTimelineUIElement) -> None:

        if element in self._selected_elements:
            logger.debug(f"Deselecting element '{element}'")
            self._remove_from_selected_elements_set(element)
            element.on_deselect()

    def _deselect_if_selected(self, element: SomeTimelineUIElement):
        logger.debug(f"Will deselect {element} if it is selected.")
        if element in self._selected_elements:
            self.deselect_element(element)
        else:
            logger.debug(f"Element was not selected.")

    def deselect_all_elements(self):
        logger.debug(f"Deselecting all elements of {self}")
        for element in self._selected_elements.copy():
            self.deselect_element(element)

    def _add_to_selected_elements_set(self, element: SomeTimelineUIElement) -> None:
        logger.debug(f"Adding element '{element}' to selected elements {self}.")
        self._selected_elements.append(element)

    def _remove_from_selected_elements_set(
        self, element: SomeTimelineUIElement
    ) -> None:
        logger.debug(f"Removing element '{element}' from selected elements of {self}.")
        try:
            self._selected_elements.remove(element)
        except ValueError:
            raise ValueError(
                f"Can't remove element '{element}' from selected objects of {self}: not in self._selected_elements."
            )

    def get_selected_elements(self) -> list[SomeTimelineUIElement]:
        return self._selected_elements

    def delete_element(self, element: SomeTimelineUIElement):
        logger.debug(f"Deleting UI element '{element}'")
        # self._deselect_if_selected(element)
        element.delete()
        element
        self._remove_from_elements_set(element)

    @staticmethod
    def get_canvas_drawings_ids_from_elements(
        elements: list[SomeTimelineUIElement],
    ) -> list[int]:
        drawings_ids = []
        for element in elements:
            for id_ in element.canvas_drawings_ids:
                drawings_ids.append(id_)

        return drawings_ids

    def __repr__(self) -> str:
        return default_str(self)

    def get_all_elements(self) -> set:
        return self._elements

    def update_elements_postion(self) -> None:
        """
        Calls the update_position method on all manager's elements.
        Should be called when zooming, for instance.
        """

        for element in self._elements:
            element.update_position()
