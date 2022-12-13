from __future__ import annotations

import os
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable

from tilia.timelines.state_actions import StateAction
from tilia.ui.tkinter.timelines.copy_paste import CopyError, PasteError
from tilia.ui.tkinter.windows import WindowKind

if TYPE_CHECKING:
    from tilia.ui.timelines.common import (
        TimelineComponent,
        TimelineComponentUI,
        TimelineUIElement,
    )
    from tilia.ui.tkinter.tkinterui import TkinterUI
    from tilia.ui.tkinter.timelines.slider import SliderTimelineTkUI

import logging

logger = logging.getLogger(__name__)
import tkinter as tk
import tkinter.messagebox

from tilia import events, settings
from tilia.ui.element_kinds import UIElementKind
from tilia.ui.timelines.common import (
    TimelineUI,
    TimelineUICollection,
    TimelineUIElement,
)
from tilia.events import Event, subscribe, unsubscribe, unsubscribe_from_all
from tilia.repr import default_repr
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.common import InvalidComponentKindError, log_object_creation, Timeline
from tilia.ui.tkinter.modifier_enum import ModifierEnum
from tilia.misc_enums import InOrOut, UpOrDown, Side
from tilia.ui.tkinter.timelines.copy_paste import get_copy_data_from_elements, paste_into_element, CopyAttributes, \
    Copyable


@runtime_checkable
class Inspectable(Protocol):
    """Protocol for timeline elements that may be inspected by the inspector window.
    When selected, they must, via an event, pass a dict with the attributes to be displayed."""

    id: int
    INSPECTOR_FIELDS: list[tuple[str, str]]

    def get_inspector_dict(self) -> dict[str:Any]:
        ...


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

        self._label_width = left_margin_width

        self._setup_label(initial_name)

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

    def _setup_label(self, initial_name: str):
        self.label_bg = self.create_rectangle(
            *self._get_label_bg_coords, fill="white", width=0
        )

        self.label_in_canvas = self.create_text(
            self._get_label_coords, anchor="nw", text=initial_name
        )

    def update_label(self, new_name: str):
        self.itemconfig(self.label_in_canvas, text=new_name)

    def update_height(self, new_height: int):
        self.config(height=new_height)

    @property
    def _get_label_coords(self):
        return self.LABEL_PAD, self.winfo_reqheight() / 2

    @property
    def _get_label_bg_coords(self):
        return 0, 0, self._label_width, self.winfo_reqheight()


