from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable
if TYPE_CHECKING:
    from tilia.ui.timelines.common import (
        TimelineComponent,
        TimelineComponentUI,
        TimelineUIElement,
    )
    from tilia.ui.tkinter.tkinterui import TkinterUI
    from tilia.ui.tkinter.timelines.slider import SliderTimelineTkUI

import importlib
import logging
logger = logging.getLogger(__name__)
import tkinter as tk

from tilia import events
from tilia.ui.element_kinds import UIElementKind
from tilia.ui.timelines.common import (
    TimelineUI,
    TimelineUICollection,
    TimelineUIElement,
)
from tilia.events import Subscriber, EventName
from tilia.repr import default_repr
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.common import InvalidComponentKindError, log_object_creation
from tilia.ui.tkinter.modifier_enum import ModifierEnum


@runtime_checkable
class Inspectable(Protocol):
    """Protocol for timeline elements that may be inspected by the inspector window.
    When selected, they must, via an event, pass a dict with the attributes to be displayed."""
    id: int
    INSPECTOR_FIELDS: list[tuple[str, str]]

    def get_inspector_dict(self) -> dict[str:Any]: ...


class TimelineCanvas(tk.Canvas):
    """Interface for the canvas that composes a timeline.
    Is, right now, an actual tk.Canvas. Will hopefully be replaced with a class that redirects
    draw requests to the appropriate coords in a single canvas for all the timelines."""
    DEFAULT_BG = "#FFFFFF"
    LABEL_PAD = 20

    @log_object_creation
    def __init__(
            self,
            parent: tk.Frame,
            scrollbar: tk.Scrollbar,
            width: int,
            left_margin_width: int,
            height: int,
            initial_name: str,
    ):
        super().__init__(
            parent,
            height=height,
            bg=self.DEFAULT_BG,
            highlightthickness=0,
        )

        # TODO what are these?
        bindings = [
            # ("<Configure>", lambda event: self.configure(scrollregion=self.bbox("all")),),
            # ("<MouseWheel>", self.on_mouse_wheel)
        ]

        for binding in bindings:
            self.bind(*binding)

        self._label_width = left_margin_width

        self.label_bg = self.create_rectangle(
            *self._get_label_bg_coords, fill="white", width=0
        )

        self.label_in_canvas = self.create_text(
            self._get_label_coords, anchor="nw", text=initial_name
        )

        self.config(scrollregion=(0, 0, width, height))
        self.config(xscrollcommand=scrollbar.set)
        self.focus_set()

        self._setup_cursors()

    TAG_TO_CURSOR = [("arrowsCursor", "sb_h_double_arrow"), ("handCursor", "hand2")]

    def _setup_cursors(self):
        for tag, cursor_name in self.TAG_TO_CURSOR:
            self.tag_bind(
                tag, "<Enter>", lambda x, name=cursor_name: self.config(cursor=name)
            )
            self.tag_bind(tag, "<Leave>", lambda x: self.config(cursor=""))

    @property
    def _get_label_coords(self):
        return self.LABEL_PAD, self.winfo_reqheight() / 2

    @property
    def _get_label_bg_coords(self):
        return 0, 0, self._label_width, self.winfo_reqheight()


