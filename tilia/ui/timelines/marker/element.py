"""
Defines the ui corresponding to a Marker object.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
import logging
import tkinter as tk

import tilia.utils.color
from tilia.requests import Post, listen, stop_listening, stop_listening_to_all, post, get, Get
from tilia.timelines.state_actions import Action
from ..copy_paste import CopyAttributes
from ..drag import DragManager
from ..timeline import RightClickOption
from ...common import format_media_time
from ...coords import get_x_by_time, get_time_by_x
from tilia import settings
from tilia.timelines.common import (
    log_object_deletion,
)
from tilia.ui.timelines.common import TimelineUIElement

if TYPE_CHECKING:
    from .timeline import MarkerTimelineUI

logger = logging.getLogger(__name__)


class MarkerUI(TimelineUIElement):
    WIDTH = settings.get("marker_timeline", "marker_width")
    HEIGHT = settings.get("marker_timeline", "marker_height")

    LABEL_PADX = 7

    INSPECTOR_FIELDS = [
        ("Label", "entry"),
        ("Time", "label"),
        ("Comments", "scrolled_text"),
    ]

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

    def __init__(
        self,
        id: str,
        timeline_ui: MarkerTimelineUI,
        canvas: tk.Canvas,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, canvas=canvas)

        self.marker_proper_id = self.draw_unit()
        self.label_id = self.draw_label()

        self.dragged = None

    def __str__(self) -> str:
        try:
            return f"UI->{self.tl_component}"
        except KeyError:
            return "UI-><unavailable>"

    @classmethod
    def create(
        cls,
        id: str,
        timeline_ui: MarkerTimelineUI,
        canvas: tk.Canvas,
        **kwargs,
    ) -> MarkerUI:
        return MarkerUI(id, timeline_ui, canvas, **kwargs)

    @property
    def time(self):
        return self.tl_component.time

    @property
    def label(self):
        return self.tl_component.label

    @property
    def comments(self):
        return self.tl_component.comments

    @comments.setter
    def comments(self, value):
        self.tl_component.comments = value

    @property
    def x(self):
        return get_x_by_time(self.time)

    @property
    def seek_time(self):
        return self.time

    @label.setter
    def label(self, value):
        self.tl_component.label = value
        self.update_label()

    @property
    def color(self):
        return self.tl_component.color

    @color.setter
    def color(self, value):
        logger.debug(f"Setting {self} color to {value}")
        self.tl_component.color = value

    @property
    def shaded_color(self):
        return tilia.utils.color.hex_to_shaded_hex(self.color)

    def reset_color(self) -> None:
        self.color = settings.get("marker_timeline", "marker_default_color")

    @property
    def canvas_drawings_ids(self):
        return self.marker_proper_id, self.label_id

    def update_label(self):
        self.canvas.itemconfig(self.label_id, text=self.label)

    def update_color(self):
        self.canvas.itemconfig(self.marker_proper_id, fill=self.color)

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
        stop_listening_to_all(self)

    @property
    def selection_triggers(self) -> tuple[int, ...]:
        return self.marker_proper_id, self.label_id

    @property
    def left_click_triggers(self) -> tuple[int, ...]:
        return (self.marker_proper_id,)

    def on_left_click(self, _) -> None:
        self.setup_drag()

    @property
    def right_click_triggers(self) -> tuple[int, ...]:
        return self.marker_proper_id, self.label_id

    def on_right_click(self, x: float, y: float, _) -> None:
        self.timeline_ui.display_right_click_menu_for_element(
            x, y, self.RIGHT_CLICK_OPTIONS
        )
        self.timeline_ui.listen_for_uielement_rightclick_options(self)

    def setup_drag(self) -> None:
        DragManager(
            get_min_x=lambda: get(Get.LEFT_MARGIN_X),
            get_max_x=lambda: get(Get.RIGHT_MARGIN_X),
            before_each=self.before_each_drag,
            after_each=self.after_each_drag,
            on_release=self.on_drag_end,
        )
        
    def before_each_drag(self):
        if not self.dragged:
            post(Post.ELEMENT_DRAG_START)
            self.dragged = True
    
    def after_each_drag(self, drag_x: int):    
        self.tl_component.time = get_time_by_x(drag_x)
        self.update_position()

    def on_drag_end(self):
        if self.dragged:
            logger.debug(f"Dragged {self}. New x is {self.x}")
            post(Post.REQUEST_RECORD_STATE, Action.MARKER_DRAG)
            post(Post.ELEMENT_DRAG_END)

        self.dragged = False

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
