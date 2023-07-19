from __future__ import annotations
import functools
import logging
import tkinter as tk
from abc import ABC
from enum import Enum, auto
from typing import (
    runtime_checkable,
    Protocol,
    Any,
    Callable,
    TYPE_CHECKING,
    Optional,
)

from tilia.requests import Post, stop_listening, stop_listening_to_all, listen, post
from tilia.repr import default_str
from tilia.requests import get, Get
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.state_actions import Action
from tilia.ui import dialogs
from tilia.ui.modifier_enum import ModifierEnum
from tilia.ui.timelines.common import TimelineUIElement, TimelineCanvas, TimelineToolbar
from tilia.ui.timelines.copy_paste import (
    CopyAttributes,
    get_copy_data_from_elements,
    Copyable,
)

if TYPE_CHECKING:
    from tilia.ui.timelines.collection import TimelineUIs

logger = logging.getLogger(__name__)


@runtime_checkable
class Inspectable(Protocol):
    """
    Protocol for timeline elements that may be inspected by the inspector window.
    When selected, they must pass a dict with the attributes to be displayed via an
    event.
    """

    id: int
    timeline_ui: TimelineUI
    INSPECTOR_FIELDS: list[tuple[str, str]]
    FIELD_NAMES_TO_ATTRIBUTES: dict[str, str]

    def get_inspector_dict(self) -> dict[str, Any]:
        ...


@runtime_checkable
class Selectable(Protocol):
    """
    Interface for objects that can be selected. Selectables must
    'selection_triggers', a list of the canvas drawing ids that count for selecting
    it. Obs.: selection triggers may not coincide with all the elements canvas
    drawings, as in the case of HierarchyUnitTkUI.
    """

    selection_triggers: tuple[int, ...]

    def on_select(self) -> None:
        ...


@runtime_checkable
class LeftClickable(Protocol):
    """
    Interface for objects that respond to left clicks (independent of selection).
    Used, for instance, to trigger dragging of a hierarchy ui boundary marker. Left
    clickable must have the property 'left_click_triggers', a list of the canvas
    drawing ids that count for triggering its on_left_click method.
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
    Interface for objects that respond to double left clicks (independent of
    selection). Used, for instance, to trigger dragging of a hierarchy ui boundary
    marker. Left clickable must 'double_left_cilck_triggers', a list of the canvas
    drawing ids that count for triggering its on_double_left_click method.
    """

    double_left_click_triggers: tuple[int, ...]

    def on_double_left_click(self, clicked_item_id: int) -> None:
        ...


@runtime_checkable
class CanSeekTo(Protocol):
    seek_time: float


