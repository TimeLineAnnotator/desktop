"""
Defines the tkinter ui corresponding a HierarchyTimeline.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.timelines.component_kinds import ComponentKind
from tilia.events import EventName
from tilia.misc_enums import IncreaseOrDecrease
from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.ui.tkinter.timelines.common import (
        TkTimelineUICollection,
        TimelineUIElementManager,
        TimelineCanvas,
    )

import logging

logger = logging.getLogger(__name__)
import tkinter as tk

from tilia import globals_, utils, events
from tilia.timelines.hierarchy.timeline import HierarchyTimeline, ParentChildRelation
from tilia.ui.tkinter.timelines.common import TimelineTkUI
from tilia.ui.tkinter.timelines.hierarchy import (
    HierarchyTimelineToolbar,
    HierarchyTkUI,
)

from tilia.ui.element_kinds import UIElementKind


class HierarchyTimelineTkUI(TimelineTkUI, events.Subscriber):

    DEFAULT_HEIGHT = 150
    CANVAS_CLASS = tk.Canvas
    LABEL_WIDTH = 15
    LINE_WEIGHT = 3
    LINE_YOFFSET = 3

    TOOLBAR_CLASS = HierarchyTimelineToolbar
    ELEMENT_KINDS_TO_ELEMENT_CLASSES = {UIElementKind.HIERARCHY_TKUI: HierarchyTkUI}
    COMPONENT_KIND_TO_UIELEMENT_KIND = {
        ComponentKind.HIERARCHY: UIElementKind.HIERARCHY_TKUI
    }

    SUBSCRIPTIONS = [
        EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_GROUP,
        EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_MERGE,
        EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_CREATE_CHILD,
        EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_DECREASE,
        EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_INCREASE,
        EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT,
        EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT_WITH_CHILDREN,
        EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_DELETE,
        EventName.INSPECTOR_WINDOW_CLOSED,
        EventName.INSPECTOR_WINDOW_OPENED,
    ]

    TIMELINE_KIND = TimelineKind.HIERARCHY_TIMELINE

    def __init__(
        self,
        *args,
        timeline_ui_collection: TkTimelineUICollection,
        element_manager: TimelineUIElementManager,
        canvas: TimelineCanvas,
        toolbar: HierarchyTimelineToolbar,
        name: str,
        height: int = DEFAULT_HEIGHT,
        is_visible: bool = True,
        **kwargs,
    ):

        super().__init__(
            *args,
            timeline_ui_collection=timeline_ui_collection,
            timeline_ui_element_manager=element_manager,
            component_kinds_to_classes=self.ELEMENT_KINDS_TO_ELEMENT_CLASSES,
            component_kinds_to_ui_element_kinds=self.COMPONENT_KIND_TO_UIELEMENT_KIND,
            canvas=canvas,
            toolbar=toolbar,
            name=name,
            height=height,
            is_visible=is_visible,
            subscriptions=self.SUBSCRIPTIONS,
            **kwargs,
        )

        self.collection = timeline_ui_collection

        self._height = height
        self.name = name

        self.timeline = None

    def get_timeline_height(self):
        return self._height

    def create_hierarchy_ui(self, *args, **kwargs) -> HierarchyTkUI:

        start, end, level = args

        return HierarchyTkUI(
            self, self.canvas, start, end, level, self.height, **kwargs
        )

    def rearrange_canvas_drawings(self):
        for element in self.element_manager.get_all_elements():
            if element.tl_component.parent and not element.tl_component.children:
                self.rearrange_upward_hierarchies_stacking_order(element)

    def rearrange_upward_hierarchies_stacking_order(
        self, element: HierarchyTkUI
    ) -> None:
        if parent_ui := element.tl_component.parent.ui:
            lowest_element_drawing_id = (
                self.element_manager.get_lowest_element_from_id_list(
                    list(element.canvas_drawings_ids), self.canvas
                )
            )

            # lower parents canvas drawings
            self.canvas.tag_lower(parent_ui.rect_id, lowest_element_drawing_id)
            self.canvas.tag_lower(parent_ui.label_id, lowest_element_drawing_id)
            self.canvas.tag_lower(parent_ui.comments_ind_id, lowest_element_drawing_id)

            self.rearrange_upward_hierarchies_stacking_order(parent_ui)

    def get_markerid_at_x(self, x: int):
        starts_or_ends_at_time = lambda u: u.start_x == x or u.end_x == x
        element = self.element_manager.get_element_by_condition(
            starts_or_ends_at_time, UIElementKind.HIERARCHY_TKUI
        )

        if not element:
            return

        # noinspection PyUnresolvedReferences
        if element.start_x == x:
            # noinspection PyUnresolvedReferences
            return element.start_marker
        elif element.end_x == x:
            # noinspection PyUnresolvedReferences
            return element.end_marker
        else:
            raise ValueError(
                "Can't get marker: markers in found element do not match desired x."
            )

    def get_units_using_marker(self, marker_id: int) -> list[int]:
        logger.debug(f"Getting units using marker '{marker_id}'...")
        id_as_start_or_end_marker = (
            lambda e: e.start_marker == marker_id or e.end_marker == marker_id
        )
        units_using_marker = self.element_manager.get_elements_by_condition(
            id_as_start_or_end_marker, kind=UIElementKind.ANY
        )
        logger.debug(f"Got units {units_using_marker}.")
        return units_using_marker

    def _increment_toolbar_counter(self):
        self.toolbar.increment_visible_timeline_counter()
        pass

    def on_subscribed_event(
        self, event_name: str, *args: tuple, **kwargs: dict
    ) -> None:
        if event_name == EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_CREATE_CHILD:
            self.on_create_unit_below_button()
        elif event_name == EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_INCREASE:
            self.on_change_level_button(IncreaseOrDecrease.INCREASE)
        elif event_name == EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_DECREASE:
            self.on_change_level_button(IncreaseOrDecrease.DECREASE)
        elif event_name == EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_GROUP:
            self.on_group_button()
        elif event_name == EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_SPLIT:
            self.on_split_button()
        elif event_name == EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_MERGE:
            self.on_merge_button()
        elif event_name == EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT:
            self.on_paste_unit_button()
        elif (
            event_name
            == EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT_WITH_CHILDREN
        ):
            self.on_paste_unit_with_children_button()
        elif event_name == EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_DELETE:
            self.on_delete_button()
        elif event_name == EventName.INSPECTOR_WINDOW_OPENED:
            self.on_inspector_window_opened()

    @staticmethod
    def _swap_components_with_uis_in_relation(
        relation: ParentChildRelation,
    ) -> ParentChildRelation:

        return ParentChildRelation(
            parent=relation[0].ui, children=[child.ui for child in relation[1]]
        )

    def update_parent_child_relation(self, relation: ParentChildRelation) -> None:
        logging.debug(
            f"Arranging elements in {self} to parent/child relation '{relation}'"
        )

        ui_relation = self._swap_components_with_uis_in_relation(relation)
        parent_ui, children_uis = ui_relation

        if not parent_ui or not children_uis:
            logger.debug(f"No parent or children in relation. Nothing to do.")
            return

        children_canvas_drawings_ids = (
            self.element_manager.get_canvas_drawings_ids_from_elements(children_uis)
        )

        lowest_child_drawing_id = self.element_manager.get_lowest_element_from_id_list(
            children_canvas_drawings_ids, self.canvas
        )

        # lower parents canvas drawings
        self.canvas.tag_lower(parent_ui.rect_id, lowest_child_drawing_id)
        self.canvas.tag_lower(parent_ui.label_id, lowest_child_drawing_id)
        self.canvas.tag_lower(parent_ui.comments_ind_id, lowest_child_drawing_id)

    def on_create_unit_below_button(self):
        selected_elements = self._log_and_get_elements_for_button_processing(
            "create button below"
        )
        if not selected_elements:
            return

        selected_tl_components = [e.tl_component for e in selected_elements]
        for component in selected_tl_components:
            logging.debug(f"Requesting timeline to create unit below {component}.")
            self.timeline.create_unit_below(component)

        logging.debug(f"Processed create unit below button.")

    def on_change_level_button(self, increase_or_decrease: IncreaseOrDecrease):
        selected_elements = self._log_and_get_elements_for_button_processing(
            increase_or_decrease.name.lower()
        )
        if not selected_elements:
            return

        if not selected_elements:
            logging.debug(f"No element is selected. Nothing to do.")

        selected_tl_components = [e.tl_component for e in selected_elements]
        for component in selected_tl_components:
            logging.debug(
                f"Requesting timeline to {increase_or_decrease.name.lower()} level of {component}."
            )
            self.timeline.change_level_by_amount(increase_or_decrease.value, component)

        logging.debug(f"Processed {increase_or_decrease.name.lower()} level button.")

    def on_group_button(self):
        selected_elements = self._log_and_get_elements_for_button_processing("group")
        if not selected_elements:
            return

        selected_components = [e.tl_component for e in selected_elements]
        logging.debug(f"Requesting timeline to group {selected_components}.")
        self.timeline.group(selected_components)

        logging.debug(f"Processed group level button.")

    def on_split_button(self):
        logging.debug(f"Processing split button press...")
        split_time = self.timeline.get_current_playback_time()
        logging.debug(f"Requesting timeline to split at time={split_time}.")
        self.timeline.split(split_time)
        logging.debug(f"Processed split button press.")

    def on_merge_button(self):
        selected_elements = self._log_and_get_elements_for_button_processing("merge")
        if not selected_elements:
            return

        selected_components = [e.tl_component for e in selected_elements]
        logging.debug(f"Requesting timeline to merge {selected_components}.")
        self.timeline.merge(selected_components)

    def on_paste_unit_button(self):
        selected_elements = self._log_and_get_elements_for_button_processing("paste")
        if not selected_elements:
            return

    def on_paste_unit_with_children_button(self):
        selected_elements = self._log_and_get_elements_for_button_processing(
            "paste with children"
        )
        if not selected_elements:
            return

        selected_tl_components = [e.tl_component for e in selected_elements]

    def on_delete_button(self):
        self.delete_selected_elements()

    def get_previous_marker_x_by_x(self, x: int) -> None | int:
        all_marker_xs = self.get_all_elements_boundaries()
        earlier_marker_xs = [x_ for x_ in all_marker_xs if x_ < x]

        if earlier_marker_xs:
            return max(earlier_marker_xs)
        else:
            return None

    def get_next_marker_x_by_x(self, x: int) -> None | int:
        all_marker_xs = self.get_all_elements_boundaries()
        later_marker_xs = [x_ for x_ in all_marker_xs if x_ > x]

        if later_marker_xs:
            return min(later_marker_xs)
        else:
            return None

    def get_all_elements_boundaries(self) -> set[int]:
        """Returns all the start_x and end_x values for hierarchy ui's in timeline."""
        earlier_boundaries = self.element_manager.get_existing_values_for_attribute(
            "start_x", kind=UIElementKind.HIERARCHY_TKUI
        )
        later_boundaries = self.element_manager.get_existing_values_for_attribute(
            "end_x", kind=UIElementKind.HIERARCHY_TKUI
        )

        return earlier_boundaries.union(later_boundaries)

    def on_inspector_window_opened(self):
        for element in self.element_manager.get_selected_elements():
            logger.debug(
                f"Notifying inspector of previsously selected elements on {self}..."
            )
            # noinspection PyTypeChecker
            self.post_inspectable_selected_event(element)

    def __repr__(self):
        return f"{type(self).__name__}({self.name}|{id(self)})"


