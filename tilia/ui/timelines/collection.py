from __future__ import annotations
import logging
import tkinter as tk
from functools import partial
from typing import Any, TYPE_CHECKING

from tilia.clipboard import ClipboardContents
from tilia.requests import get, Get
from tilia.ui import dialogs, coords
from tilia.ui.canvas_tags import TRANSPARENT
from tilia.ui.coords import get_x_by_time
from tilia.ui.dialogs.choose import ChooseDialog
from tilia import settings
from tilia.requests import listen, Post, post
from tilia.enums import Side, UpOrDown, InOrOut
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind as TlKind, TimelineKind
from tilia.ui.modifier_enum import ModifierEnum
from tilia.ui.timelines.common import TimelineCanvas, TimelineToolbar
from tilia.ui.timelines.timeline import TimelineUI, TimelineUIElementManager
from tilia.ui.timelines.copy_paste import CopyError, PasteError
from tilia.ui.timelines.selection_box import SelectionBox
from tilia.exceptions import TimelineUINotFound

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tilia.ui.tkinterui import TkinterUI


class TimelineUIs:
    """
    Collection of timeline uis. Responsible for:
        - Creating timeline uis;
        - Redirecting events (e.g. clicks, drags, button presses)
            from the TKEventHandler to the appropriate TimelineUI instance;
        - Handling queries for timeline uis;
        - Griding timeline ui's canvases on the timeline parent;
        - Getting 'global' information (e.g. margins and timeline size)
            for timeline uis.
    """

    ZOOM_SCALE_FACTOR = 0.1

    def __init__(
        self,
        ui: TkinterUI,
        scrollbar: tk.Scrollbar,
    ):
        self.ui = ui
        self._toolbars = set()

        self.element_is_being_dragged = False
        self.selection_boxes = []
        self.selection_boxes_above = False
        self.selection_boxes_below = True

        self._timeline_uis = set()
        self._select_order = []
        self._timeline_uis_to_playback_line_ids = {}
        self.selection_box_elements_to_selected_triggers = {}

        self.create_playback_lines()

        self._setup_subscriptions()
        self._setup_scrollbar(scrollbar)

    def __str__(self) -> str:
        return self.__class__.__name__ + "-" + str(id(self))

    def __iter__(self):
        return iter(self._timeline_uis)

    def __getitem__(self, item):
        return sorted(self._timeline_uis)[item]

    def __len__(self):
        return len(self._timeline_uis)

    def _setup_subscriptions(self):
        SUBSCRIPTIONS = [
            (
                Post.TIMELINE_COLLECTION_STATE_RESTORED,
                self.on_timeline_collection_state_restored,
            ),
            (Post.TIMELINE_CREATED, self.on_timeline_created),
            (Post.TIMELINE_DELETED, self.on_timeline_deleted),
            (Post.TIMELINE_ORDER_SWAPPED, self.on_timeline_order_swapped),
            (Post.BEAT_UPDATED, partial(self.on_component_event, Post.BEAT_UPDATED)),
            (
                Post.HIERARCHIES_DESERIALIZED,
                partial(self.on_timeline_event, Post.HIERARCHIES_DESERIALIZED),
            ),
            (
                Post.HIERARCHY_GENEALOGY_CHANGED,
                partial(self.on_component_event, Post.HIERARCHY_GENEALOGY_CHANGED),
            ),
            (
                Post.HIERARCHY_LEVEL_CHANGED,
                partial(self.on_component_event, Post.HIERARCHY_LEVEL_CHANGED),
            ),
            (
                Post.HIERARCHY_POSITION_CHANGED,
                partial(self.on_component_event, Post.HIERARCHY_POSITION_CHANGED),
            ),
            (Post.TIMELINE_COMPONENT_CREATED, self.on_timeline_component_created),
            (Post.TIMELINE_COMPONENT_DELETED, self.on_timeline_component_deleted),
            (
                Post.BEAT_TOOLBAR_BUTTON_ADD,
                lambda: self.on_timeline_toolbar_button(TlKind.BEAT_TIMELINE, "add"),
            ),
            (
                Post.BEAT_TOOLBAR_BUTTON_DELETE,
                lambda: self.on_timeline_toolbar_button(TlKind.BEAT_TIMELINE, "delete"),
            ),
            (
                Post.HIERARCHY_TOOLBAR_CREATE_CHILD,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.HIERARCHY_TIMELINE, "create_child"
                ),
            ),
            (
                Post.HIERARCHY_TOOLBAR_LEVEL_INCREASE,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.HIERARCHY_TIMELINE, "increase_level"
                ),
            ),
            (
                Post.HIERARCHY_TOOLBAR_LEVEL_DECREASE,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.HIERARCHY_TIMELINE, "decrease_level"
                ),
            ),
            (
                Post.HIERARCHY_TOOLBAR_GROUP,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.HIERARCHY_TIMELINE, "group"
                ),
            ),
            (
                Post.HIERARCHY_TOOLBAR_MERGE,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.HIERARCHY_TIMELINE, "merge"
                ),
            ),
            (
                Post.HIERARCHY_TOOLBAR_PASTE,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.HIERARCHY_TIMELINE, "paste"
                ),
            ),
            (
                Post.HIERARCHY_TOOLBAR_PASTE_WITH_CHILDREN,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.HIERARCHY_TIMELINE, "paste_with_children"
                ),
            ),
            (
                Post.HIERARCHY_TOOLBAR_DELETE,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.HIERARCHY_TIMELINE, "delete"
                ),
            ),
            (
                Post.HIERARCHY_TOOLBAR_SPLIT,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.HIERARCHY_TIMELINE, "split"
                ),
            ),
            (
                Post.MARKER_TOOLBAR_BUTTON_ADD,
                lambda: self.on_timeline_toolbar_button(TlKind.MARKER_TIMELINE, "add"),
            ),
            (
                Post.MARKER_TOOLBAR_BUTTON_DELETE,
                lambda: self.on_timeline_toolbar_button(
                    TlKind.MARKER_TIMELINE, "delete"
                ),
            ),
            (Post.CANVAS_LEFT_CLICK, self._on_timeline_ui_left_click),
            (Post.CANVAS_RIGHT_CLICK, self._on_timeline_ui_right_click),
            (Post.DEBUG_SELECTED_ELEMENTS, self._on_debug_selected_elements),
            (Post.ELEMENT_DRAG_END, lambda: self.on_element_drag(False)),
            (Post.ELEMENT_DRAG_START, lambda: self.on_element_drag(True)),
            (
                Post.HIERARCHY_TIMELINE_UI_CREATED_INITIAL_HIERARCHY,
                self.on_create_initial_hierarchy,
            ),
            (Post.KEY_PRESS_CONTROL_C, self._on_request_to_copy),
            (Post.KEY_PRESS_CONTROL_SHIFT_V, self._on_request_to_paste_with_children),
            (Post.KEY_PRESS_CONTROL_V, self._on_request_to_paste),
            (Post.KEY_PRESS_DELETE, self._on_delete_press),
            (Post.KEY_PRESS_DOWN, lambda: self._on_up_down_arrow_press(UpOrDown.DOWN)),
            (Post.KEY_PRESS_ENTER, self._on_enter_press),
            (Post.KEY_PRESS_LEFT, lambda: self._on_side_arrow_press(Side.LEFT)),
            (Post.KEY_PRESS_RIGHT, lambda: self._on_side_arrow_press(Side.RIGHT)),
            (Post.KEY_PRESS_UP, lambda: self._on_up_down_arrow_press(UpOrDown.UP)),
            (Post.PLAYER_MEDIA_TIME_CHANGE, self.on_media_time_change),
            (Post.TIMELINE_WIDTH_CHANGED, self.on_timeline_width_changed),
            (Post.REQUEST_CLEAR_ALL_TIMELINES, self.on_request_to_clear_all_timelines),
            (Post.REQUEST_CLEAR_TIMELINE, self.on_request_to_clear_timeline),
            (Post.REQUEST_DELETE_TIMELINE, self.on_request_to_delete_timeline),
            (Post.REQUEST_FOCUS_TIMELINES, self.on_request_to_focus_timelines),
            (Post.REQUEST_ZOOM_IN, lambda: self.zoomer(InOrOut.IN)),
            (Post.REQUEST_ZOOM_OUT, lambda: self.zoomer(InOrOut.OUT)),
            (
                Post.SELECTION_BOX_REQUEST_DESELECT,
                self.on_selection_box_request_deselect,
            ),
            (Post.SELECTION_BOX_REQUEST_SELECT, self.on_selection_box_request_select),
            (Post.SLIDER_DRAG_END, lambda: self.on_element_drag(False)),
            (Post.SLIDER_DRAG_START, lambda: self.on_element_drag(True)),
            (
                Post.TIMELINES_REQUEST_TO_HIDE_TIMELINE,
                self.on_request_to_hide_timeline,
            ),
            (
                Post.TIMELINES_REQUEST_TO_SHOW_TIMELINE,
                self.on_request_to_show_timeline,
            ),
            (Post.TIMELINE_LEFT_BUTTON_DRAG, self._on_timeline_ui_left_drag),
        ]
        for event, callback in SUBSCRIPTIONS:
            listen(self, event, callback)

    def _setup_scrollbar(self, scrollbar: tk.Scrollbar):
        def on_scrollbar_move(*args):
            for timeline in self:
                timeline.canvas.xview(*args)

        scrollbar.config(command=on_scrollbar_move)

    def create_timeline_ui(self, kind: TlKind, id: str) -> TimelineUI:
        timeline_class = self.get_timeline_ui_class_from_kind(kind)
        canvas = self.create_timeline_canvas()
        toolbar = self.get_toolbar_for_timeline_ui(timeline_class.TOOLBAR_CLASS)

        element_manager = TimelineUIElementManager(timeline_class.ELEMENT_CLASS)

        tl_ui = timeline_class(
            id=id,
            collection=self,
            element_manager=element_manager,
            canvas=canvas,
            toolbar=toolbar,
        )

        if toolbar:
            toolbar.on_timeline_create()

        self.grid_timeline_ui_canvas(tl_ui.canvas, tl_ui.ordinal)

        self._add_to_timeline_uis_set(tl_ui)
        self._add_to_timeline_ui_select_order(tl_ui)

        if not kind == TlKind.SLIDER_TIMELINE:
            self.create_playback_line(tl_ui)

        return tl_ui

    def on_timeline_component_created(
        self, _: TimelineKind, tl_id: int, component_id: int
    ):
        self.get_timeline_ui(tl_id).on_timeline_component_created(component_id)

    def on_timeline_component_deleted(
        self, _: TimelineKind, tl_id: int, component_id: int
    ):
        self.get_timeline_ui(tl_id).on_timeline_component_deleted(component_id)

    def delete_timeline_ui(self, timeline_ui: TimelineUI):
        """Deletes given timeline ui. To be called by Timelines
        after a Timeline has been deleted"""
        timeline_ui.delete()
        self._remove_from_timeline_uis_set(timeline_ui)
        self._remove_from_timeline_ui_select_order(timeline_ui)
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
                f"Can't remove timeline ui '{timeline_ui}' from {self}: not in"
                " self.timeline_uis."
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
                f"Can't remove timeline ui '{tl_ui}' from select order: not in select"
                " order."
            )

    def _send_to_top_of_select_order(self, tl_ui: TimelineUI):
        """
        Sends timeline to top of selecting order.
        UI commands (e.g. button clicks) are send to topmost timeline
         of the appropriate type on the select order.
        """

        # TODO give user some visual feedback as to what timeline ui is currently
        #  selected
        logger.debug(f"Sending {tl_ui} to top of select order.")
        self._select_order.remove(tl_ui)
        self._select_order.insert(0, tl_ui)

    def on_timeline_order_swapped(self, id1: str, id2: str):
        tl_ui1 = self.get_timeline_ui(id1)
        tl_ui2 = self.get_timeline_ui(id2)

        for tl_ui in [tl_ui1, tl_ui2]:
            if tl_ui.is_visible:
                tl_ui.canvas.grid_forget()
                tl_ui.canvas.grid(row=tl_ui.ordinal, column=0, sticky="ew")

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

    @staticmethod
    def show_timeline_ui(timeline_ui: TimelineUI):
        timeline_ui.canvas.grid(
            row=timeline_ui.ordinal,
            column=0,
            sticky="ew",
        )
        timeline_ui.is_visible = True

        if timeline_ui.toolbar:
            timeline_ui.toolbar.process_visiblity_change(True)

    @staticmethod
    def get_timeline_ui_class_from_kind(kind: TlKind) -> type[TimelineUI]:
        from tilia.ui.timelines.hierarchy import HierarchyTimelineUI
        from tilia.ui.timelines.slider import SliderTimelineUI
        from tilia.ui.timelines.marker import MarkerTimelineUI
        from tilia.ui.timelines.beat import BeatTimelineUI

        kind_to_class_dict = {
            TlKind.HIERARCHY_TIMELINE: HierarchyTimelineUI,
            TlKind.SLIDER_TIMELINE: SliderTimelineUI,
            TlKind.MARKER_TIMELINE: MarkerTimelineUI,
            TlKind.BEAT_TIMELINE: BeatTimelineUI,
        }

        class_ = kind_to_class_dict[kind]

        return class_

    # TODO: this should be moved to the UI class, probably
    def create_timeline_canvas(self):
        canvas = TimelineCanvas(
            parent=self.ui.get_timelines_frame(),
            scrollbar=self.ui.get_timelines_scrollbar(),
            width=self.ui.get_window_size(),
            left_margin_width=self.ui.timeline_padx,
        )
        canvas.config(scrollregion=(0, 0, get(Get.TIMELINE_FRAME_WIDTH), 1))
        canvas.xview_moveto(self.get_scroll_fraction())
        return canvas

    @property
    def _toolbar_types(self):
        return {type(toolbar) for toolbar in self._toolbars}

    def get_toolbar_for_timeline_ui(
        self, toolbar_type: type[TimelineToolbar]
    ) -> TimelineToolbar | None:
        if not toolbar_type:
            logger.debug("Timeline kind has no toolbar.")
            return

        logger.debug(f"Getting toolbar of type '{toolbar_type}'")

        if toolbar_type in self._toolbar_types:
            logger.debug("Found previous toolbar of same type.")
            return self._get_toolbar_from_toolbars_by_type(toolbar_type)
        else:
            logger.debug("No previous toolbar of same type, creating new toolbar.")
            new_toolbar = toolbar_type(self.ui.get_toolbar_frame())
            self._toolbars.add(new_toolbar)

            return new_toolbar

    def _get_toolbar_from_toolbars_by_type(self, type_: type[TimelineToolbar]):
        return next(
            iter(toolbar for toolbar in self._toolbars if type(toolbar) == type_)
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
        root_x: int,
        root_y: int,
        **_,  # ignores the double argument
    ) -> None:
        clicked_timeline_ui = self.get_timeline_ui_by_attr('canvas', canvas)

        if clicked_timeline_ui:
            logger.debug(
                f"Notifying timeline ui '{clicked_timeline_ui}' about right click."
            )
            clicked_timeline_ui.on_right_click(
                x,
                y,
                clicked_item_id,
                modifier=modifier,
                root_x=root_x,
                root_y=root_y,
            )
        else:
            raise ValueError(
                f"Can't process left click: no timeline with canvas '{canvas}' on"
                f" {self}"
            )

    def _on_timeline_ui_left_click(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        clicked_item_id: int,
        modifier: ModifierEnum,
        double: bool,
    ) -> None:
        clicked_timeline_ui = self.get_timeline_ui_by_attr('canvas', canvas)

        if modifier == ModifierEnum.NONE:
            self.deselect_all_elements_in_timeline_uis(excluding=clicked_timeline_ui)

        if clicked_timeline_ui is not None:
            self._send_to_top_of_select_order(clicked_timeline_ui)
            logger.debug(
                f"Notifying timeline ui '{clicked_timeline_ui}' about left click."
            )
            clicked_timeline_ui.on_left_click(
                clicked_item_id, modifier=modifier, double=double
            )

            if not self.element_is_being_dragged:
                logger.debug(f"{x=}")
                logger.debug(f"{y=}")
                self.selection_boxes = [SelectionBox(canvas, [x, y], 0)]
                self.next_sbx_boundary_below = canvas.winfo_height()
                self.next_sbx_boundary_above = 0
        else:
            logger.debug(
                f"Can't process left click: no timeline with canvas '{canvas}' on"
                f" {self}"
            )

    def _on_timeline_ui_left_drag(self, _, y: int) -> None:
        """
        Creates selection boxes on aproppriate timelines as mouse is dragged.
        :param _: x coord on timeline that started drag
        :param y: y coord on timeline that started drag
        """

        if self.element_is_being_dragged:
            return

        def create_selection_box_below():
            """
            Extends the selection box to the timeline below the current one
            """
            curr_timeline_ord = self.get_timeline_ui_by_attr(
                'canvas',
                self.selection_boxes[-1].canvas
            ).ordinal

            if curr_timeline_ord == len(self):
                # no more timelines below
                return

            next_timeline_ui = self.get_timeline_ui_by_attr('ordinal', curr_timeline_ord + 1)

            self.selection_boxes.append(
                SelectionBox(
                    next_timeline_ui.canvas,
                    [self.selection_boxes[-1].upper_left[0], -1],
                    self.next_sbx_boundary_below * -1,
                )
            )

        def create_selection_box_above():
            curr_timeline_ord = self.get_timeline_ui_by_attr('canvas',
                self.selection_boxes[-1].canvas
            ).ordinal

            if curr_timeline_ord == 1:
                # no more timelines above
                return

            next_timeline_ui = self.get_timeline_ui_by_attr('ordinal', curr_timeline_ord - 1)

            self.selection_boxes.append(
                SelectionBox(
                    next_timeline_ui.canvas,
                    [
                        self.selection_boxes[-1].upper_left[0],
                        next_timeline_ui.canvas.winfo_height(),
                    ],
                    sum([sbx.canvas.winfo_height() for sbx in self.selection_boxes][1:])
                    + next_timeline_ui.canvas.winfo_height(),
                )
            )

        if not self.selection_boxes:
            return

        if y > self.next_sbx_boundary_below:
            if self.selection_boxes_above:
                self.selection_boxes = self.selection_boxes[:1]
                self.selection_boxes_above = False
                self.next_sbx_boundary_above = 0

            self.next_sbx_boundary_below = sum(
                [sbx.canvas.winfo_height() for sbx in self.selection_boxes]
            )
            self.selection_boxes_below = True

            create_selection_box_below()
        elif y < self.next_sbx_boundary_above:
            if self.selection_boxes_below:
                self.selection_boxes = self.selection_boxes[:1]
                self.selection_boxes_below = False
                self.next_sbx_boundary_below = self.selection_boxes[
                    0
                ].canvas.winfo_height()

            self.next_sbx_boundary_above = (
                sum([sbx.canvas.winfo_height() for sbx in self.selection_boxes[1:]])
                * -1
            )
            self.selection_boxes_above = True

            create_selection_box_above()

    def on_selection_box_request_select(
        self, canvas: tk.Canvas, canvas_item_id: int
    ) -> None:
        timeline_ui = self.get_timeline_ui_by_attr('canvas', canvas)

        try:
            element = timeline_ui.get_clicked_element(canvas_item_id)[0]
        except IndexError:
            return

        was_selected = timeline_ui.select_element_if_selectable(element, canvas_item_id)

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
        timeline_ui = self.get_timeline_ui_by_attr('canvas', canvas)

        try:
            element = timeline_ui.get_clicked_element(canvas_item_id)[0]
        except IndexError:
            # canvas id does not belong to a timeline element (as in the playback line's
            # id) note that if the canvas item belongs to multiple elements 'element'
            # will always hold the first one on the list returned
            return

        if canvas_item_id not in element.selection_triggers:
            return

        self.selection_box_elements_to_selected_triggers[element].remove(canvas_item_id)

        # stop tracking element if there are no more selection triggers under
        # selection box
        if not self.selection_box_elements_to_selected_triggers[element]:
            self.selection_box_elements_to_selected_triggers.pop(element)
            timeline_ui.deselect_element(element)

    def _on_enter_press(self):
        if any([tlui.has_selected_elements for tlui in self]):
            post(Post.UI_REQUEST_WINDOW_INSPECTOR)

    def _on_side_arrow_press(self, side: Side):
        for timeline_ui in self:
            if hasattr(timeline_ui, "on_side_arrow_press"):
                timeline_ui.on_side_arrow_press(side)

    def _on_up_down_arrow_press(self, direction: UpOrDown):
        for timeline_ui in self:
            if hasattr(timeline_ui, "on_up_down_arrow_press"):
                timeline_ui.on_up_down_arrow_press(direction)

    def _on_request_to_copy(self):
        ui_with_selected_elements = [
            tlui for tlui in self if tlui.has_selected_elements
        ]

        if len(ui_with_selected_elements) == 0:
            raise CopyError("Can't copy: there are no selected elements.")
        if len(ui_with_selected_elements) > 1:
            post(
                Post.REQUEST_DISPLAY_ERROR,
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
        post(
            Post.TIMELINE_COMPONENT_COPIED,
            {
                "components": copied_components,
                "timeline_kind": timeline_ui.timeline.KIND,
            },
        )

    def _on_request_to_paste(self) -> None:
        clipboard_data = get_clipboard()

        paste_cardinality = (
            "MULTIPLE" if len(clipboard_data["components"]) > 1 else "SINGLE"
        )

        same_kind_timeline_uis = [
            tlui
            for tlui in self
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
            timeline_to_paste = self.get_first_from_select_order_by_kind(
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
        clipboard_elements = get_clipboard()

        if clipboard_elements["timeline_kind"] != TlKind.HIERARCHY_TIMELINE:
            logger.debug(
                "Copied elements are not hierarchies. Can't paste with children."
            )
            return

        for tl_ui in self:
            if (
                tl_ui.has_selected_elements
                and tl_ui.TIMELINE_KIND == TlKind.HIERARCHY_TIMELINE
            ):
                tl_ui.paste_with_children_into_selected_elements(
                    clipboard_elements["components"]
                )

    def _on_debug_selected_elements(self):
        for timeline_ui in self:
            timeline_ui.debug_selected_elements()

    def on_timeline_width_changed(self):
        scroll_time = coords.get_time_by_x(self[0].canvas.canvasx(0))

        for tl_ui in self:
            tl_ui.canvas.config(
                scrollregion=(0, 0, get(Get.TIMELINE_FRAME_WIDTH), tl_ui.height)
            )

            logging.disable(logging.CRITICAL)
            tl_ui.update_elements_position()
            logging.disable(logging.NOTSET)

            if not tl_ui.timeline.KIND == TlKind.SLIDER_TIMELINE:
                change_playback_line_x(
                    tl_ui,
                    self._timeline_uis_to_playback_line_ids[tl_ui],
                    coords.get_x_by_time(get(Get.CURRENT_PLAYBACK_TIME)),
                )

        self.scroll_to_x(coords.get_x_by_time(scroll_time))

    tlkind_to_action_to_call_type = {
        TlKind.HIERARCHY_TIMELINE: {
            "create_child": "all",
            "increase_level": "all",
            "decrease_level": "all",
            "group": "all",
            "merge": "all",
            "paste": "all",
            "paste_with_children": "all",
            "delete": "all",
            "split": "first",
        },
        TlKind.MARKER_TIMELINE: {"add": "first", "delete": "all"},
        TlKind.BEAT_TIMELINE: {"add": "first", "delete": "all"},
    }

    def _on_delete_press(self):
        self.on_timeline_toolbar_button(
            [TlKind.HIERARCHY_TIMELINE, TlKind.MARKER_TIMELINE, TlKind.BEAT_TIMELINE],
            "delete",
        )

    def on_timeline_toolbar_button(
        self, kinds: TlKind | list[TlKind], button: str
    ) -> None:
        if not isinstance(kinds, list):
            kinds = [kinds]

        for kind in kinds:
            if self.tlkind_to_action_to_call_type[kind][button] == "all":
                self.timeline_toolbar_button_call_on_all(kind, button)
            else:
                self.timeline_toolbar_button_call_on_first(kind, button)

        self.timeline_toolbar_button_record(button)

    def timeline_toolbar_button_call_on_all(self, kind: TlKind, button: str):
        for tlui in self.get_timeline_uis_by_attr('TIMELINE_KIND', kind):
            tlui.action_to_callback[button]()

    def timeline_toolbar_button_call_on_first(self, kind: TlKind, button: str):
        first_timeline_ui = self.get_first_from_select_order_by_kind([kind])

        first_timeline_ui.action_to_callback[button]()

    @staticmethod
    def timeline_toolbar_button_record(button: str):
        button_to_method = {
            "create_child": Action.CREATE_CHILD,
            "increase_level": Action.LEVEL_INCREASE,
            "decrease_level": Action.LEVEL_DECREASE,
            "group": Action.GROUP,
            "merge": Action.MERGE,
            "paste": Action.PASTE,
            "paste_with_children": Action.PASTE_WITH_CHILDREN,
            "delete": Action.DELETE_TIMELINE_COMPONENT,
            "split": Action.SPLIT,
            "add": Action.ADD_COMPONENT,
        }

        post(Post.REQUEST_RECORD_STATE, button_to_method[button])

    def on_marker_timeline_add_marker_button(self) -> None:
        first_marker_timeline_ui = self.get_first_from_select_order_by_kind(
            [TlKind.MARKER_TIMELINE]
        )

        if first_marker_timeline_ui:
            post(
                Post.COMPONENT_CREATE_REQUEST,
                first_marker_timeline_ui.id,
                get(Get.CURRENT_PLAYBACK_TIME),
            )

    def on_beat_timeline_add_beat_button(self) -> None:
        first_beat_timeline_ui = self.get_first_from_select_order_by_kind(
            [TlKind.BEAT_TIMELINE]
        )

        if first_beat_timeline_ui:
            post(
                Post.COMPONENT_CREATE_REQUEST,
                first_beat_timeline_ui.id,
                get(Get.CURRENT_PLAYBACK_TIME),
            )

            post(Post.REQUEST_RECORD_STATE, Action.CREATE_BEAT)

    def get_first_from_select_order_by_kind(self, classes: list[TlKind]) -> TimelineUI:
        for tl_ui in self._select_order:
            if tl_ui.TIMELINE_KIND in classes:
                return tl_ui

    def zoomer(self, direction: InOrOut):
        prev_width = get(Get.TIMELINE_WIDTH)
        if direction == InOrOut.IN:
            new_width = prev_width * (1 + self.ZOOM_SCALE_FACTOR)
        else:
            new_width = prev_width * (1 - self.ZOOM_SCALE_FACTOR)

        post(Post.TIMELINE_WIDTH_CHANGE_REQUEST, new_width)

    def create_playback_lines(self):
        for tl_ui in self:
            if tl_ui.timeline.KIND == TlKind.SLIDER_TIMELINE:
                continue

            self.create_playback_line(tl_ui)

    def create_playback_line(self, timeline_ui: TimelineUI):
        line_id = draw_playback_line(
            timeline_ui=timeline_ui, initial_time=get(Get.CURRENT_PLAYBACK_TIME)
        )
        self._timeline_uis_to_playback_line_ids[timeline_ui] = line_id

    def on_timeline_collection_state_restored(self):
        for tl_ui in self:
            if tl_ui.timeline.KIND == TlKind.SLIDER_TIMELINE:
                continue

            tl_ui.canvas.tag_raise(self._timeline_uis_to_playback_line_ids[tl_ui])

    def after_height_change(self, timeline_ui: TimelineUI):
        """Updates timeline ui's playback line coords so it matches new height"""
        self.change_playback_line_position(timeline_ui, get(Get.CURRENT_PLAYBACK_TIME))

    def on_media_time_change(self, time: float) -> None:
        for tl_ui in self:
            if not self.element_is_being_dragged and settings.get(
                "general", "auto-scroll"
            ):
                self.auto_scroll(tl_ui, time)
            self.change_playback_line_position(tl_ui, time)

    def on_element_drag(self, is_dragging: bool) -> None:
        self.element_is_being_dragged = is_dragging

    def auto_scroll(self, timeline_ui: TimelineUI, time: float):
        visible_width = timeline_ui.canvas.winfo_width()
        trough_x = get_x_by_time(time)

        if trough_x >= visible_width / 2:
            self.center_view_at_x(timeline_ui, trough_x - (visible_width / 2))

    def on_center_view_on_time(self, time: float):
        center_x = get_x_by_time(time)
        for tl_ui in self:
            self.center_view_at_x(tl_ui, center_x)

    def center_view_at_x(self, timeline_ui: TimelineUI, x: float) -> None:
        scroll_fraction = x / get(Get.TIMELINE_FRAME_WIDTH)
        timeline_ui.canvas.xview_moveto(scroll_fraction)

    def change_playback_line_position(self, timeline_ui: TimelineUI, time: float):
        if timeline_ui.timeline.KIND == TlKind.SLIDER_TIMELINE:
            return

        change_playback_line_x(
            timeline_ui=timeline_ui,
            playback_line_id=self._timeline_uis_to_playback_line_ids[timeline_ui],
            x=get_x_by_time(time),
        )

    def on_create_initial_hierarchy(self, timeline_id: str) -> None:
        tlui = self.get_timeline_ui(timeline_id)
        tlui.canvas.tag_raise(self._timeline_uis_to_playback_line_ids[tlui])

    def deselect_all_elements_in_timeline_uis(self, excluding: TimelineUI):
        for timeline_ui in self:
            if timeline_ui == excluding:
                continue
            timeline_ui.deselect_all_elements()

        self.selection_box_elements_to_selected_triggers = {}

    def get_scroll_fraction(self) -> float:
        if not self._timeline_uis:
            return 0

        return self[0].canvas.canvasx(0) / get(Get.TIMELINE_FRAME_WIDTH)

    def scroll_to_x(self, x: float):
        x = max(x, 0)
        for tl_ui in self:
            tl_ui.canvas.xview_moveto(x / get(Get.TIMELINE_FRAME_WIDTH))

    def _delete_timeline_ui_toolbar_if_necessary(self, deleted_timeline_ui: TimelineUI):
        logger.debug(
            f"Checking if it is necessary to delete {deleted_timeline_ui} toolbar."
        )
        existing_timeline_uis_of_same_kind = [
            tlui for tlui in self if type(tlui) == type(deleted_timeline_ui)
        ]
        if not existing_timeline_uis_of_same_kind:
            logger.debug("No more timelines of same kind. Deleting toolbar.")
            deleted_timeline_ui.toolbar.delete()
            self._toolbars.remove(deleted_timeline_ui.toolbar)
        else:
            logger.debug(
                "There are still timelines of the same kind. Do not delete toolbar."
            )

    def get_timeline_uis(self):
        return sorted(list(self._timeline_uis))

    def get_timeline_ui(self, tl_id: int) -> TimelineUI:
        """Presupposes timeline ui of 'tl_kind' and with 'tl_id' exists"""
        try:
            return next(tlui for tlui in self if tlui.id == tl_id)
        except StopIteration:
            raise TimelineUINotFound("No timeline UI with id=" + tl_id)

    def get_timeline_ui_by_attr(self, attr: str, value: Any) -> TimelineUI | None:
        return next((tlui for tlui in self if getattr(tlui, attr) == value), None)

    def get_timeline_uis_by_attr(self, attr: str, value: Any) -> [TimelineUI]:
        return [tlui for tlui in self if getattr(tlui, attr) == value]

    def on_request_to_delete_timeline(self, id_: int) -> None:
        timeline_ui = self.get_timeline_ui(id_)
        if dialogs.ask_delete_timeline(str(timeline_ui)):
            post(Post.REQUEST_TIMELINE_DELETE, timeline_ui.id)

        post(Post.REQUEST_RECORD_STATE, Action.TIMELINE_DELETE)

    def on_request_to_clear_timeline(self, id_: int) -> None:
        timeline_ui = self.get_timeline_ui(id_)
        if dialogs.ask_clear_timeline(str(timeline_ui)):
            post(Post.REQUEST_TIMELINE_CLEAR, timeline_ui.id)

    @staticmethod
    def on_request_to_clear_all_timelines() -> None:
        if dialogs.ask_clear_all_timelines():
            post(Post.REQUEST_TIMELINE_CLEAR_ALL)

    def _get_choose_timeline_dialog(
        self,
        title: str,
        prompt: str,
        kind: TimelineKind | list[TimelineKind] | None = None,
    ) -> ChooseDialog:
        if kind and not isinstance(kind, list):
            kind = [kind]

        options = [
            (tlui.ordinal, str(tlui))
            for tlui in sorted(self._timeline_uis, key=lambda x: x.ordinal)
            if ((tlui.TIMELINE_KIND in kind) if kind else True)
        ]

        return ChooseDialog(self.ui.root, title, prompt, options)

    def ask_choose_timeline(
        self,
        title: str,
        prompt: str,
        kind: TimelineKind | list[TimelineKind] | None = None,
    ) -> Timeline:
        """
        Opens a dialog where the user may choose an existing timeline.
        Choices are restricted to the kinds in 'kind'. If no kind is passed,
        all kinds are considered.
        """

        chosen_ordinal = self._get_choose_timeline_dialog(title, prompt, kind).ask()

        chosen_tlui = [
            tlui for tlui in self._timeline_uis if tlui.ordinal == chosen_ordinal
        ][0]

        return chosen_tlui.timeline

    def on_request_to_hide_timeline(self, id_: int) -> None:
        timeline_ui = self.get_timeline_ui(id_)
        logger.debug(f"User requested to hide timeline {timeline_ui}")
        if not timeline_ui.is_visible:
            logger.debug("Timeline is already hidden.")
        else:
            logger.debug("Hiding timeline.")
            self.hide_timeline_ui(timeline_ui)

    def on_request_to_show_timeline(self, id_: int) -> None:
        timeline_ui = self.get_timeline_ui(id_)
        logger.debug(f"User requested to show timeline {timeline_ui}")
        if timeline_ui.is_visible:
            logger.debug("Timeline is already visible.")
        else:
            logger.debug("Making timeline visible.")
            self.show_timeline_ui(timeline_ui)
        pass

    def on_request_to_focus_timelines(self):
        self._select_order[0].canvas.focus_set()

    def on_component_event(
        self,
        event: Post,
        tl_kind: TimelineKind,
        tl_id: int,
        component_id: int,
        *args,
        **kwargs,
    ):
        from tilia.ui.timelines.hierarchy import HierarchyTimelineUI as HrcTlUI
        from tilia.ui.timelines.beat import BeatTimelineUI as BeatTlUI

        event_to_callback = {
            Post.HIERARCHY_LEVEL_CHANGED: HrcTlUI.on_hierarchy_level_changed,
            Post.HIERARCHY_POSITION_CHANGED: HrcTlUI.on_hierarchy_position_changed,
            Post.HIERARCHY_GENEALOGY_CHANGED: HrcTlUI.update_genealogy,
            Post.BEAT_UPDATED: BeatTlUI.on_beat_position_change,
        }

        tlui = self.get_timeline_ui(tl_id)

        event_to_callback[event](tlui, component_id, *args, **kwargs)

    def on_timeline_event(self, event: Post, tl_id: str, *args, **kwargs):
        from tilia.ui.timelines.hierarchy import HierarchyTimelineUI as HrcTlUI

        event_to_callback = {
            Post.HIERARCHIES_DESERIALIZED: HrcTlUI.rearrange_canvas_drawings,
        }
        tlui = self.get_timeline_ui(tl_id)

        event_to_callback[event](tlui, *args, **kwargs)

    def on_timeline_created(self, kind: TimelineKind, id: str):
        self.create_timeline_ui(kind, id)

    def on_timeline_deleted(self, id: str):
        self.delete_timeline_ui(self.get_timeline_ui(id))


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
        coords.get_x_by_time(initial_time),
        0,
        coords.get_x_by_time(initial_time),
        timeline_ui.height,
        dash=(2, 2),  # my windows only supports two dash patterns
        fill="black",
        tags=(TRANSPARENT,),
    )

    timeline_ui.canvas.tag_raise(line_id)

    return line_id


def get_clipboard() -> ClipboardContents:
    clipboard_elements = get(Get.CLIPBOARD)

    if not clipboard_elements:
        raise PasteError("Can't paste: got no elements from clipboard.")

    return clipboard_elements