class TkTimelineUICollection(TimelineUICollection):
    """
    Collection of timeline uis. Responsible for:
        - Creating timeline uis;
        - Redirecting events (e.g. clicks, drags, button presses) from the TKEventHandler to the appropriate TimelineUI instance;
        - Handling queries for timeline uis;
        - Gridding timeline ui's canvases on the timeline frame;
        - Getting 'global' information (e.g. margins and timeline size) for timeline uis.
    """

    ZOOM_SCALE_FACTOR = 0.1

    def __init__(
            self,
            app_ui: TkinterUI,
            frame: tk.Frame,
            scrollbar: tk.Scrollbar,
            toolbar_frame: tk.Frame
    ):

        subscribe(self, Event.CANVAS_LEFT_CLICK, self._on_timeline_ui_left_click)
        subscribe(self, Event.CANVAS_RIGHT_CLICK, self._on_timeline_ui_right_click)
        subscribe(self, Event.KEY_PRESS_DELETE, self._on_delete_press)
        subscribe(self, Event.KEY_PRESS_ENTER, self._on_enter_press)
        subscribe(self, Event.KEY_PRESS_LEFT, lambda: self._on_side_arrow_press(Side.LEFT))
        subscribe(self, Event.KEY_PRESS_RIGHT, lambda: self._on_side_arrow_press(Side.RIGHT))
        subscribe(self, Event.KEY_PRESS_CONTROL_C, self._on_request_to_copy)
        subscribe(self, Event.KEY_PRESS_CONTROL_V, self._on_request_to_paste)
        subscribe(self, Event.KEY_PRESS_CONTROL_SHIFT_V, self._on_request_to_paste_with_children)
        subscribe(self, Event.DEBUG_SELECTED_ELEMENTS, self._on_debug_selected_elements)
        subscribe(self, Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_SPLIT, self._on_hierarchy_timeline_split_button)
        subscribe(self, Event.REQUEST_ZOOM_IN, lambda *args: self.zoomer(InOrOut.IN, *args))
        subscribe(self, Event.REQUEST_ZOOM_OUT, lambda *args: self.zoomer(InOrOut.OUT, *args))
        subscribe(self, Event.REQUEST_CHANGE_TIMELINE_WIDTH, self.on_request_change_timeline_width)
        subscribe(self, Event.TIMELINES_REQUEST_MOVE_DOWN_IN_DISPLAY_ORDER,
                  lambda *args: self._move_in_display_order(*args,
                                                            UpOrDown.DOWN))
        subscribe(self, Event.TIMELINES_REQUEST_MOVE_UP_IN_DISPLAY_ORDER,
                  lambda *args: self._move_in_display_order(*args,
                                                            UpOrDown.UP))
        subscribe(self, Event.TIMELINES_REQUEST_TO_DELETE_TIMELINE, self._on_request_to_delete_timeline)
        subscribe(self, Event.TIMELINES_REQUEST_TO_CLEAR_TIMELINE, lambda: 1 / 0)
        subscribe(self, Event.TIMELINES_REQUEST_TO_SHOW_TIMELINE, self.on_request_to_show_timeline)
        subscribe(self, Event.TIMELINES_REQUEST_TO_HIDE_TIMELINE, self.on_request_to_hide_timeline)
        subscribe(self, Event.PLAYER_MEDIA_TIME_CHANGE, self.on_media_time_change)
        subscribe(self, Event.SLIDER_DRAG_START, lambda: self.on_slider_drag(True))
        subscribe(self, Event.SLIDER_DRAG_END, lambda: self.on_slider_drag(False))
        subscribe(self, Event.HIERARCHY_TIMELINE_UI_CREATED_INITIAL_HIERARCHY, self.on_create_initial_hierarchy)
        subscribe(self, Event.REQUEST_FOCUS_TIMELINES, self.on_request_to_focus_timelines)

        self._app_ui = app_ui
        self.frame = frame
        self.toolbar_frame = toolbar_frame
        self._toolbars = set()

        self.scrollbar = scrollbar
        self.scrollbar.config(command=self.on_scrollbar_move)
        self.scrollbar.pack(fill="x", expand=True)
        self.slider_is_being_dragged = False

        self._timeline_uis = set()
        self._select_order = []
        self._display_order = []
        self._timeline_uis_to_playback_line_ids = {}

        self.create_playback_lines()

        self._timeline_collection = None  # will be set by the TiLiA object

    def __str__(self) -> str:
        return self.__class__.__name__ + '-' + str(id(self))

    def on_scrollbar_move(self, *args):
        for timeline in self._timeline_uis:
            timeline.canvas.xview(*args)

    @property
    def left_margin_x(self):
        return self._app_ui.timeline_padx

    @property
    def right_margin_x(self):
        return self._app_ui.timeline_padx + self._app_ui.timeline_width

    @property
    def timeline_width(self):
        return self._app_ui.timeline_width

    @timeline_width.setter
    def timeline_width(self, value):
        logger.debug(f"Changing to timeline widht to {value}.")
        self._app_ui.timeline_width = value

    def create_timeline_ui(self, kind: TimelineKind, name: str) -> TimelineTkUI:
        timeline_class = self.get_timeline_ui_class_from_kind(kind)

        canvas = self.create_timeline_canvas(name, timeline_class.DEFAULT_HEIGHT)

        toolbar = self.get_toolbar_for_timeline_ui(timeline_class.TOOLBAR_CLASS)

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

        if toolbar:
            toolbar.on_timeline_create()

        self.grid_timeline_ui_canvas(tl_ui.canvas, self._get_last_grid_row_number())

        self._add_to_timeline_uis_set(tl_ui)
        self._add_to_timeline_ui_select_order(tl_ui)
        self._add_to_timeline_ui_display_order(tl_ui)

        if not kind == TimelineKind.SLIDER_TIMELINE:
            self.create_playback_line(tl_ui)

        return tl_ui

    def delete_timeline_ui(self, timeline_ui: TimelineTkUI):
        """Deletes given timeline ui. To be called by TimelineCollection
        after a Timeline has been deleted"""
        timeline_ui.delete()
        self._remove_from_timeline_uis_set(timeline_ui)
        self._remove_from_timeline_ui_select_order(timeline_ui)
        self._remove_from_timeline_ui_display_order(timeline_ui)
        if timeline_ui.toolbar:
            self._delete_timeline_ui_toolbar_if_necessary(timeline_ui)

    def _add_to_timeline_uis_set(self, timeline_ui: TimelineTkUI) -> None:
        logger.debug(f"Adding timeline ui '{timeline_ui}' to {self}.")
        self._timeline_uis.add(timeline_ui)

    def _remove_from_timeline_uis_set(self, timeline_ui: TimelineTkUI) -> None:
        logger.debug(f"Removing timeline ui '{timeline_ui}' to {self}.")
        try:
            self._timeline_uis.remove(timeline_ui)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline ui '{timeline_ui}' from {self}: not in self.timeline_uis."
            )

    def _add_to_timeline_ui_select_order(self, tl_ui: TimelineTkUI) -> None:
        logger.debug(f"Inserting timeline into {self} select order.")
        self._select_order.insert(0, tl_ui)

    def _remove_from_timeline_ui_select_order(self, tl_ui: TimelineTkUI) -> None:
        logger.debug(f"Removing timeline from {self} select order.")
        try:
            self._select_order.remove(tl_ui)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline ui '{tl_ui}' from select order: not in select order."
            )

    def _add_to_timeline_ui_display_order(self, tl_ui: TimelineTkUI) -> None:
        logger.debug(f"Inserting timeline into {self} display order.")
        self._display_order.append(tl_ui)

    def _remove_from_timeline_ui_display_order(self, tl_ui: TimelineTkUI) -> None:
        logger.debug(f"Removing timeline from {self} display order.")
        try:
            self._display_order.remove(tl_ui)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline ui '{tl_ui}' from display order: not in select order."
            )

    def _move_in_display_order(self, tl_ui_id: int, direction: UpOrDown):
        tl_ui = self.get_timeline_ui_by_id(tl_ui_id)
        logger.debug(f"Moving {tl_ui} {direction.value} in display order.")
        logger.debug(f"Current display order is {self._display_order}.")

        prev_display_index = self._display_order.index(tl_ui)
        if tl_ui.is_visible:
            tl_ui.canvas.grid_forget()
            tl_ui.canvas.grid(row=prev_display_index - direction.value, column=0, sticky="ew")

        tl_ui_to_swap = self._display_order[prev_display_index - direction.value]
        logger.debug(f"Swaping with timeline {tl_ui_to_swap}")

        if tl_ui_to_swap.is_visible:
            tl_ui_to_swap.canvas.grid_forget()
            tl_ui_to_swap.canvas.grid(row=prev_display_index, column=0, sticky="ew")

        (
            self._display_order[prev_display_index],
            self._display_order[prev_display_index - direction.value]
        ) = (
            self._display_order[prev_display_index - direction.value],
            self._display_order[prev_display_index]
        )

        logger.debug(f"New display order is {self._display_order}.")

    def get_timeline_display_position(self, tl_ui: TimelineTkUI):
        return self._display_order.index(tl_ui)

    def _send_to_top_of_select_order(self, tl_ui: TimelineTkUI):
        """
        Sends given timeline to top of selecting order.
        Ui commands (e.g. button clicks) are send to topmost timeline
         of the appropriate type on the select order.
        """

        # TODO give user some visual feedback as to what timeline ui is currently selected
        logger.debug(f"Sending {tl_ui} to top of select order.")
        self._select_order.remove(tl_ui)
        self._select_order.insert(0, tl_ui)

    def _get_last_grid_row_number(self):
        return len(self._display_order)

    @staticmethod
    def grid_timeline_ui_canvas(canvas: tk.Canvas, row_number: int) -> None:
        logger.debug(f"Griding canvas at row '{row_number}'")
        canvas.grid(row=row_number, column=0, sticky="ew")

    @staticmethod
    def hide_timeline_ui(timeline_ui: TimelineTkUI):

        timeline_ui.canvas.grid_forget()
        timeline_ui.is_visible = False

        if timeline_ui.toolbar:
            timeline_ui.toolbar.process_visiblity_change(False)

    def show_timeline_ui(self, timeline_ui: TimelineTkUI):

        timeline_ui.canvas.grid(row=self.get_timeline_display_position(timeline_ui), column=0, sticky='ew')
        timeline_ui.is_visible = True

        if timeline_ui.toolbar:
            timeline_ui.toolbar.process_visiblity_change(True)

    @staticmethod
    def get_timeline_ui_class_from_kind(kind: TimelineKind) -> type(TimelineTkUI):
        from tilia.ui.tkinter.timelines.hierarchy import HierarchyTimelineTkUI
        from tilia.ui.tkinter.timelines.slider import SliderTimelineTkUI

        kind_to_class_dict = {
            TimelineKind.HIERARCHY_TIMELINE: HierarchyTimelineTkUI,
            TimelineKind.SLIDER_TIMELINE: SliderTimelineTkUI,
        }

        class_ = kind_to_class_dict[kind]

        return class_

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
            self._toolbars.add(new_toolbar)

            return new_toolbar

    def _get_toolbar_from_toolbars_by_type(self, type_: type(TimelineToolbar)):
        return next(
            iter(toolbar for toolbar in self._toolbars if type(toolbar) == type_)
        )

    def get_tlcanvas_width(self) -> int:
        return self._app_ui.timeline_total_size

    def _get_timeline_ui_by_canvas(self, canvas):
        return next(
            (tlui for tlui in self._timeline_uis if tlui.canvas == canvas), None
        )

    def _get_toolbar_by_type(self, canvas):
        return next(
            (toolbar for toolbar in self._toolbars if toolbar.canvas == canvas), None
        )

    def _on_timeline_ui_right_click(
            self,
            canvas: tk.Canvas,
            x: int,
            y: int,
            clicked_item_id: int,
            modifier: ModifierEnum,
            double: bool
    ) -> None:

        clicked_timeline_ui = self._get_timeline_ui_by_canvas(canvas)

        if clicked_timeline_ui:
            logger.debug(
                f"Notifying timeline ui '{clicked_timeline_ui}' about right click."
            )
            clicked_timeline_ui.on_click(x, y, clicked_item_id, button=Side.RIGHT, modifier=modifier, double=double)
        else:
            raise ValueError(
                f"Can't process left click: no timeline with canvas '{canvas}' on {self}"
            )

    def _on_timeline_ui_left_click(
            self,
            canvas: tk.Canvas,
            x: int,
            y: int,
            clicked_item_id: int,
            modifier: ModifierEnum,
            double: bool
    ) -> None:

        clicked_timeline_ui = self._get_timeline_ui_by_canvas(canvas)

        if modifier == ModifierEnum.NONE:
            self.deselect_all_elements_in_timeline_uis()

        if clicked_timeline_ui:
            self._send_to_top_of_select_order(clicked_timeline_ui)
            logger.debug(
                f"Notifying timeline ui '{clicked_timeline_ui}' about left click."
            )
            clicked_timeline_ui.on_click(x, y, clicked_item_id, button=Side.LEFT, modifier=modifier, double=double)
        else:
            raise ValueError(
                f"Can't process left click: no timeline with canvas '{canvas}' on {self}"
            )

    def _on_delete_press(self):
        for timeline_ui in self._timeline_uis:
            timeline_ui.on_delete_press()

    def _on_enter_press(self):
        if any([tlui.has_selected_elements for tlui in self._timeline_uis]):
            events.post(Event.UI_REQUEST_WINDOW_INSPECTOR)

    def _on_side_arrow_press(self, side: Side):

        @runtime_checkable
        class AcceptsArrowPress(Protocol):
            def on_side_arrow_press(self, side): ...

        for timeline_ui in self._timeline_uis:
            if isinstance(timeline_ui, AcceptsArrowPress):
                timeline_ui.on_side_arrow_press(side)

    def _on_request_to_copy(self):

        ui_with_selected_elements = [tlui for tlui in self._timeline_uis if tlui.has_selected_elements]

        if len(ui_with_selected_elements) == 0:
            raise CopyError("Can't copy: there are no selected elements.")
        if len(ui_with_selected_elements) > 1:
            raise CopyError("Can't copy: there are elements selected in multiple timelines.")

        for timeline_ui in self._select_order:
            if timeline_ui.has_selected_elements:
                copied_components = timeline_ui.get_copy_data_from_selected_elements()

        # noinspection PyUnboundLocalVariable
        events.post(Event.TIMELINE_COMPONENT_COPIED, copied_components)

    def get_elements_for_pasting(self) -> list[dict]:
        clipboard_elements = self._app_ui.get_elements_for_pasting()

        if not clipboard_elements:
            raise PasteError("Can't paste: got no elements from clipboard.")

        return clipboard_elements

    def _on_request_to_paste(self) -> None:

        clipboard_elements = self.get_elements_for_pasting()

        for timeline_ui in self._timeline_uis:
            if timeline_ui.has_selected_elements:
                timeline_ui.paste_into_selected_elements(clipboard_elements)

    def _on_request_to_paste_with_children(self) -> None:
        clipboard_elements = self.get_elements_for_pasting()

        for timeline_ui in self._timeline_uis:
            if timeline_ui.has_selected_elements and timeline_ui.TIMELINE_KIND == TimelineKind.HIERARCHY_TIMELINE:
                timeline_ui.paste_with_children_into_selected_elements(clipboard_elements)

    def _on_debug_selected_elements(self):
        for timeline_ui in self._timeline_uis:
            timeline_ui.debug_selected_elements()

    def get_id(self) -> str:
        return self._app_ui.get_id()

    def get_media_length(self):
        return self._app_ui.get_media_length()

    def get_timeline_width(self):
        return self._app_ui.timeline_width

    # noinspection PyUnresolvedReferences
    def get_x_by_time(self, time: float) -> int:
        return (
                       (time / self._app_ui.get_media_length())
                       * self._app_ui.timeline_width
               ) + self.left_margin_x

    # noinspection PyUnresolvedReferences
    def get_time_by_x(self, x: int) -> float:
        return (
                (x - self.left_margin_x)
                * self._app_ui.get_media_length()
                / self._app_ui.timeline_width
            )

    def _on_hierarchy_timeline_split_button(self) -> None:
        first_hierarchy_timeline_ui = self._get_first_from_select_order_by_kinds(
            [TimelineKind.HIERARCHY_TIMELINE]
        )

        if first_hierarchy_timeline_ui:
            first_hierarchy_timeline_ui.on_split_button()

    def _get_first_from_select_order_by_kinds(self, classes: list[TimelineKind]):
        for tl_ui in self._select_order:
            if tl_ui.TIMELINE_KIND in classes:
                return tl_ui

    def zoomer(self, direction: InOrOut, mouse_x: int):
        if direction == InOrOut.IN:
            self.timeline_width *= 1 + self.ZOOM_SCALE_FACTOR
        else:
            self.timeline_width *= 1 - self.ZOOM_SCALE_FACTOR

        self._update_timelines_after_width_change()

    def create_playback_lines(self):
        for tl_ui in self._timeline_uis:
            if tl_ui.timeline.KIND == TimelineKind.SLIDER_TIMELINE:
                continue

            self.create_playback_line(tl_ui)

    def create_playback_line(self, timeline_ui: TimelineTkUI):
        line_id = draw_playback_line(
            timeline_ui=timeline_ui,
            initial_time=self._timeline_collection.get_current_playback_time()
        )
        self._timeline_uis_to_playback_line_ids[timeline_ui] = line_id

    def on_media_time_change(self, time: float) -> None:
        for tl_ui in self._timeline_uis:
            if not self.slider_is_being_dragged and settings.settings['general']['auto-scroll']:
                self.auto_scroll(tl_ui, time)
            self.change_playback_line_position(tl_ui, time)

    def on_slider_drag(self, is_dragging: bool) -> None:
        self.slider_is_being_dragged = is_dragging

    def auto_scroll(self, timeline_ui: TimelineTkUI, time: float):
        visible_width = timeline_ui.canvas.winfo_width()
        trough_x = self.get_x_by_time(time)

        if trough_x >= visible_width / 2:
            scroll_fraction = (trough_x - (visible_width / 2)) / self.get_timeline_total_size()
            timeline_ui.canvas.xview_moveto(scroll_fraction)

    def change_playback_line_position(self, timeline_ui: TimelineTkUI, time: float):
        if timeline_ui.timeline.KIND == TimelineKind.SLIDER_TIMELINE:
            return

        change_playback_line_x(
            timeline_ui=timeline_ui,
            playback_line_id=self._timeline_uis_to_playback_line_ids[timeline_ui],
            x=self.get_x_by_time(time)
        )


    def on_create_initial_hierarchy(self, timeline: Timeline) -> None:
        timeline.ui.canvas.tag_raise(self._timeline_uis_to_playback_line_ids[timeline.ui])

    def on_request_change_timeline_width(self, width: float) -> None:
        if width < 0:
            raise ValueError(f'Timeline width must be positive. Got {width=}')

        self.timeline_width = width

        self._update_timelines_after_width_change()

    def deselect_all_elements_in_timeline_uis(self):
        for timeline_ui in self._timeline_uis:
            timeline_ui.deselect_all_elements()

    def _update_timelines_after_width_change(self):
        for tl_ui in self._timeline_uis:
            tl_ui.canvas.config(
                scrollregion=(0, 0, self.get_timeline_total_size(), tl_ui.height)
            )

            tl_ui.update_elements_position()

            if not tl_ui.timeline.KIND == TimelineKind.SLIDER_TIMELINE:
                change_playback_line_x(
                    tl_ui,
                    self._timeline_uis_to_playback_line_ids[tl_ui],
                    self._timeline_collection.get_current_playback_time()
                )
            # TODO center view at appropriate point

    def get_timeline_total_size(self):
        return self._app_ui.timeline_total_size

    def _delete_timeline_ui_toolbar_if_necessary(
            self, deleted_timeline_ui: TimelineTkUI
    ):
        logger.debug(
            f"Checking if it is necessary to delete {deleted_timeline_ui} toolbar."
        )
        existing_timeline_uis_of_same_kind = [
            tlui
            for tlui in self._timeline_uis
            if type(tlui) == type(deleted_timeline_ui)
        ]
        if not existing_timeline_uis_of_same_kind:
            logger.debug(f"No more timelines of same kind. Deleting toolbar.")
            deleted_timeline_ui.toolbar.delete()
            self._toolbars.remove(deleted_timeline_ui.toolbar)
        else:
            logger.debug(
                f"There are still timelines of the same kind. Do not delete toolbar."
            )

    def get_timeline_ui_attribute_by_id(self, id_: int, attribute: str) -> Any:
        timeline = self._get_timeline_ui_by_id(id_)
        return getattr(timeline, attribute)

    def _get_timeline_ui_by_id(self, id_: int) -> TimelineTkUI:
        return next((e for e in self._timeline_uis if e.timeline.id == id_), None)

    def get_timeline_uis(self):
        return self._timeline_uis

    def get_timeline_ui_by_id(self, tl_ui_id: int) -> TimelineTkUI:
        return self._timeline_collection.get_timeline_by_id(tl_ui_id).ui

    def _on_request_to_delete_timeline(self, id_: int) -> None:
        timeline_ui = self._get_timeline_ui_by_id(id_)
        if self._ask_delete_timeline(timeline_ui):
            self._timeline_collection.delete_timeline(timeline_ui.timeline)

    @staticmethod
    def _ask_delete_timeline(timeline_ui: TimelineTkUI):
        return tk.messagebox.askyesno(
            "Delete timeline?", f"Are you sure you want to delete timeline {str(timeline_ui)}?"
        )

    def on_request_to_hide_timeline(self, id_: int) -> None:
        timeline_ui = self._get_timeline_ui_by_id(id_)
        logger.debug(f"User requested to hide timeline {timeline_ui}")
        if not timeline_ui.is_visible:
            logger.debug(f"Timeline is already hidden.")
        else:
            logger.debug(f"Hiding timeline.")
            self.hide_timeline_ui(timeline_ui)

    def on_request_to_show_timeline(self, id_: int) -> None:
        timeline_ui = self._get_timeline_ui_by_id(id_)
        logger.debug(f"User requested to show timeline {timeline_ui}")
        if timeline_ui.is_visible:
            logger.debug(f"Timeline is already visible.")
        else:
            logger.debug(f"Making timeline visible.")
            self.show_timeline_ui(timeline_ui)
        pass

    def on_request_to_focus_timelines(self):
        self._select_order[0].canvas.focus_set()

