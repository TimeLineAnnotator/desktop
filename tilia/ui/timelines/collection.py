from __future__ import annotations

import logging
import tkinter as tk
from typing import Any, TYPE_CHECKING

from tilia.ui.canvas_tags import CLICK_THROUGH

if TYPE_CHECKING:
    from tilia.ui.tkinterui import TkinterUI

from tilia import events, settings
from tilia.events import subscribe, Event
from tilia.misc_enums import Side, UpOrDown, InOrOut
from tilia.timelines.common import Timeline
from tilia.timelines.state_actions import StateAction
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.modifier_enum import ModifierEnum
from tilia.ui.timelines.common import TimelineCanvas, TimelineToolbar
from tilia.ui.timelines.timeline import TimelineUI, TimelineUIElementManager
from tilia.ui.timelines.copy_paste import CopyError, PasteError
from tilia.ui.timelines.selection_box import SelectionBox
from tilia.ui.windows.beat_pattern import AskBeatPattern

logger = logging.getLogger(__name__)


class TimelineUICollection:
    """
    Collection of timeline uis. Responsible for:
        - Creating timeline uis;
        - Redirecting events (e.g. clicks, drags, button presses) from the TKEventHandler to the appropriate TimelineUI instance;
        - Handling queries for timeline uis;
        - Gridding timeline ui's canvases on the timeline parent;
        - Getting 'global' information (e.g. margins and timeline size) for timeline uis.
    """

    ZOOM_SCALE_FACTOR = 0.1

    def __init__(
        self,
        app_ui: TkinterUI,
        frame: tk.Frame,
        scrollbar: tk.Scrollbar,
        toolbar_frame: tk.Frame,
    ):

        subscribe(self, Event.CANVAS_LEFT_CLICK, self._on_timeline_ui_left_click)
        subscribe(self, Event.TIMELINE_LEFT_BUTTON_DRAG, self._on_timeline_ui_left_drag)
        subscribe(self, Event.CANVAS_RIGHT_CLICK, self._on_timeline_ui_right_click)
        subscribe(self, Event.KEY_PRESS_DELETE, self._on_delete_press)
        subscribe(self, Event.KEY_PRESS_ENTER, self._on_enter_press)
        subscribe(
            self, Event.KEY_PRESS_LEFT, lambda: self._on_side_arrow_press(Side.LEFT)
        )
        subscribe(
            self, Event.KEY_PRESS_RIGHT, lambda: self._on_side_arrow_press(Side.RIGHT)
        )
        subscribe(
            self, Event.KEY_PRESS_UP, lambda: self._on_up_down_arrow_press(UpOrDown.UP)
        )
        subscribe(
            self,
            Event.KEY_PRESS_DOWN,
            lambda: self._on_up_down_arrow_press(UpOrDown.DOWN),
        )
        subscribe(self, Event.KEY_PRESS_CONTROL_C, self._on_request_to_copy)
        subscribe(self, Event.KEY_PRESS_CONTROL_V, self._on_request_to_paste)
        subscribe(
            self,
            Event.KEY_PRESS_CONTROL_SHIFT_V,
            self._on_request_to_paste_with_children,
        )
        subscribe(self, Event.DEBUG_SELECTED_ELEMENTS, self._on_debug_selected_elements)
        subscribe(
            self,
            Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_SPLIT,
            self._on_hierarchy_timeline_split_button,
        )
        subscribe(
            self,
            Event.MARKER_TOOLBAR_BUTTON_ADD,
            self.on_marker_timeline_add_marker_button,
        )
        subscribe(
            self, Event.BEAT_TOOLBAR_BUTTON_ADD, self.on_beat_timeline_add_beat_button
        )
        subscribe(self, Event.REQUEST_ZOOM_IN, lambda: self.zoomer(InOrOut.IN))
        subscribe(self, Event.REQUEST_ZOOM_OUT, lambda: self.zoomer(InOrOut.OUT))
        subscribe(
            self,
            Event.REQUEST_CHANGE_TIMELINE_WIDTH,
            self.on_request_change_timeline_width,
        )
        subscribe(
            self,
            Event.TIMELINES_REQUEST_MOVE_DOWN_IN_DISPLAY_ORDER,
            lambda tlui_id: self._move_in_display_order(tlui_id, UpOrDown.DOWN),
        )
        subscribe(
            self,
            Event.TIMELINES_REQUEST_MOVE_UP_IN_DISPLAY_ORDER,
            lambda tlui_id: self._move_in_display_order(tlui_id, UpOrDown.UP),
        )
        subscribe(
            self,
            Event.REQUEST_DELETE_TIMELINE,
            self.on_request_to_delete_timeline,
        )
        subscribe(self, Event.REQUEST_CLEAR_TIMELINE, self.on_request_to_clear_timeline)
        subscribe(
            self,
            Event.TIMELINES_REQUEST_TO_SHOW_TIMELINE,
            self.on_request_to_show_timeline,
        )
        subscribe(
            self,
            Event.TIMELINES_REQUEST_TO_HIDE_TIMELINE,
            self.on_request_to_hide_timeline,
        )
        subscribe(self, Event.PLAYER_MEDIA_TIME_CHANGE, self.on_media_time_change)
        subscribe(self, Event.SLIDER_DRAG_START, lambda: self.on_slider_drag(True))
        subscribe(self, Event.SLIDER_DRAG_END, lambda: self.on_slider_drag(False))
        subscribe(
            self,
            Event.HIERARCHY_TIMELINE_UI_CREATED_INITIAL_HIERARCHY,
            self.on_create_initial_hierarchy,
        )
        subscribe(
            self, Event.REQUEST_FOCUS_TIMELINES, self.on_request_to_focus_timelines
        )
        subscribe(
            self,
            Event.SELECTION_BOX_REQUEST_SELECT,
            self.on_selection_box_request_select,
        )
        subscribe(
            self,
            Event.SELECTION_BOX_REQUEST_DESELECT,
            self.on_selection_box_request_deselect,
        )

        self._app_ui = app_ui
        self.frame = frame
        self.toolbar_frame = toolbar_frame
        self._toolbars = set()

        self.scrollbar = scrollbar
        self.scrollbar.config(command=self.on_scrollbar_move)

        self.slider_is_being_dragged = False
        self.selection_boxes = []

        self._timeline_uis = set()
        self._select_order = []
        self._display_order = []
        self._timeline_uis_to_playback_line_ids = {}
        self.selection_box_elements_to_selected_triggers = {}

        self.create_playback_lines()

        self._timeline_collection = None  # will be set by the TiLiA object

    def __str__(self) -> str:
        return self.__class__.__name__ + "-" + str(id(self))

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

    def create_timeline_ui(self, kind: TimelineKind, name: str, **kwargs) -> TimelineUI:
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
            **kwargs,
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

    def delete_timeline_ui(self, timeline_ui: TimelineUI):
        """Deletes given timeline ui. To be called by TimelineCollection
        after a Timeline has been deleted"""
        timeline_ui.delete()
        self._remove_from_timeline_uis_set(timeline_ui)
        self._remove_from_timeline_ui_select_order(timeline_ui)
        self._remove_from_timeline_ui_display_order(timeline_ui)
        if timeline_ui.toolbar:
            self._delete_timeline_ui_toolbar_if_necessary(timeline_ui)

    def _add_to_timeline_uis_set(self, timeline_ui: TimelineUI) -> None:
        logger.debug(f"Adding timeline ui '{timeline_ui}' to {self}.")
        self._timeline_uis.add(timeline_ui)

    def _remove_from_timeline_uis_set(self, timeline_ui: TimelineUI) -> None:
        logger.debug(f"Removing timeline ui '{timeline_ui}' to {self}.")
        try:
            self._timeline_uis.remove(timeline_ui)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline ui '{timeline_ui}' from {self}: not in self.timeline_uis."
            )

    def _add_to_timeline_ui_select_order(self, tl_ui: TimelineUI) -> None:
        logger.debug(f"Inserting timeline into {self} select order.")
        self._select_order.insert(0, tl_ui)

    def _remove_from_timeline_ui_select_order(self, tl_ui: TimelineUI) -> None:
        logger.debug(f"Removing timeline from {self} select order.")
        try:
            self._select_order.remove(tl_ui)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline ui '{tl_ui}' from select order: not in select order."
            )

    def _add_to_timeline_ui_display_order(self, tl_ui: TimelineUI) -> None:
        logger.debug(f"Inserting timeline into {self} display order.")
        self._display_order.append(tl_ui)

    def _remove_from_timeline_ui_display_order(self, tl_ui: TimelineUI) -> None:
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
            tl_ui.canvas.grid(
                row=prev_display_index - direction.value, column=0, sticky="ew"
            )

        tl_ui_to_swap = self._display_order[prev_display_index - direction.value]
        logger.debug(f"Swaping with timeline {tl_ui_to_swap}")

        if tl_ui_to_swap.is_visible:
            tl_ui_to_swap.canvas.grid_forget()
            tl_ui_to_swap.canvas.grid(row=prev_display_index, column=0, sticky="ew")

        (
            self._display_order[prev_display_index],
            self._display_order[prev_display_index - direction.value],
        ) = (
            self._display_order[prev_display_index - direction.value],
            self._display_order[prev_display_index],
        )

        logger.debug(f"New display order is {self._display_order}.")

    def get_timeline_display_position(self, tl_ui: TimelineUI):
        return self._display_order.index(tl_ui)

    def _send_to_top_of_select_order(self, tl_ui: TimelineUI):
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
    def hide_timeline_ui(timeline_ui: TimelineUI):

        timeline_ui.canvas.grid_forget()
        timeline_ui.is_visible = False

        if timeline_ui.toolbar:
            timeline_ui.toolbar.process_visiblity_change(False)

    def show_timeline_ui(self, timeline_ui: TimelineUI):

        timeline_ui.canvas.grid(
            row=self.get_timeline_display_position(timeline_ui), column=0, sticky="ew"
        )
        timeline_ui.is_visible = True

        if timeline_ui.toolbar:
            timeline_ui.toolbar.process_visiblity_change(True)

    @staticmethod
    def get_timeline_ui_class_from_kind(kind: TimelineKind) -> type(TimelineUI):
        from tilia.ui.timelines.hierarchy import HierarchyTimelineUI
        from tilia.ui.timelines.slider import SliderTimelineUI
        from tilia.ui.timelines.marker import MarkerTimelineUI
        from tilia.ui.timelines.beat import BeatTimelineUI

        kind_to_class_dict = {
            TimelineKind.HIERARCHY_TIMELINE: HierarchyTimelineUI,
            TimelineKind.SLIDER_TIMELINE: SliderTimelineUI,
            TimelineKind.MARKER_TIMELINE: MarkerTimelineUI,
            TimelineKind.BEAT_TIMELINE: BeatTimelineUI,
        }

        class_ = kind_to_class_dict[kind]

        return class_

    def create_timeline_canvas(self, name: str, starting_height: int):
        return TimelineCanvas(
            parent=self.frame,
            scrollbar=self.scrollbar,
            width=self.get_tlcanvas_width(),
            left_margin_width=self._app_ui.timeline_padx,
            height=starting_height,
            initial_name=name,
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
        return self._app_ui.get_window_size()

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
        double: bool,
    ) -> None:

        clicked_timeline_ui = self._get_timeline_ui_by_canvas(canvas)

        if clicked_timeline_ui:
            logger.debug(
                f"Notifying timeline ui '{clicked_timeline_ui}' about right click."
            )
            clicked_timeline_ui.on_click(
                x,
                y,
                clicked_item_id,
                button=Side.RIGHT,
                modifier=modifier,
                double=double,
            )
        else:
            raise ValueError(
                f"Can't process left click: no timeline with canvas '{canvas}' on {self}"
            )

    def ask_beat_pattern(self) -> list[int] | None:
        result = AskBeatPattern.ask(self._app_ui.root)
        if result:
            return result
        else:
            return None

    def _on_timeline_ui_left_click(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        clicked_item_id: int,
        modifier: ModifierEnum,
        double: bool,
    ) -> None:

        clicked_timeline_ui = self._get_timeline_ui_by_canvas(canvas)

        if modifier == ModifierEnum.NONE:
            self.deselect_all_elements_in_timeline_uis()

        if clicked_timeline_ui:
            self._send_to_top_of_select_order(clicked_timeline_ui)
            logger.debug(
                f"Notifying timeline ui '{clicked_timeline_ui}' about left click."
            )
            clicked_timeline_ui.on_click(
                x,
                y,
                clicked_item_id,
                button=Side.LEFT,
                modifier=modifier,
                double=double,
            )
            if not self.slider_is_being_dragged:
                self.selection_boxes = [SelectionBox(canvas, [x, y], 0)]
        else:
            logger.debug(
                f"Can't process left click: no timeline with canvas '{canvas}' on {self}"
            )

    def _on_timeline_ui_left_drag(self, _, y: int) -> None:

        if self.slider_is_being_dragged:
            return

        def create_selection_box_below():
            last_selection_box_timeline = self._get_timeline_ui_by_canvas(
                self.selection_boxes[-1].canvas
            )
            last_display_order = self._display_order.index(last_selection_box_timeline)
            try:
                next_timeline = self._display_order[last_display_order + 1]
            except IndexError:
                # no timeline below
                return

            self.selection_boxes.append(
                SelectionBox(
                    next_timeline.canvas,
                    [self.selection_boxes[-1].upper_left[0], -1],
                    next_boundary_below * -1,
                )
            )

        def create_selection_box_above():
            last_selection_box_timeline = self._get_timeline_ui_by_canvas(
                self.selection_boxes[-1].canvas
            )
            last_display_order = self._display_order.index(last_selection_box_timeline)
            try:
                next_timeline = self._display_order[last_display_order - 1]
            except IndexError:
                # no timeline above
                return

            self.selection_boxes.append(
                SelectionBox(
                    next_timeline.canvas,
                    [
                        self.selection_boxes[-1].upper_left[0],
                        next_timeline.canvas.winfo_height(),
                    ],
                    sum([sbx.canvas.winfo_height() for sbx in self.selection_boxes]),
                )
            )

        if self.selection_boxes:
            next_boundary_below = sum(
                [sbx.canvas.winfo_height() for sbx in self.selection_boxes]
            )
            next_boundary_above = (
                sum([sbx.canvas.winfo_height() for sbx in self.selection_boxes[:-1]])
                * -1
            )
            if y > next_boundary_below:
                create_selection_box_below()
            elif y < next_boundary_above:
                create_selection_box_above()

    def on_selection_box_request_select(
        self, canvas: tk.Canvas, canvas_item_id: int
    ) -> None:

        timeline_ui = self._get_timeline_ui_by_canvas(canvas)

        try:
            element = timeline_ui.get_clicked_element(canvas_item_id)[0]
        except IndexError:
            return

        was_selected = timeline_ui.select_element_if_appropriate(
            element, canvas_item_id
        )

        # track selection triggers under selection box
        if was_selected:
            if element in self.selection_box_elements_to_selected_triggers:
                self.selection_box_elements_to_selected_triggers[element].add(
                    canvas_item_id
                )
            else:
                self.selection_box_elements_to_selected_triggers[element] = {
                    canvas_item_id
                }

    def on_selection_box_request_deselect(
        self, canvas: tk.Canvas, canvas_item_id: int
    ) -> None:

        timeline_ui = self._get_timeline_ui_by_canvas(canvas)

        try:
            element = timeline_ui.get_clicked_element(canvas_item_id)[0]
        except IndexError:
            # canvas id does not belong to a timeline element (as in the playback line's id)
            # note that if the canvas item belongs to multiple elements 'element' will always
            # hold the first one on the list returned
            return

        if canvas_item_id not in element.selection_triggers:
            return

        self.selection_box_elements_to_selected_triggers[element].remove(canvas_item_id)

        # stop tracking element if there are no more selection triggers under selection box
        if not self.selection_box_elements_to_selected_triggers[element]:
            self.selection_box_elements_to_selected_triggers.pop(element)
            timeline_ui.deselect_element(element)

    def _on_delete_press(self):

        if not any([tlui.has_selected_elements for tlui in self._timeline_uis]):
            return

        for timeline_ui in self._timeline_uis:
            timeline_ui.on_delete_press()

        events.post(Event.REQUEST_RECORD_STATE, "delete timeline component(s)")

    def _on_enter_press(self):
        if any([tlui.has_selected_elements for tlui in self._timeline_uis]):
            events.post(Event.UI_REQUEST_WINDOW_INSPECTOR)

    def _on_side_arrow_press(self, side: Side):

        for timeline_ui in self._timeline_uis:
            if hasattr(timeline_ui, "on_side_arrow_press"):
                timeline_ui.on_side_arrow_press(side)

    def _on_up_down_arrow_press(self, direction: UpOrDown):

        for timeline_ui in self._timeline_uis:
            if hasattr(timeline_ui, "on_up_down_arrow_press"):
                timeline_ui.on_up_down_arrow_press(direction)

    def _on_request_to_copy(self):

        ui_with_selected_elements = [
            tlui for tlui in self._timeline_uis if tlui.has_selected_elements
        ]

        if len(ui_with_selected_elements) == 0:
            raise CopyError("Can't copy: there are no selected elements.")
        if len(ui_with_selected_elements) > 1:
            events.post(
                Event.REQUEST_DISPLAY_ERROR,
                "Copy error",
                "Can't copy components from more than one timeline.",
            )
            raise CopyError(
                "Can't copy: there are elements selected in multiple timelines."
            )

        for timeline_ui in self._select_order:
            if timeline_ui.has_selected_elements:
                copied_components = timeline_ui.get_copy_data_from_selected_elements()
                break

        # noinspection PyUnboundLocalVariable
        events.post(
            Event.TIMELINE_COMPONENT_COPIED,
            {
                "components": copied_components,
                "timeline_kind": timeline_ui.timeline.KIND,
            },
        )

    def get_elements_for_pasting(self) -> dict[str: dict | TimelineKind]:
        clipboard_elements = self._app_ui.get_elements_for_pasting()

        if not clipboard_elements:
            raise PasteError("Can't paste: got no elements from clipboard.")

        return clipboard_elements

    def _on_request_to_paste(self) -> None:

        clipboard_data = self.get_elements_for_pasting()

        paste_cardinality = (
            "MULTIPLE" if len(clipboard_data["components"]) > 1 else "SINGLE"
        )

        same_kind_timeline_uis = [
            tlui
            for tlui in self._timeline_uis
            if tlui.TIMELINE_KIND == clipboard_data["timeline_kind"]
        ]

        if any(
            [tlui.has_selected_elements for tlui in same_kind_timeline_uis]
        ):  # when there are selected elements
            for timeline_ui in [
                tlui for tlui in same_kind_timeline_uis if tlui.has_selected_elements
            ]:
                if paste_cardinality == "SINGLE" and hasattr(
                    timeline_ui, "paste_single_into_selected_elements"
                ):
                    timeline_ui.paste_single_into_selected_elements(
                        clipboard_data["components"]
                    )
                elif paste_cardinality == "MULTIPLE" and hasattr(
                    timeline_ui, "paste_multiple_into_selected_elements"
                ):
                    timeline_ui.paste_multiple_into_selected_elements(
                        clipboard_data["components"]
                    )
        else:  # no elements are selected
            timeline_to_paste = self._get_first_from_select_order_by_kinds(
                [clipboard_data["timeline_kind"]]
            )
            if paste_cardinality == "SINGLE" and hasattr(
                timeline_to_paste, "paste_single_into_timeline"
            ):
                timeline_to_paste.paste_single_into_timeline(
                    clipboard_data["components"]
                )
            elif paste_cardinality == "MULTIPLE" and hasattr(
                timeline_to_paste, "paste_multiple_into_timeline"
            ):
                timeline_to_paste.paste_multiple_into_timeline(
                    clipboard_data["components"]
                )

    def _on_request_to_paste_with_children(self) -> None:
        clipboard_elements = self.get_elements_for_pasting()

        if clipboard_elements["timeline_kind"] != TimelineKind.HIERARCHY_TIMELINE:
            logger.debug(
                f"Copied elements are not hierarchies. Can't paste with children."
            )
            return

        for timeline_ui in self._timeline_uis:
            if (
                timeline_ui.has_selected_elements
                and timeline_ui.TIMELINE_KIND == TimelineKind.HIERARCHY_TIMELINE
            ):
                timeline_ui.paste_with_children_into_selected_elements(
                    clipboard_elements["components"]
                )

    def _on_debug_selected_elements(self):
        for timeline_ui in self._timeline_uis:
            timeline_ui.debug_selected_elements()

    def get_id(self) -> str:
        return self._app_ui.get_id()

    def get_media_length(self):
        return self._app_ui.get_media_length()

    def get_timeline_width(self):
        return self._app_ui.timeline_width

    def get_current_playback_time(self):
        return self._timeline_collection.get_current_playback_time()

    # noinspection PyUnresolvedReferences
    def get_x_by_time(self, time: float) -> int:
        return (
            (time / self._app_ui.get_media_length()) * self._app_ui.timeline_width
        ) + self.left_margin_x

    # noinspection PyUnresolvedReferences
    def get_time_by_x(self, x: float) -> float:
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

    def on_marker_timeline_add_marker_button(self) -> None:
        first_marker_timeline_ui = self._get_first_from_select_order_by_kinds(
            [TimelineKind.MARKER_TIMELINE]
        )

        if first_marker_timeline_ui:
            first_marker_timeline_ui.create_marker(self.get_current_playback_time())

    def on_beat_timeline_add_beat_button(self) -> None:
        first_beat_timeline_ui = self._get_first_from_select_order_by_kinds(
            [TimelineKind.BEAT_TIMELINE]
        )

        if first_beat_timeline_ui:
            first_beat_timeline_ui.create_beat(time=self.get_current_playback_time())

    def _get_first_from_select_order_by_kinds(self, classes: list[TimelineKind]):
        for tl_ui in self._select_order:
            if tl_ui.TIMELINE_KIND in classes:
                return tl_ui

    def zoomer(self, direction: InOrOut):
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

    def create_playback_line(self, timeline_ui: TimelineUI):
        line_id = draw_playback_line(
            timeline_ui=timeline_ui, initial_time=self.get_current_playback_time()
        )
        self._timeline_uis_to_playback_line_ids[timeline_ui] = line_id

    def after_restore_state(self):
        for tl_ui in self._timeline_uis:
            if tl_ui.timeline.KIND == TimelineKind.SLIDER_TIMELINE:
                continue

            tl_ui.canvas.tag_raise(self._timeline_uis_to_playback_line_ids[tl_ui])

    def on_media_time_change(self, time: float) -> None:
        for tl_ui in self._timeline_uis:
            if (
                not self.slider_is_being_dragged
                and settings.settings["general"]["auto-scroll"]
            ):
                self.auto_scroll(tl_ui, time)
            self.change_playback_line_position(tl_ui, time)

    def on_slider_drag(self, is_dragging: bool) -> None:
        self.slider_is_being_dragged = is_dragging

    def auto_scroll(self, timeline_ui: TimelineUI, time: float):
        visible_width = timeline_ui.canvas.winfo_width()
        trough_x = self.get_x_by_time(time)

        if trough_x >= visible_width / 2:
            self.center_view_at_x(timeline_ui, trough_x - (visible_width / 2))

    def on_center_view_on_time(self, time: float):
        center_x = self.get_x_by_time(time)
        for tl_ui in self._timeline_uis:
            self.center_view_at_x(tl_ui, center_x)

    def center_view_at_x(self, timeline_ui: TimelineUI, x: float) -> None:
        scroll_fraction = x / self.get_timeline_total_size()
        timeline_ui.canvas.xview_moveto(scroll_fraction)

    def change_playback_line_position(self, timeline_ui: TimelineUI, time: float):
        if timeline_ui.timeline.KIND == TimelineKind.SLIDER_TIMELINE:
            return

        change_playback_line_x(
            timeline_ui=timeline_ui,
            playback_line_id=self._timeline_uis_to_playback_line_ids[timeline_ui],
            x=self.get_x_by_time(time),
        )

    def on_create_initial_hierarchy(self, timeline: Timeline) -> None:
        timeline.ui.canvas.tag_raise(
            self._timeline_uis_to_playback_line_ids[timeline.ui]
        )

    def on_request_change_timeline_width(self, width: float) -> None:
        if width < 0:
            raise ValueError(f"Timeline width must be positive. Got {width=}")

        self.timeline_width = width

        self._update_timelines_after_width_change()

    def deselect_all_elements_in_timeline_uis(self):
        for timeline_ui in self._timeline_uis:
            timeline_ui.deselect_all_elements()

        self.selection_box_elements_to_selected_triggers = {}

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
                    self.get_x_by_time(self.get_current_playback_time()),
                )
            # TODO center view at appropriate point

    def get_timeline_total_size(self):
        return self._app_ui.timeline_total_size

    def _delete_timeline_ui_toolbar_if_necessary(self, deleted_timeline_ui: TimelineUI):
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

    def _get_timeline_ui_by_id(self, id_: int) -> TimelineUI:
        return next((e for e in self._timeline_uis if e.timeline.id == id_), None)

    def get_timeline_uis(self):
        return self._timeline_uis

    def get_timeline_ui_by_id(self, tl_ui_id: int) -> TimelineUI:
        return self._timeline_collection.get_timeline_by_id(tl_ui_id).ui

    def on_request_to_delete_timeline(self, id_: int) -> None:
        timeline_ui = self._get_timeline_ui_by_id(id_)
        if self._ask_delete_timeline(timeline_ui):
            self._timeline_collection.delete_timeline(timeline_ui.timeline)

        events.post(Event.REQUEST_RECORD_STATE, StateAction.TIMELINE_DELETE)

    def on_request_to_clear_timeline(self, id_: int) -> None:
        timeline_ui = self._get_timeline_ui_by_id(id_)
        if self._ask_clear_timeline(timeline_ui):
            self._timeline_collection.clear_timeline(timeline_ui.timeline)

    @staticmethod
    def _ask_delete_timeline(timeline_ui: TimelineUI):
        return tk.messagebox.askyesno(
            "Delete timeline",
            f"Are you sure you want to delete timeline {str(timeline_ui)}?",
        )

    @staticmethod
    def _ask_clear_timeline(timeline_ui: TimelineUI):
        return tk.messagebox.askyesno(
            "Delete timeline",
            f"Are you sure you want to clear timeline {str(timeline_ui)}?",
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


def change_playback_line_x(
    timeline_ui: TimelineUI, playback_line_id: int, x: float
) -> None:
    timeline_ui.canvas.coords(
        playback_line_id,
        x,
        0,
        x,
        timeline_ui.height,
    )

    timeline_ui.canvas.tag_raise(playback_line_id)


def draw_playback_line(timeline_ui: TimelineUI, initial_time: float) -> int:
    line_id = timeline_ui.canvas.create_line(
        timeline_ui.get_x_by_time(initial_time),
        0,
        timeline_ui.get_x_by_time(initial_time),
        timeline_ui.height,
        dash=(3, 3),
        fill="black",
        tags=(CLICK_THROUGH,),
    )

    timeline_ui.canvas.tag_raise(line_id)

    return line_id