class TimelineUI(ABC):
    """
    Interface for the UI of a Timeline.
    Is composed of:
        - a tk.Canvas;
        - a TimelineToolbar (which is shared between other uis of the same class);
        - a TimelineUiElementManager;

    Is responsible for processing tkinter events send to the timeline
    via TimelineUIs.
    """

    TIMELINE_KIND = None
    TOOLBAR_CLASS = None
    COPY_PASTE_MANGER_CLASS = None
    DEFAULT_COPY_ATTRIBUTES = CopyAttributes([], [], [], [])
    ELEMENT_CLASS = TimelineUIElement

    def __init__(
        self,
        id: str,
        collection: TimelineUIs,
        element_manager: TimelineUIElementManager,
        canvas: TimelineCanvas,
        toolbar: TimelineToolbar | None,
    ):
        super().__init__()
        self.id = id
        self.collection = collection
        self.canvas = canvas

        self.element_manager = element_manager
        self.toolbar = toolbar

        self.right_clicked_element: Optional[TimelineUIElement] = None

        self._setup_visiblity()
        self._setup_height()
        self._setup_name()
        self._setup_user_actions_to_callbacks()

        listen(self, Post.INSPECTOR_WINDOW_OPENED, self.on_inspector_window_opened)

    def __iter__(self):
        return iter(self.elements)

    def __getitem__(self, item):
        return sorted(self.elements)[item]

    def __len__(self):
        return len(self.elements)

    def __bool__(self):
        """Prevents False form being returned when timeline is empty."""
        return True

    def __lt__(self, other):
        return self.ordinal < other.ordinal

    def _setup_visiblity(self):
        if not self.is_visible:
            self.collection.hide_timeline_ui(self)

    def _setup_name(self):
        self.canvas.update_label(self.name)

    def _setup_height(self):
        self.canvas.update_height(self.height)

    @property
    def timeline(self):
        return get(Get.TIMELINE, self.id)

    @property
    def name(self):
        return self.timeline.name

    @name.setter
    def name(self, value):
        self.timeline.name = value
        self.canvas.update_label(value)

    @property
    def is_visible(self):
        return self.timeline.is_visible

    @is_visible.setter
    def is_visible(self, value):
        self.timeline.is_visible = value
        self.canvas.update_label(value)

    @property
    def ordinal(self):
        return self.timeline.ordinal

    @property
    def height(self):
        return self.timeline.height

    @height.setter
    def height(self, value):
        self.timeline.height = value
        self.canvas.update_height(value)
        self.update_elements_position()

    @property
    def elements(self):
        return list(self.element_manager.get_all_elements())

    @property
    def id_to_element(self):
        return self.element_manager.id_to_element

    @property
    def selected_elements(self):
        return self.element_manager.get_selected_elements()

    @property
    def selected_components(self):
        return [element.tl_component for element in self.selected_elements]

    def get_element(self, id: str) -> TimelineUIElement:
        return self.element_manager.get_element(id)

    def get_timeline_component(self, id: int):
        return self.timeline.get_component(id)

    def get_component_ui(self, component: TimelineComponent):
        return self.id_to_element[component.id]

    # noinspection PyUnresolvedReferences

    def _setup_user_actions_to_callbacks(self):
        """
        Subclasses should override this and create a self.action_to_callback dict
        where:

        action: str = user action
        callback: Callable = function to be called when action is performed

        TimelineUIs will use this dictionary to call the appropriate function
        according to user request.
        """
        self.action_to_callback = {}

    def on_timeline_component_created(self, id: int):
        return self.element_manager.create_element(id, self, self.canvas)

    def on_timeline_component_deleted(self, id: int):
        self.delete_element(self.id_to_element[id])

    def on_right_click(
        self,
        x: int,
        y: int,
        item_id: int,
        root_x: int,
        root_y: int,
        **_,  # ignores the 'modifier' argument
    ) -> None:
        logger.debug(f"Processing click on {self}...")

        if not item_id:
            self.display_right_click_menu_for_timeline(x, y)
            return

        if not (clicked_elements := self.get_clicked_element(item_id)):
            logger.debug("No ui element was clicked.")
            return

        for (
            elm
        ) in clicked_elements:  # clicked item might be owned by more than on element
            self._on_element_right_click(root_x, root_y, elm, item_id)

        logger.debug(f"Processed click on {self}.")

    def on_left_click(self, item_id: int, modifier: ModifierEnum, double: bool) -> None:
        logger.debug(f"Processing click on {self}...")

        if not item_id:
            logger.debug("No canvas item was clicked.")

        clicked_elements = self.get_clicked_element(item_id)

        if not clicked_elements:
            logger.debug("No ui element was clicked.")

        for (
            elm
        ) in clicked_elements:  # clicked item might be owned by more than on element
            if not double:
                self.on_element_left_click(elm, item_id)
            else:
                double_clicked = self._on_element_double_left_click(elm, item_id)
                if not double_clicked:  # consider as single click
                    self.on_element_left_click(elm, item_id)

        self.deselect_all_elements(excluding=clicked_elements)

        logger.debug(f"Processed click on {self}.")

    def get_clicked_element(self, clicked_item_id: int) -> list[TimelineUIElement]:
        """Returns the element that owns the item with the given id"""
        clicked_elements = self.element_manager.get_elements_by_condition(
            lambda e: clicked_item_id in e.canvas_drawings_ids
        )

        return clicked_elements

    def select_element_if_selectable(
        self, element: TimelineUIElement, canvas_item_id: int
    ) -> bool:
        if (
            isinstance(element, Selectable)
            and canvas_item_id in element.selection_triggers
        ):
            self.select_element(element)
            return True
        else:
            logger.debug("Element is not selectable.")
            return False

    def on_element_left_click(
        self, clicked_element: TimelineUIElement, clicked_item_id: int
    ) -> None:
        logger.debug(f"Processing left click on ui element '{clicked_element}'...")

        selected = self.select_element_if_selectable(clicked_element, clicked_item_id)

        if selected and isinstance(clicked_element, CanSeekTo):
            post(Post.PLAYER_REQUEST_TO_SEEK_IF_NOT_PLAYING, clicked_element.seek_time)

        if (
            isinstance(clicked_element, LeftClickable)
            and clicked_item_id in clicked_element.left_click_triggers
        ):
            clicked_element.on_left_click(clicked_item_id)
        else:
            logger.debug("Element is not left clickable.")

        logger.debug(f"Processed click on ui element '{clicked_element}'.")

    def _on_element_double_left_click(
        self, clicked_element: TimelineUIElement, clicked_item_id: int
    ) -> None | bool:
        logger.debug(f"Processing double click on ui element '{clicked_element}'...")

        was_selected = self.select_element_if_selectable(
            clicked_element, clicked_item_id
        )
        if was_selected and isinstance(clicked_element, CanSeekTo):
            post(Post.PLAYER_REQUEST_TO_SEEK_IF_NOT_PLAYING, clicked_element.seek_time)

        if (
            isinstance(clicked_element, DoubleLeftClickable)
            and clicked_item_id in clicked_element.double_left_click_triggers
        ):
            clicked_element.on_double_left_click(clicked_item_id)
            return True
        else:
            logger.debug("Element is not double clickable.")
            return False

    def _on_element_right_click(
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
            listen(
                self,
                Post.RIGHT_CLICK_MENU_OPTION_CLICK,
                self.on_right_click_menu_option_click,
            )
            clicked_element.on_right_click(root_x, root_y, clicked_item_id)
        else:
            logger.debug("Element is not right clickable.")

    def select_element(self, element):
        self.element_manager.select_element(element)

        if isinstance(element, Inspectable):
            logger.debug("Element is inspectable. Sending data to inspector.")
            self.post_inspectable_selected_event(element)

            listen(
                element,
                Post.INSPECTOR_FIELD_EDITED,
                functools.partial(on_inspector_field_edited, element),
            )

    def deselect_element(self, element):
        self.element_manager.deselect_element(element)

        if isinstance(element, Inspectable):
            stop_listening(element, Post.INSPECTOR_FIELD_EDITED)

            post(Post.INSPECTABLE_ELEMENT_DESELECTED, element.id)

    def deselect_all_elements(self, excluding: list[TimelineUIElement] | None = None):
        if excluding is None:
            excluding = []

        for element in self.selected_elements.copy():
            if element in excluding:
                continue
            self.deselect_element(element)

    def on_right_click_menu_option_click(self, option: RightClickOption):
        ...

    def on_right_click_menu_new(self) -> None:
        stop_listening(self, Post.RIGHT_CLICK_MENU_OPTION_CLICK)
        stop_listening(self, Post.RIGHT_CLICK_MENU_NEW)

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
        post(Post.RIGHT_CLICK_MENU_NEW)
        listen(
            self,
            Post.RIGHT_CLICK_MENU_OPTION_CLICK,
            self.on_right_click_menu_option_click,
        )

        display_right_click_menu(
            root_x,
            root_y,
            options,
        )

        listen(self, Post.RIGHT_CLICK_MENU_NEW, self.on_right_click_menu_new)

    def display_right_click_menu_for_timeline(self, canvas_x: float, canvas_y: float):
        RIGHT_CLICK_OPTIONS = [
            ("Change timeline name...", RightClickOption.CHANGE_TIMELINE_NAME),
            ("Change timeline height...", RightClickOption.CHANGE_TIMELINE_HEIGHT),
        ]

        post(Post.RIGHT_CLICK_MENU_NEW)
        listen(
            self,
            Post.RIGHT_CLICK_MENU_OPTION_CLICK,
            self.on_right_click_menu_option_click,
        )

        display_right_click_menu(
            self.canvas.winfo_rootx() + int(canvas_x),
            self.canvas.winfo_rooty() + int(canvas_y),
            RIGHT_CLICK_OPTIONS,
        )

        listen(self, Post.RIGHT_CLICK_MENU_NEW, self.on_right_click_menu_new)

    def right_click_menu_change_timeline_height(self) -> None:
        height = dialogs.ask_for_int(
            "Change timeline height",
            "Insert new timeline height",
            initialvalue=self.height,
        )
        if height:
            logger.debug(f"User requested new timeline height of '{height}'")
            self.height = height
            self.collection.after_height_change(self)

        post(Post.REQUEST_RECORD_STATE, Action.TIMELINE_HEIGHT_CHANGE)

    def right_click_menu_change_timeline_name(self) -> None:
        name = dialogs.ask_for_string(
            "Change timeline name", "Insert new timeline name", initialvalue=self.name
        )
        if name:
            logger.debug(f"User requested new timeline name of '{name}'")
            self.name = name

        post(Post.REQUEST_RECORD_STATE, Action.TIMELINE_NAME_CHANGE)

    def on_inspector_window_opened(self):
        for element in self.selected_elements:
            logger.debug(
                f"Notifying inspector of previsously selected elements on {self}..."
            )
            self.post_inspectable_selected_event(element)

    @staticmethod
    def post_inspectable_selected_event(element: Inspectable):
        post(
            Post.INSPECTABLE_ELEMENT_SELECTED,
            type(element),
            element.INSPECTOR_FIELDS,
            element.get_inspector_dict(),
            element.id,
        )

    def update_elements_position(self) -> None:
        self.element_manager.update_elements_postion()

    def delete_selected_elements(self):
        if not self.selected_elements:
            return

        for component in self.selected_components:
            self.timeline.on_request_to_delete_components([component])

            post(Post.REQUEST_DELETE_COMPONENT, component.id)

    def delete_element(self, element: TimelineUIElement):
        if element in self.selected_elements:
            try:
                self.deselect_element(element)
            except KeyError:
                # can't access component, as it is already deleted
                pass

        self.element_manager.delete_element(element)

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
        stop_listening_to_all(self)
        self.canvas.grid_forget()
        if self.toolbar:
            self.toolbar.on_timeline_delete()

    def delete(self):
        logger.info(f"Deleting timeline ui {self}...")

        stop_listening_to_all(self)
        stop_listening_to_all(self.canvas)
        self.canvas.destroy()
        if self.toolbar:
            self.toolbar.on_timeline_delete()

    def __repr__(self):
        return default_str(self)

    def __str__(self):
        return (
            f"{self.name if self.timeline else '<unavailable>'} |"
            f" {self.TIMELINE_KIND.value.capitalize().split('_')[0]} Timeline"
        )


class RightClickOption(Enum):
    ADD_PRE_START = auto()
    ADD_POST_END = auto()
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
    def get_right_click_callback(option) -> Callable[[], None]:
        return lambda: post(Post.RIGHT_CLICK_MENU_OPTION_CLICK, option)

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
                        label=option[0], command=get_right_click_callback(option[1])
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

    post(
        Post.REQUEST_RECORD_STATE,
        Action.ATTRIBUTE_EDIT_VIA_INSPECTOR,
        no_repeat=True,
        repeat_identifier=f"{attr}_{element.id}",
    )


class TimelineUIElementManager:
    """
    Composes a TimelineUI object.
    Is responsible for:
        - Creating timeline elements;
        - Querying timeline ui elements and its attributes (e.g. to know which one
        was clicked);
        - Handling selections and deselections;
        - Deleting timeline elements;
    """

    def __init__(self, element_class: type[TimelineUIElement]):
        self._elements = set()
        self.id_to_element = {}
        self.element_class = element_class

        self._selected_elements = []

    @property
    def has_selected_elements(self):
        return bool(self._selected_elements)

    @property
    def ordered_elements(self):
        return sorted(self._elements, key=lambda e: (e.level, e.start))

    def create_element(
        self,
        id: int,
        timeline_ui: TimelineUI,
        canvas: TimelineCanvas,
    ):
        element = self.element_class.create(id, timeline_ui, canvas)

        self._add_to_elements_set(element)

        return element

    def _add_to_elements_set(self, element: TimelineUIElement) -> None:
        logger.debug(f"Adding element '{element}' to {self}.")
        self._elements.add(element)
        self.id_to_element[element.id] = element

    def _remove_from_elements_set(self, element: TimelineUIElement) -> None:
        logger.debug(f"Removing element '{element}' from {self}.")
        try:
            self._elements.remove(element)
            del self.id_to_element[element.id]
        except ValueError:
            raise ValueError(
                f"Can't remove element '{element}' from {self}: not in self._elements."
            )

    def get_element(self, id: str) -> TimelineUIElement:
        return self.id_to_element[id]

    def get_element_by_attribute(self, attr_name: str, value: Any):
        return self._get_element_from_set_by_attribute(self._elements, attr_name, value)

    def get_elements_by_attribute(self, attr_name: str, value: Any) -> list:
        return self._get_elements_from_set_by_attribute(
            self._elements, attr_name, value
        )

    def get_elements_by_condition(
        self, condition: Callable[[TimelineUIElement], bool]
    ) -> list:
        return [e for e in self._elements if condition(e)]

    def get_element_by_condition(
        self, condition: Callable[[TimelineUIElement], bool]
    ) -> TimelineUIElement | None:
        return next((e for e in self._elements if condition(e)), None)

    def get_existing_values_for_attribute(self, attr_name: str) -> set:
        return set([getattr(cmp, attr_name) for cmp in self._elements])

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

    def select_element(self, element: TimelineUIElement) -> None:
        logger.debug(f"Selecting element '{element}'")
        if element not in self._selected_elements:
            self._add_to_selected_elements_set(element)
            element.on_select()
        else:
            logger.debug(f"Element '{element}' is already selected.")

    def deselect_element(self, element: TimelineUIElement) -> None:
        if element in self._selected_elements:
            logger.debug(f"Deselecting element '{element}'")
            self._remove_from_selected_elements_set(element)
            element.on_deselect()

    def _deselect_if_selected(self, element: TimelineUIElement):
        logger.debug(f"Will deselect {element} if it is selected.")
        if element in self._selected_elements:
            self.deselect_element(element)
        else:
            logger.debug("Element was not selected.")

    def deselect_all_elements(self):
        logger.debug(f"Deselecting all elements of {self}")
        for element in self._selected_elements.copy():
            self.deselect_element(element)

    def _add_to_selected_elements_set(self, element: TimelineUIElement) -> None:
        logger.debug(f"Adding element '{element}' to selected elements {self}.")
        self._selected_elements.append(element)

    def _remove_from_selected_elements_set(self, element: TimelineUIElement) -> None:
        logger.debug(f"Removing element '{element}' from selected elements of {self}.")
        try:
            self._selected_elements.remove(element)
        except ValueError:
            raise ValueError(
                f"Can't remove element '{element}' from selected objects of {self}: not"
                " in self._selected_elements."
            )

    def get_selected_elements(self) -> list[TimelineUIElement]:
        return self._selected_elements

    def delete_element(self, element: TimelineUIElement):
        element.delete()
        self._remove_from_elements_set(element)

    @staticmethod
    def get_canvas_drawings_ids_from_elements(
        elements: list[TimelineUIElement],
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