class TkTimelineUICollection(Subscriber, TimelineUICollection):
    """
    Collection of timeline uis. Responsible for:
        - Creating timeline uis;
        - Redirecting events (e.g. clicks, drags, button presses) from the TKEventHandler to the appropriate TimelineUI instance;
        - Handling queries for timeline uis;
        - Gridding timeline ui's canvases on the timeline frame;
        - Getting 'global' information (e.g. margins and timeline size) for timeline uis.

    """
    SUBSCRIPTIONS = [
        EventName.CANVAS_LEFT_CLICK,
        EventName.KEY_PRESS_DELETE,
        EventName.DEBUG_SELECTED_ELEMENTS
    ]

    def __init__(
            self,
            app_ui: TkinterUI,
            frame: tk.Frame,
            scrollbar: tk.Scrollbar,
            toolbar_frame: tk.Frame,
    ):
        super().__init__(subscriptions=self.SUBSCRIPTIONS)
        self._app_ui = app_ui
        self.frame = frame
        self.toolbar_frame = toolbar_frame
        self._toolbars = set()

        self.scrollbar = scrollbar
        # self.scrollbar.config(command=self.scroll_x) # TODO fix this config
        self.scrollbar.pack(fill="x", expand=True)

        self.timeline_uis = set()
        self.select_order = []

    @property
    def left_margin_x(self):

        return self._app_ui.timeline_padx

    @property
    def right_margin_x(self):

        return self._app_ui.timeline_padx + self._app_ui.timeline_width

    @property
    def timeline_width(self):
        return self._app_ui.timeline_width

    def create_timeline_ui(self, kind: TimelineKind, name: str) -> TimelineUI:
        timeline_class = self.get_timeline_ui_class_from_kind(kind)

        canvas = self.create_timeline_canvas(name, timeline_class.DEFAULT_HEIGHT)

        toolbar = self.get_toolbar_for_timeline_ui(
            timeline_class.TOOLBAR_CLASS
        )

        element_manager = TimelineUIElementManager(
            timeline_class.ELEMENT_KINDS_TO_ELEMENT_CLASSES
        )

        tl_ui = timeline_class(
            timeline_ui_collection=self,
            element_manager=element_manager,
            canvas=canvas,
            toolbar=toolbar,
            name=name,
        )

        self.grid_canvas(tl_ui.canvas, self._get_last_grid_row_number())

        self._add_to_timeline_uis_set(tl_ui)

        return tl_ui

    def delete_timeline_ui(self, timeline: TimelineTkUI):
        timeline.delete()
        self._remove_from_timeline_uis_set(timeline)

    def _add_to_timeline_uis_set(self, timeline_ui: TimelineTkUI) -> None:
        logger.debug(f"Adding timeline ui '{timeline_ui}' to {self}.")
        self.timeline_uis.add(timeline_ui)

    def _remove_from_timeline_uis_set(self, timeline_ui: TimelineTkUI) -> None:
        logger.debug(f"Removing timeline ui '{timeline_ui}' to {self}.")
        try:
            self.timeline_uis.remove(timeline_ui)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline ui '{timeline_ui}' from {self}: not in self.timeline_uis."
            )

    def _get_last_grid_row_number(self):
        return len([tlui for tlui in self.timeline_uis if tlui.visible])

    def grid_canvas(self, canvas: tk.Canvas, row_number: int) -> None:
        canvas.grid(row=row_number, column=0, sticky="ew")
        self.frame.grid_columnconfigure(
            0,
            weight=1
        )  # needed so scrollregion is right. Don't know why.
        # Do we need to do this every time a timeline is created?
        self.frame.update()  # TODO check if this is necessary

    @staticmethod
    def get_timeline_ui_class_from_kind(kind: TimelineKind) -> type(TimelineTkUI):
        from tilia.ui.tkinter.timelines.hierarchy import HierarchyTimelineTkUI
        from tilia.ui.tkinter.timelines.slider import SliderTimelineTkUI

        kind_to_class_dict = {
            TimelineKind.HIERARCHY_TIMELINE: HierarchyTimelineTkUI,
            TimelineKind.SLIDER_TIMELINE: SliderTimelineTkUI
        }

        class_ = kind_to_class_dict[kind]

        return class_

    # noinspection PyUnresolvedReferences
    def create_hierarchy_timeline_ui(self, name: str) -> HierarchyTimelineTkUI:

        logger.debug("Importing module for creating hierarchy timeline Tkinter UI...")
        hierarchytl_module = importlib.import_module(
            "tilia.ui.tkinter.timelines.hierarchy"
        )
        logger.debug(f"Got module {hierarchytl_module}.")

        canvas = self.create_timeline_canvas(name, hierarchytl_module.HierarchyTimelineTkUI.DEFAULT_HEIGHT)

        toolbar = self.get_toolbar_for_timeline_ui(
            hierarchytl_module.HierarchyTimelineToolbar
        )

        element_manager = TimelineUIElementManager(
            hierarchytl_module.HierarchyTimelineTkUI.ELEMENT_KINDS_TO_ELEMENT_CLASSES
        )

        return hierarchytl_module.HierarchyTimelineTkUI(
            timeline_ui_collection=self,
            element_manager=element_manager,
            canvas=canvas,
            toolbar=toolbar,
            name=name,
        )

    def create_slider_timeline_ui(self) -> SliderTimelineTkUI:
        logger.debug("Importing module for creating slider timeline Tkinter UI...")
        slidertl_module = importlib.import_module(
            "tilia.ui.tkinter.timelines.slider"
        )
        logger.debug(f"Got module {slidertl_module}.")

    def create_timeline_canvas(self, name: str, starting_height: int):
        return TimelineCanvas(
            self.frame,
            self.scrollbar,
            self.get_tlcanvas_width(),
            self._app_ui.timeline_padx,
            starting_height,
            name,
        )

    @property
    def _toolbar_types(self):
        return {type(toolbar) for toolbar in self._toolbars}

    def get_toolbar_for_timeline_ui(
            self, toolbar_type: type(TimelineToolbar)
    ) -> TimelineToolbar | None:

        if not toolbar_type:
            logger.debug(f"Timeline kind has no toolbar.")
            return

        logger.debug(f"Getting toolbar of type '{toolbar_type}'")

        if toolbar_type in self._toolbar_types:
            logger.debug(f"Found previous toolbar of same type.")
            return self._get_toolbar_from_toolbars_by_type(toolbar_type)
        else:
            logger.debug(f"No previous toolbar of same type, creating new toolbar.")
            new_toolbar = toolbar_type(self.toolbar_frame)
            return new_toolbar

    def _get_toolbar_from_toolbars_by_type(self, type_: type(TimelineToolbar)):
        return next(
            iter(toolbar for toolbar in self._toolbars if type(toolbar) == type_)
        )

    def get_tlcanvas_width(self) -> int:
        return self._app_ui.timeline_total_size

    def _get_timeline_ui_by_canvas(self, canvas):
        return next((tlui for tlui in self.timeline_uis if tlui.canvas == canvas), None)

    def _get_toolbar_by_type(self, canvas):
        return next(
            (toolbar for toolbar in self._toolbars if toolbar.canvas == canvas), None
        )

    def on_subscribed_event(self, event_name: str, *args: tuple, **kwargs: dict) -> None:
        if event_name == EventName.CANVAS_LEFT_CLICK:
            self._on_click(*args, **kwargs)
        elif event_name == EventName.KEY_PRESS_DELETE:
            self._on_delete_press()
        elif event_name == EventName.DEBUG_SELECTED_ELEMENTS:
            self._on_debug_selected_elements()

    def _on_click(
            self,
            canvas: tk.Canvas,
            x: int,
            y: int,
            clicked_item_id: int,
            modifier: ModifierEnum,
    ) -> None:

        clicked_timeline_ui = self._get_timeline_ui_by_canvas(canvas)

        if clicked_timeline_ui:
            logger.debug(
                f"Notifying timeline ui '{clicked_timeline_ui}' about left click."
            )
            clicked_timeline_ui.on_click(x, y, clicked_item_id, modifier=modifier)
        else:
            raise ValueError(
                f"Can't process left click: no timeline with canvas '{canvas}' on {self}"
            )

    def _on_delete_press(self):
        for timeline_ui in self.timeline_uis:
            timeline_ui.on_delete_press()

    def _on_debug_selected_elements(self):
        for timeline_ui in self.timeline_uis:
            timeline_ui.debug_selected_elements()

    def get_id(self) -> int:
        return self._app_ui.get_id()

    def get_media_length(self):
        return self._app_ui.get_media_length()

    def get_timeline_width(self):
        return self._app_ui.timeline_width