def change_playback_line_x(timeline_ui: TimelineTkUI, playback_line_id: int, x: float) -> None:
    timeline_ui.canvas.coords(
        playback_line_id, x, 0, x, timeline_ui.height,
    )

    timeline_ui.canvas.tag_raise(playback_line_id)


def draw_playback_line(timeline_ui: TimelineTkUI, initial_time: float) -> int:
    line_id = timeline_ui.canvas.create_line(
        timeline_ui.get_x_by_time(initial_time),
        0,
        timeline_ui.get_x_by_time(initial_time),
        timeline_ui.height,
        dash=(3, 3),
        fill="black",
    )

    timeline_ui.canvas.tag_raise(line_id)

    return line_id


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
    def delete(self):
        ...


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
    def __init__(
            self, element_kinds_to_classes: dict[UIElementKind: type(TimelineTkUIElement)]
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
        logger.debug(f"Deleting UI element '{element}'")
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

    def __repr__(self) -> str:
        return default_repr(self)

    def get_all_elements(self) -> set:
        return self._elements

    def update_elements_postion(self) -> None:
        """
        Calls the update_position method on all manager's elements.
        Should be called when zooming, for instance.
        """

        for element in self._elements:
            element.update_position()


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

    TIMELINE_KIND = None
    TOOLBAR_CLASS = None
    COPY_PASTE_MANGER_CLASS = None
    DEFAULT_COPY_ATTRIBUTES = CopyAttributes([], [], [], [])

    def __init__(
            self,
            *args,
            timeline_ui_collection: TkTimelineUICollection,
            timeline_ui_element_manager: TimelineUIElementManager,
            component_kinds_to_classes: dict[UIElementKind: type(TimelineTkUIElement)],
            component_kinds_to_ui_element_kinds: dict[ComponentKind:UIElementKind],
            canvas: TimelineCanvas,
            toolbar: TimelineToolbar,
            name: str,
            height: int,
            is_visible: bool,
            **kwargs
    ):
        super().__init__(
            *args,
            timeline_ui_collection=timeline_ui_collection,
            height=height,
            is_visible=is_visible,
            name=name,
            **kwargs
        )

        self.component_kinds_to_ui_element_kinds = component_kinds_to_ui_element_kinds
        self.element_manager = timeline_ui_element_manager
        self.component_kinds_to_classes = component_kinds_to_classes
        self.canvas = canvas
        self.toolbar = toolbar

        self._setup_visiblity(is_visible)

    #     self.create_playback_line()
    #
    # def create_playback_line(self):
    #     self.playback_line_id = draw_playback_line(
    #         timeline_ui=self,
    #         initial_time=self.timeline_ui_collection._timelineget_current_playback_time()
    #     )
    #
    #     self.canvas.tag_raise(self.playback_line_id)

    def _change_name(self, name: str):
        self.name = name
        self.canvas.update_label(name)

    def _change_height(self, height: int):
        self.height = height
        self.canvas.update_height(height)
        self.update_elements_position()

    # noinspection PyUnresolvedReferences
    @property
    def display_position(self):
        return self.timeline_ui_collection.get_timeline_display_position(self)

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
            self, x: int,
            y: int,
            clicked_item_id: int,
            button: Side,
            modifier: ModifierEnum,
            double: bool
    ) -> None:

        logger.debug(f"Processing click on {self}...")

        if not clicked_item_id:
            if button == Side.LEFT:
                logger.debug(f"No canvas item was clicked.")
            else:
                self.display_right_click_menu_for_timeline(x, y)
            return

        clicked_elements = self._get_clicked_element(clicked_item_id)

        if not clicked_elements:
            logger.debug(f"No ui element was clicked.")
            return

        for clicked_element in clicked_elements:  # clicked item might be owned by more than on element
            if button == Side.LEFT:
                if not double:
                    self._process_ui_element_left_click(clicked_element, clicked_item_id)
                else:
                    self._process_ui_element_double_left_click(clicked_element, clicked_item_id)
            elif button == Side.RIGHT:
                self._process_ui_element_right_click(x, y, clicked_element, clicked_item_id)

        logger.debug(f"Processed click on {self}.")

    def _get_clicked_element(self, clicked_item_id: int) -> list[TimelineUIElement]:

        owns_clicked_item = lambda e: clicked_item_id in e.canvas_drawings_ids

        clicked_elements = self.element_manager.get_elements_by_condition(
            owns_clicked_item, kind=UIElementKind.ANY
        )

        return clicked_elements

    def _process_ui_element_left_click(
            self, clicked_element: TimelineComponentUI, clicked_item_id: int
    ) -> None:

        logger.debug(f"Processing left click on ui element '{clicked_element}'...")

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

    def _process_ui_element_double_left_click(
            self, clicked_element: TimelineComponentUI, clicked_item_id: int
    ) -> None:

        logger.debug(f"Processing double click on ui element '{clicked_element}'...")

        if (
                isinstance(clicked_element, Selectable)
                and clicked_item_id in clicked_element.selection_triggers
        ):
            self._select_element(clicked_element)
        else:
            logger.debug(f"Element is not selectable.")

        if (
                isinstance(clicked_element, DoubleLeftClickable)
                and clicked_item_id in clicked_element.double_left_click_triggers
        ):
            clicked_element.on_double_left_click(clicked_item_id)
        else:
            logger.debug(f"Element is not double clickable.")

    def _process_ui_element_right_click(
            self,
            x: float, y: float,
            clicked_element: TimelineComponentUI,
            clicked_item_id: int
    ) -> None:

        if (
                isinstance(clicked_element, RightClickable)
                and clicked_item_id in clicked_element.right_click_triggers
        ):
            events.subscribe(self, Event.RIGHT_CLICK_MENU_OPTION_CLICK, self.on_right_click_menu_option_click)
            clicked_element.on_right_click(x, y, clicked_item_id)
        else:
            logger.debug(f"Element is not right clickable.")

    def _select_element(self, element: Selectable):

        self.element_manager.select_element(element)

        if isinstance(element, Inspectable):
            logger.debug(f"Element is inspectable. Sending data to inspector.")
            self.post_inspectable_selected_event(element)

            events.subscribe(element, Event.INSPECTOR_FIELD_EDITED, self.on_inspector_field_edited)

    def deselect_all_elements(self):
        for element in self.element_manager.get_all_elements():
            if isinstance(element, Inspectable):
                events.post(Event.INSPECTABLE_ELEMENT_DESELECTED, element.id)

            self.element_manager.deselect_element(element)

    def on_right_click_menu_option_click(self, option: RightClickOption):
        pass

    def on_right_click_menu_new(self) -> None:
        unsubscribe(self, Event.RIGHT_CLICK_MENU_OPTION_CLICK)
        unsubscribe(self, Event.RIGHT_CLICK_MENU_NEW)

    def display_right_click_menu_for_element(self, canvas_x: float, canvas_y: float,
                                             options: list[tuple[str, RightClickOption]]):
        events.post(Event.RIGHT_CLICK_MENU_NEW)
        events.subscribe(self, Event.RIGHT_CLICK_MENU_OPTION_CLICK, self.on_right_click_menu_option_click)

        display_right_click_menu(self.canvas.winfo_rootx() + int(canvas_x),
                                 self.canvas.winfo_rooty() + int(canvas_y), options)

        events.subscribe(self, Event.RIGHT_CLICK_MENU_NEW, self.on_right_click_menu_new)

    def display_right_click_menu_for_timeline(self, canvas_x: float, canvas_y: float):
        RIGHT_CLICK_OPTIONS = [
            ("Change timeline name...", RightClickOption.CHANGE_TIMELINE_NAME),
            ("Change timeline height...", RightClickOption.CHANGE_TIMELINE_HEIGHT)
        ]

        events.post(Event.RIGHT_CLICK_MENU_NEW)
        events.subscribe(self, Event.RIGHT_CLICK_MENU_OPTION_CLICK, self.on_right_click_menu_option_click)

        display_right_click_menu(self.canvas.winfo_rootx() + int(canvas_x),
                                 self.canvas.winfo_rooty() + int(canvas_y), RIGHT_CLICK_OPTIONS)

        events.subscribe(self, Event.RIGHT_CLICK_MENU_NEW, self.on_right_click_menu_new)

    @staticmethod
    def post_inspectable_selected_event(element: Inspectable):
        events.post(
            Event.INSPECTABLE_ELEMENT_SELECTED,
            type(element),
            element.INSPECTOR_FIELDS,
            element.get_inspector_dict(),
            element.id
        )

    def on_inspector_field_edited(self, field_name: str, value: str, inspected_id: int):
        pass

    def update_elements_position(self) -> None:
        self.element_manager.update_elements_postion()

    def _log_and_get_elements_for_button_processing(
            self, action_str_for_log: str
    ) -> list[TimelineTkUIElement] | None:
        """Gets selected elements to start with button click processing.
        Logs process start and if there is nothing to do, if that is the case.
        If timeline is not is_visible or there are no selected elements, there is nothing to do"""

        logging.debug(f"Processing {action_str_for_log} button click in {self}...")

        if not self.visible:
            logging.debug(f"TimelineUI is not visible, nothing to do.")

        selected_elements = self.element_manager.get_selected_elements()

        if not selected_elements:
            logging.debug(f"No element is selected. Nothing to do.")
            return None

        return selected_elements

    def on_delete_press(self):
        selected_elements = self.element_manager.get_selected_elements()
        for element in selected_elements.copy():
            self.timeline.on_request_to_delete_component(element.tl_component)

    def delete_selected_elements(self):
        selected_elements = self._log_and_get_elements_for_button_processing("delete")
        if not selected_elements:
            return

        selected_tl_components = [e.tl_component for e in selected_elements]

        for component in selected_tl_components:
            self.timeline.on_request_to_delete_component(component)

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

    def validate_copy(self, elements: list[TimelineUIElement]) -> None:
        """Can be overwritten by subcalsses to implement validation"""
        pass

    def validate_paste(self, paste_data: dict, elements_to_receive_paste: list[TimelineUIElement]) -> None:
        """Can be overwritten by subcalsses to implement validation"""
        if len(paste_data) > 1:
            raise CopyError("Can't paste more than one copied item at the same time.")

    def get_copy_data_from_selected_elements(self) -> list[dict]:
        selected_elements = self.element_manager.get_selected_elements()

        self.validate_copy(selected_elements)

        return get_copy_data_from_elements(
            [(el, el.DEFAULT_COPY_ATTRIBUTES) for el in selected_elements if isinstance(el, Copyable)])

    def paste_into_selected_elements(self, paste_data: list[dict] | dict):

        selected_elements = self.element_manager.get_selected_elements()

        self.validate_paste(paste_data, selected_elements)

        events.post(Event.RECORD_STATE, self.timeline, StateAction.PASTE)

        for element in self.element_manager.get_selected_elements():
            paste_into_element(element, paste_data[0])

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

    def delete(self):
        logger.info(f"Deleting timeline ui {self}...")

        unsubscribe_from_all(self)

        self.canvas.destroy()
        if self.toolbar:
            self.toolbar.on_timeline_delete()

    def __repr__(self):
        return default_repr(self)

    def __str__(self):
        return f"{self.name} | {self.TIMELINE_KIND.value.capitalize()} Timeline"


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
                create_tool_tip(button, tooltip_text)

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

    def on_timeline_create(self):
        self._increment_decrement_timelines_count(True)
        self._show_display_according_to_visible_timelines_count()

    def delete(self):
        logger.debug(f"Deleting timeline toolbar {self}.")
        self.destroy()


class ToolTip(object):
    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None
        self.id = None
        self.text = ''
        self.label = None
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

        tw.wm_overrideredirect(True)
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


def create_tool_tip(widget, text):
    toolTip = ToolTip(widget)

    def enter(_):
        toolTip.showtip(text)

    def leave(_):
        toolTip.hidetip()

    widget.bind("<Enter>", enter)
    widget.bind("<Leave>", leave)


class RightClickOption(Enum):
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


def display_right_click_menu(x: int, y: int, options: list[tuple[str, RightClickOption]]) -> None:
    class RightClickMenu:
        def __init__(
                self,
                x: int,
                y: int,
                options: list[tuple[str, RightClickOption]]
        ):
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
                        command=lambda _option=option[1]: events.post(Event.RIGHT_CLICK_MENU_OPTION_CLICK, _option)
                    )

    RightClickMenu(x, y, options)
