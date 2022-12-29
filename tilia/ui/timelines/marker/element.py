"""
Defines the ui corresponding to a Marker object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import tilia.utils.color
from tilia.events import Event, subscribe, unsubscribe
from tilia.timelines.state_actions import StateAction
from ..copy_paste import CopyAttributes
from ..timeline import RightClickOption
from ...common import format_media_time

if TYPE_CHECKING:
    from .timeline import MarkerTimelineUI
    from tilia.timelines.marker.components import Marker
    from tilia.ui.timelines.common import TimelineCanvas, RightClickOption

import logging

logger = logging.getLogger(__name__)
import tkinter as tk

from tilia import events
from tilia.timelines.common import (
    log_object_creation,
    log_object_deletion,
)

from tilia.ui.timelines.common import TimelineUIElement


class MarkerUI(TimelineUIElement):

    WIDTH = 8
    HEIGHT = 10

    DEFAULT_COLOR = "#999999"

    LABEL_PADX = 7

    INSPECTOR_FIELDS = [("Label", "entry"), ("Time", "label"), ("Comments", "entry")]

    FIELD_NAMES_TO_ATTRIBUTES = {"Label": "label", "Comments": "comments"}

    DEFAULT_COPY_ATTRIBUTES = CopyAttributes(
        by_element_value=["label", "color"],
        by_component_value=["comments"],
        support_by_element_value=[],
        support_by_component_value=["time"],
    )

    RIGHT_CLICK_OPTIONS = [
        ("Edit...", RightClickOption.EDIT),
        ("", RightClickOption.SEPARATOR),
        ("Change color...", RightClickOption.CHANGE_COLOR),
        ("Reset color", RightClickOption.RESET_COLOR),
        ("", RightClickOption.SEPARATOR),
        ("Copy", RightClickOption.COPY),
        ("Paste", RightClickOption.PASTE),
        ("", RightClickOption.SEPARATOR),
        ("Delete", RightClickOption.DELETE),
    ]

    @log_object_creation
    def __init__(
        self,
        timeline_component: Marker,
        timeline_ui: MarkerTimelineUI,
        canvas: tk.Canvas,
        label: str = "",
        color: str = DEFAULT_COLOR,
        **_,
    ):

        super().__init__(
            tl_component=timeline_component, timeline_ui=timeline_ui, canvas=canvas
        )

        self._label = label
        self._color = color

        self.marker_proper_id = self.draw_unit()
        self.label_id = self.draw_label()

        self.drag_data = {}

    def __str__(self) -> str:
        return f"UI->{self.tl_component}"

    @classmethod
    def create(
        cls,
        unit: Marker,
        timeline_ui: MarkerTimelineUI,
        canvas: TimelineCanvas,
        **kwargs,
    ) -> MarkerUI:

        return MarkerUI(unit, timeline_ui, canvas, **kwargs)

    @property
    def time(self):
        return self.tl_component.time

    @property
    def comments(self):
        return self.tl_component.comments

    @comments.setter
    def comments(self, value):
        logger.debug(
            f"{self} is setting the value of attribute 'comments' of its timeline component..."
        )
        logger.debug(f"... to '{value}'.")
        self.tl_component.comments = value

    @property
    def x(self):
        return self.timeline_ui.get_x_by_time(self.time)

    @property
    def seek_time(self):
        return self.time

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, value):
        self._label = value
        self.canvas.itemconfig(self.label_id, text=self._label)

    @property
    def color(self):
        return self._color

    # noinspection PyAttributeOutsideInit
    @color.setter
    def color(self, value):
        logger.debug(f"Setting {self} color to {value}")
        self._color = value
        self.canvas.itemconfig(self.marker_proper_id, fill=self._color)

    @property
    def shaded_color(self):
        return tilia.utils.color.hex_to_shaded_hex(self.color)

    def reset_color(self) -> None:
        self.color = self.DEFAULT_COLOR

    @property
    def canvas_drawings_ids(self):
        return (self.marker_proper_id, self.label_id)

    def update_position(self):

        logger.debug(f"Updating {self} canvas drawings positions...")

        # update marker proper
        self.canvas.coords(
            self.marker_proper_id,
            *self.get_unit_coords(),
        )

        # update label
        self.canvas.coords(self.label_id, *self.get_label_coords())

    def draw_unit(self) -> int:
        coords = self.get_unit_coords()
        logger.debug(f"Drawing marker proper with {coords} ans {self.color=}")
        return self.canvas.create_polygon(
            *coords,
            width=self.WIDTH,
            fill=self.color,
        )

    def draw_label(self):
        coords = self.get_label_coords()
        logger.debug(f"Drawing marker label with {coords=} and {self.label=}")
        return self.canvas.create_text(*coords, text=self.label)

    def get_unit_coords(self):

        x0 = self.x - self.WIDTH / 2
        y0 = self.HEIGHT
        x1 = self.x
        y1 = 0
        x2 = self.x + self.WIDTH / 2
        y2 = self.HEIGHT

        return x0, y0, x1, y1, x2, y2

    def get_label_coords(self):
        return self.x, self.HEIGHT + self.LABEL_PADX

    @log_object_deletion
    def delete(self):
        logger.debug(f"Deleting marker proper '{self.marker_proper_id}'")
        self.canvas.delete(self.marker_proper_id)
        logger.debug(f"Deleting label '{self.label_id}'")
        self.canvas.delete(self.label_id)

    @property
    def selection_triggers(self) -> tuple[int, ...]:
        return self.marker_proper_id, self.label_id

    @property
    def left_click_triggers(self) -> tuple[int, ...]:
        return self.marker_proper_id,

    def on_left_click(self, _) -> None:
        self.make_drag_data()
        subscribe(self, Event.TIMELINE_LEFT_BUTTON_DRAG, self.drag)
        subscribe(self, Event.TIMELINE_LEFT_BUTTON_RELEASE, self.end_drag)

    @property
    def right_click_triggers(self) -> tuple[int, ...]:
        return self.marker_proper_id, self.label_id

    def on_right_click(self, x: float, y: float, _) -> None:
        self.timeline_ui.display_right_click_menu_for_element(
            x, y, self.RIGHT_CLICK_OPTIONS
        )
        self.timeline_ui.listen_for_uielement_rightclick_options(self)

    def make_drag_data(self):
        self.drag_data = {
            "max_x": self.timeline_ui.get_right_margin_x(),
            "min_x": self.timeline_ui.get_left_margin_x(),
            "dragged": False,
            "x": None,
        }

    def drag(self, x: int, _) -> None:

        if self.drag_data["x"] is None:
            events.post(Event.ELEMENT_DRAG_START)

        drag_x = x
        if x > self.drag_data["max_x"]:
            logger.debug(
                f"Mouse is beyond right drag limit. Dragging to max x='{self.drag_data['max_x']}'"
            )
            drag_x = self.drag_data["max_x"]
        elif x < self.drag_data["min_x"]:
            logger.debug(
                f"Mouse is beyond left drag limit. Dragging to min x='{self.drag_data['min_x']}'"
            )
            drag_x = self.drag_data["min_x"]

        self.tl_component.time = self.timeline_ui.get_time_by_x(drag_x)

        self.drag_data["x"] = drag_x
        self.update_position()

    def end_drag(self):
        unsubscribe(self, Event.TIMELINE_LEFT_BUTTON_DRAG)
        unsubscribe(self, Event.TIMELINE_LEFT_BUTTON_RELEASE)
        if self.drag_data["x"] is not None:
            logger.debug(f"Dragged {self}. New x is {self.x}")
            events.post(Event.REQUEST_RECORD_STATE, "marker drag")

        self.drag_data = {}

    def on_select(self) -> None:
        self.display_as_selected()

    def on_deselect(self) -> None:
        self.display_as_deselected()

    def display_as_selected(self) -> None:
        self.canvas.itemconfig(
            self.marker_proper_id, fill=self.shaded_color, width=1, outline="black"
        )

    def display_as_deselected(self) -> None:
        self.canvas.itemconfig(
            self.marker_proper_id, fill=self.color, width=0, outline=""
        )

    def request_delete_to_component(self):
        self.tl_component.receive_delete_request_from_ui()

    def get_inspector_dict(self) -> dict:
        return {
            "Label": self.label,
            "Time": format_media_time(self.time),
            "Comments": self.comments,
        }