# noinspection PyUnresolvedReferences,PyAttributeOutsideInit
class TimelineUIOldMethods:
    # -------------------OLD METHODS----------------------

    def on_hscrollbar(self, *args):
        # TODO: Refactor, I think it is redundant to do this on every timeline. Will research.
        # In the meantime, figure out what to do about collection attribute
        self.collection.scrollbar.set(*args)
        try:
            if globals_.settings["GENERAL"]["freeze_timeline_labels"]:
                self.update_freezed_label_position()
        except TypeError:
            # testing
            pass

    def update_freezed_label_position(self) -> None:
        self.canvas.coords(
            self.label_bg,
            0,
            0,
            self.canvas.canvasx(0) + globals_.TIMELINE_PADX,
            self.height,
        )
        self.canvas.tag_raise(self.label_bg)

        self.canvas.coords(
            self.label_in_canvas, self.canvas.canvasx(20), self.height / 2
        )
        self.canvas.tag_raise(self.label_in_canvas)

    def reset_label_position(self):
        self.canvas.coords(self.label_bg, *self._default_label_bg_coords)
        self.canvas.coords(self.label_in_canvas, *self._default_label_coords)

    def make_visible(self):
        self.grid_canvas()
        if isinstance(self, HasToolbar):
            self.show_toolbar()

    def make_invisible(self, change_visibility=True):
        self.canvas.grid_remove()
        if change_visibility:
            self.visible = False
        if isinstance(self, HasToolbar):
            # noinspection PyUnresolvedReferences
            self.update_toolbar()

    def update_toolbar(self):
        toolbar_should_be_visible = False
        # TODO - how to not violate the law of demeter here?
        for timeline in self.collection.objects:
            if isinstance(timeline, type(self)) and timeline.visible:
                toolbar_should_be_visible = True

        if not toolbar_should_be_visible:
            self.hide_toolbar()
        else:
            self.show_toolbar()

    def on_right_click(self, canvas_id: int, event: tk.Event) -> None:
        """Handles right-clicking inside of timeline"""
        try:
            obj = self.get_element_by_attribute("canvas_id", canvas_id)
            # if isinstance(obj, ClickProxy):
            #     obj = obj.proxied
            if isinstance(obj, utils.ObjectRightClickMenu):
                obj.show_right_click_menu(event)
        except IndexError:
            if isinstance(self, HasRightClickMenu):
                self.show_right_click_menu(event)

    def ask_change_label_text(self):
        new_label = tk.simpledialog.askstring(
            "Insert new timeline label",
            "Insert new timeline label",
            initialvalue=self.label_text,
        )
        if new_label:
            self.label_text = new_label
            self.canvas.itemconfig(self.label_in_canvas, text=self.label_text)

    def draw_vertical_line(self):
        self.vline = self.canvas.create_line(
            get_x_from_time(globals_.CURRENT_TIME),
            0,
            get_x_from_time(globals_.CURRENT_TIME),
            self.height,
            dash=(3, 3),
            fill="black",
        )

    def update_vline_position(self, time: float) -> None:
        self.canvas.coords(
            self.vline,
            get_x_from_time(time),
            0,
            get_x_from_time(time),
            self.canvas.winfo_height(),
        )

        self.canvas.tag_raise(self.vline)
        self.canvas.tag_raise(self.label_bg)
        self.canvas.tag_raise(self.label_in_canvas)

    def rearrange_label(self):
        logger.debug(f"Rearranging label on {self}")
        self.canvas.tag_raise(self.label_bg)
        self.canvas.tag_raise(self.label_in_canvas)
        self.update_vline_position(globals_.CURRENT_TIME)

    class TimelineRightClickMenu(tk.Menu):
        def __init__(self, timeline, *args, **kwargs):
            super().__init__(*args, **kwargs, tearoff=0)
            self.timeline = timeline
            self.add_command(
                label="Change timeline name",
                command=self.timeline.ask_change_label_text,
            )

        def show(self, event):
            self.tk_popup(event.x_root, event.y_root)

    def on_double_click(self, canvas_id: int, _1, _2):
        """Handles double-clicking"""
        super(HierarchyTimeline, self).on_double_click(canvas_id, _1, _2)
        self.collection.update_vlines_position(globals_.CURRENT_TIME)

    def on_shift_arrow_key(self, direction):
        """Adds unit to selection according to direction"""

        if not self.selected_objects:
            return

        units_to_add = []
        if direction.lower() == "right":
            referential_unit = sorted(self.selected_objects, key=lambda x: x.end)[-1]
            units_to_add.append(
                self.find_next_by_attr(
                    "start",
                    referential_unit.start,
                    "Hierarchy",
                    custom_list=[
                        unit
                        for unit in self.find_by_kind("Hierarchy")
                        if unit.level == referential_unit.level
                    ],
                )
            )
        elif direction.lower() == "left":
            referential_unit = sorted(self.selected_objects, key=lambda x: x.start)[0]
            units_to_add.append(
                self.find_previous_by_attr(
                    "start",
                    referential_unit.start,
                    "Hierarchy",
                    custom_list=[
                        unit
                        for unit in self.find_by_kind("Hierarchy")
                        if unit.level == referential_unit.level
                    ],
                )
            )
        elif direction.lower() == "up":
            for unit in self.selected_objects:
                if unit.parent:
                    units_to_add.append(unit.parent)

        elif direction.lower() == "down":
            for unit in self.selected_objects:
                if unit.children:
                    for child in unit.children:
                        units_to_add.append(child)

        for unit in units_to_add:
            self.select_object(unit)

    def on_arrow_key(self, direction):
        """Selects unit according to direction"""

        if not self.selected_objects:
            return

        unit_to_select = None
        if direction.lower() == "right":
            unit_to_select = self.find_next_by_attr(
                "start",
                self.selected_object.start,
                "Hierarchy",
                custom_list=[
                    unit
                    for unit in self.find_by_kind("Hierarchy")
                    if unit.level == self.selected_object.level
                ],
            )
        elif direction.lower() == "left":
            unit_to_select = self.find_previous_by_attr(
                "start",
                self.selected_object.start,
                "Hierarchy",
                custom_list=[
                    unit
                    for unit in self.find_by_kind("Hierarchy")
                    if unit.level == self.selected_object.level
                ],
            )
        elif direction.lower() == "up":
            if not self.selected_object.parent:
                return

            unit_to_select = self.selected_object.parent

        elif direction.lower() == "down":
            if not self.selected_object.children:
                return

            unit_to_select = sorted(
                self.selected_object.children, key=lambda x: x.start
            )[0]

        if unit_to_select:
            self.deselect_all()
            self.select_object(unit_to_select)

    def redraw(self):
        super().redraw()
        self.draw(redraw=True)
        self.units.redraw()
        self.arrange_fixed_elements()

    def arrange_fixed_elements(self):
        self.canvas.tag_raise(self.line.canvas_id)
        self.rearrange_label()

    def ask_change_height(self):
        new_height = tk.simpledialog.askinteger(
            "Change height", "Insert new timeline height", initialvalue=self.height
        )
        if new_height:
            self.canvas.config(height=new_height)
            self.canvas.update()
            self.height = new_height
            self.redraw()