class TimelineTkUIElement(TimelineUIElement, ABC):
    """Interface for the tkinter ui objects corresponding to to a TimelineComponent instance.
    E.g.: the HierarchyTkUI in the ui element corresponding to the Hierarchy timeline component."""
    def __init__(
            self,
            *args,
            tl_component: TimelineComponent,
            timeline_ui: TimelineUI,
            canvas: tk.Canvas,
            **kwargs,
    ):
        super().__init__(
            *args, tl_component=tl_component, timeline_ui=timeline_ui, **kwargs
        )

        self.canvas = canvas

    @abstractmethod
    def delete(self): ...


class TimelineUIElementManager:
    """
    Composes a TimelineUI object.
    Is responsible for:
        - Creating timeline elements;
        - Querying timeline ui elements and its attributes (e.g. to know which one was clicked);
        - Handling selections and deselections;
        - Deleting timeline elements;
    """

    @log_object_creation
    def __init__(self, element_kinds_to_classes: dict[UIElementKind: type(TimelineTkUIElement)]):

        self._elements = set()
        self._element_kinds_to_classes = element_kinds_to_classes

        self._selected_elements = []

    @property
    def element_kinds(self):
        return [kind for kind, _ in self._element_kinds_to_classes.items()]

    def create_element(
            self,
            kind: UIElementKind,
            component: TimelineComponent,
            timeline_ui: TimelineTkUI,
            canvas: TimelineCanvas,
            *args,
            **kwargs,
    ):
        self._validate_element_kind(kind)
        element_class = self._get_element_class_by_kind(kind)
        element = element_class.create(component, timeline_ui, canvas, *args, **kwargs)

        self._add_to_elements_set(element)

        return element

    def _add_to_elements_set(self, element: TimelineUIElement) -> None:
        logger.debug(f"Adding element '{element}' to {self}.")
        self._elements.add(element)

    def _remove_from_elements_set(self, element: TimelineUIElement) -> None:
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
            self, condition: Callable[[TimelineUIElement], bool], kind: UIElementKind
    ) -> list:
        element_set = self._get_element_set_by_kind(kind)
        return [e for e in element_set if condition(e)]

    def get_element_by_condition(
            self, condition: Callable[[TimelineUIElement], bool], kind: UIElementKind
    ) -> TimelineComponentUI:
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
    ) -> type(TimelineUIElement):
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

    def select_element(self, element: Any) -> None:
        logger.debug(f"Selecting element '{element}'")
        if element not in self._selected_elements:
            self._add_to_selected_elements_set(element)
            element.on_select()
        else:
            logger.debug(f"Element '{element}' is already selected.")

    def deselect_element(self, element: Any) -> None:
        logger.debug(f"Deselecting element '{element}'")
        if element in self._selected_elements:
            self._remove_from_selected_elements_set(element)
            element.on_deselect()
        else:
            logger.debug(f"Element '{element}' is already deselected.")

    def _deselect_if_selected(self, element):
        logger.debug(f"Will deselect {element} if it is selected.")
        if element in self._selected_elements:
            self.deselect_element(element)
        else:
            logger.debug(f"Element was not selected.")

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
                f"Can't remove element '{element}' from selected objects of {self}: not in self._selected_elements."
            )

    def get_selected_elements(self) -> list[TimelineTkUIElement]:
        return self._selected_elements

    def delete_element(self, element: TimelineTkUIElement):
        self._deselect_if_selected(element)
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

    @staticmethod
    def get_lowest_element_from_id_list(ids: list, canvas: tk.Canvas) -> int:
        ids_in_order = [id_ for id_ in canvas.find_all() if id_ in ids]
        return ids_in_order[0]

    def __repr__(self):
        return default_repr(self)

    def get_all_elements(self):
        return self._elements


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
    Interface for objects that respond to left-clicks (independent of selection).
    Used, for instance, to trigger dragging of a hierarchy ui boundary marker.
    Left clickable must 'left_cilck_trigger', a list of the canvas drawing ids
    that count for triggering its on_left_click method.
    """
    left_click_triggers: tuple[int, ...]

    def on_left_click(self, clicked_item_id: int) -> None:
        ...


class TimelineTkUI(TimelineUI, ABC):
    """
    Interface for the ui of a Timeline object.
    Is composed of:
        - a tk.Canvas;
        - a TimelineToolbar (which is shared between other uis of the same class);
        - a TimelineUiElementManager;

    Keeps a reference to the main TimelineUICollection object.

    Is responsible for processing tkinter events send to the timeline via TimelineUICollection.

    """


    def __init__(
            self,
            *args,
            timeline_ui_collection: TkTimelineUICollection,
            timeline_ui_element_manager: TimelineUIElementManager,
            component_kinds_to_classes: dict[UIElementKind: type(TimelineTkUIElement)],
            component_kinds_to_ui_element_kinds: dict[ComponentKind: UIElementKind],
            canvas: TimelineCanvas,
            toolbar: TimelineToolbar,
            name: str,
            height: int,
            is_visible: bool,
            **kwargs,
    ):
        super().__init__(
            *args,
            timeline_ui_collection=timeline_ui_collection,
            height=height,
            is_visible=is_visible,
            name=name,
            **kwargs,
        )
        self.component_kinds_to_ui_element_kinds = component_kinds_to_ui_element_kinds
        self.element_manager = timeline_ui_element_manager
        self.component_kinds_to_classes = component_kinds_to_classes
        self.canvas = canvas
        self.toolbar = toolbar

    def get_ui_for_component(self, component_kind: ComponentKind, component: TimelineComponent, **kwargs):
        return self.element_manager.create_element(
            self.component_kinds_to_ui_element_kinds[component_kind], component, self, self.canvas, **kwargs
        )

    def on_click(
            self, x: int, y: int, clicked_item_id: int, modifier: ModifierEnum
    ) -> None:
        """Redirects self._process_element_click using the appropriate ui element. Note that, in the
        case of shared canvas drawings (as in HierarchyTkUI markers), it
        will call the method more than once."""

        logger.debug(f"Processing click on {self}...")
        if modifier == ModifierEnum.NONE:
            self.deselect_all_elements()

        if not clicked_item_id:
            logger.debug(f"No canvas item was clicked.")
        else:
            self._process_canvas_item_click(x, y, clicked_item_id, modifier)

        logger.debug(f"Processed click on {self}.")

    def _process_canvas_item_click(
            self, x: int, y: int, clicked_item_id: int, modifier: ModifierEnum
    ) -> None:

        owes_clicked_item = lambda e: clicked_item_id in e.canvas_drawings_ids

        clicked_elements = self.element_manager.get_elements_by_condition(
            owes_clicked_item, kind=UIElementKind.ANY
        )

        if not clicked_elements:
            logger.debug(f"No ui element was clicked.")
            return

        for clicked_element in clicked_elements:
            self._process_ui_element_click(clicked_element, clicked_item_id)

    def _process_ui_element_click(
            self, clicked_element: TimelineComponentUI, clicked_item_id: int
    ) -> None:

        logger.debug(f"Processing click on ui element '{clicked_element}'...")

        if (
                isinstance(clicked_element, Selectable)
                and clicked_item_id in clicked_element.selection_triggers
        ):
            self._select_element(clicked_element)
        else:
            logger.debug(f"Element is not selectable.")

        if (
                isinstance(clicked_element, LeftClickable)
                and clicked_item_id in clicked_element.left_click_triggers
        ):
            clicked_element.on_left_click(clicked_item_id)
        else:
            logger.debug(f"Element is not left clickable.")

        logger.debug(f"Processed click on ui element '{clicked_element}'.")

    def _select_element(self, element: Selectable):

        self.element_manager.select_element(element)

        if isinstance(element, Inspectable):
            logger.debug(f"Element is inspectable. Sending data to inspector.")
            self.post_inspectable_selected_event(element)


            events.subscribe(EventName.INSPECTOR_FIELD_EDITED, element)


    def post_inspectable_selected_event(self, element: Selectable):
        events.post(
            EventName.INSPECTABLE_ELEMENT_SELECTED,
            type(element),
            element.INSPECTOR_FIELDS,
            element.get_inspector_dict(),
            element.id,
        )

    def on_delete_press(self):
        selected_elements = self.element_manager.get_selected_elements()
        for element in selected_elements.copy():
            self.timeline.on_request_delete_component(element.tl_component)

    def delete_element(self, element: TimelineTkUIElement):
        self.element_manager.delete_element(element)

    def debug_selected_elements(self):
        selected_elements = self.element_manager.get_selected_elements()
        print(f"========== {self} ==========")
        for element in selected_elements.copy():
            from pprint import pprint

            print(f"----- {element} -----")
            print("--- UIElement attributes ---")
            pprint(element.__dict__)
            print("--- Component attributes ---")
            pprint(element.tl_component.__dict__)

    # noinspection PyUnresolvedReferences
    def get_x_by_time(self, time: float) -> int:

        return (
                       (time / self.timeline_ui_collection.get_media_length())
                       * self.get_timeline_width()
               ) + self.get_left_margin_x()

    # noinspection PyUnresolvedReferences
    def get_time_by_x(self, x: int) -> float:
        return (
                (x - self.get_left_margin_x())
                * self.timeline_ui_collection.get_media_length()
                / self.timeline_ui_collection.get_timeline_width()
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

    def deselect_all_elements(self):
        for element in self.element_manager.get_all_elements():
            if isinstance(element, Inspectable):
                events.post(EventName.INSPECTABLE_ELEMENT_DESELECTED, element.id)

            self.element_manager.deselect_element(element)

    def get_id_for_element(self):
        return self.timeline_ui_collection.get_id()

    def delete(self):
        logger.info(f"Deleting timeline ui {self}...")

        if isinstance(self, Subscriber):
            self.unsubscribe_from_all()

        self.canvas.destroy()
        if self.toolbar:
            self.toolbar.on_timeline_delete()

    def __repr__(self):
        return default_repr(self)


class TimelineToolbar(tk.LabelFrame):
    """
    Toolbar that enables users to edit TimelineComponents.
    Keeps track of how maby timeilnes of a certain kind are instanced and hides itself
    in case there are none.
    There must be only one instance of a toolbar of a certain kind at any given moment.
    """

    PACK_ARGS = {"side": "left"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.button_info = None
        self.visible = False
        self._visible_timelines_count = 0

    def create_buttons(self):
        if self.button_info:
            for info in self.button_info:
                file_name, callback, tooltip_text = info[:3]

                # sets attribute with same name as image
                setattr(
                    self,
                    file_name,
                    tk.PhotoImage(file=os.path.join("ui", "img", f"{file_name}.png")),
                )

                # create and pack a button with img as image and command = f'on_{img}'
                button = tk.Button(
                    self,
                    image=getattr(self, file_name),
                    borderwidth=0,
                    command=callback,
                )

                button.pack(side=tk.LEFT, padx=6)
                CreateToolTip(button, tooltip_text)

                # if attribute name is provided, set button as toolbar attribute to allow future modification.
                try:
                    setattr(self, info[3] + "_button", button)
                except IndexError:
                    pass
        else:
            raise ValueError(f"No button info found for {self}")

    def _increment_decrement_timelines_count(self, increment: bool) -> None:
        """Increments timelines count if 'increment' is True,
        decrements timelines count if 'increment' is False.

        Raises ValueError if final count is negative."""
        if increment:
            logging.debug(f"Incremeting visible timelines count...")
            self._visible_timelines_count += 1
        else:
            logging.debug(f"Decrementing visible timelines count...")
            self._visible_timelines_count -= 1

        if self._visible_timelines_count < 0:
            raise ValueError(
                f"Visible timeline count of {self} decremented below zero."
            )

        logging.debug(
            f"New is_visible timeline count is {self._visible_timelines_count}"
        )

    def process_visiblity_change(self, visible: bool):
        """increments or decrements is_visible timeline count accordingly.
        Hides toolbar if final count > 1, displays toolbar if count = 0"""
        self._increment_decrement_timelines_count(visible)
        self._show_display_according_to_visible_timelines_count()

    def _show_display_according_to_visible_timelines_count(self):
        if self._visible_timelines_count > 0 and not self.visible:
            logging.debug(f"Displaying toolbar.")
            self.visible = True
            self.pack(**self.PACK_ARGS)
        elif self._visible_timelines_count == 0 and self.visible:
            logging.debug(f"Hiding toolbar.")
            self.visible = False
            self.pack_forget()

    def on_timeline_delete(self):
        """Decrements visible count and hides timelines if count reaches zero."""
        self._increment_decrement_timelines_count(False)
        self._show_display_according_to_visible_timelines_count()


class ToolTip(object):
    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0

    def showtip(self, text):
        """Display text in tooltip window"""

        self.text = text
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + self.widget.winfo_width() - 5
        y = y + cy + self.widget.winfo_rooty() + self.widget.winfo_height() - 5

        self.tipwindow = tw = tk.Toplevel(self.widget)

        tw.wm_overrideredirect(1)
        tw.wm_geometry("+%d+%d" % (x, y))
        self.label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("tahoma", "8", "normal"),
        )
        self.label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

    def change_tip_text(self, new_text: str) -> None:
        self.label.config(text=new_text)


def CreateToolTip(widget, text):
    toolTip = ToolTip(widget)

    def enter(event):
        toolTip.showtip(text)

    def leave(event):
        toolTip.hidetip()

    widget.bind("<Enter>", enter)
    widget.bind("<Leave>", leave)
