"""
Defines the ui corresponding to a Beat object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.events import Event, subscribe, unsubscribe, unsubscribe_from_all
from tilia.timelines.state_actions import Action
from ..copy_paste import CopyAttributes
from ..timeline import RightClickOption
from ...canvas_tags import CAN_DRAG_HORIZONTALLY, CURSOR_ARROWS
from ...common import format_media_time

if TYPE_CHECKING:
    from .timeline import BeatTimelineUI
    from tilia.timelines.beat.components import Beat
    from tilia.ui.timelines.common import TimelineCanvas

import logging

logger = logging.getLogger(__name__)
import tkinter as tk

from tilia import events
from tilia.timelines.common import (
    log_object_creation,
    log_object_deletion,
)

from tilia.ui.timelines.common import TimelineUIElement


class BeatUI(TimelineUIElement):
    WIDTH = 1
    HEIGHT = 7
    FIRST_IN_MEASURE_WIDTH = 1
    FIRST_IN_MEASURE_HEIGHT = 15

    FILL = "gray"
    FIRST_IN_MEASURE_FILL = "black"

    LABEL_PADX = 3

    DRAG_PROXIMITY_LIMIT = 2

    INSPECTOR_FIELDS = [("Time", "label"), ("Measure", "label")]

    FIELD_NAMES_TO_ATTRIBUTES: dict[str, str] = {}

    DEFAULT_COPY_ATTRIBUTES = CopyAttributes(
        by_element_value=[],
        by_component_value=[],
        support_by_element_value=[],
        support_by_component_value=["time"],
    )

    RIGHT_CLICK_OPTIONS = [
        ("Inspect...", RightClickOption.INSPECT),
        ("", RightClickOption.SEPARATOR),
        ("Change measure number...", RightClickOption.CHANGE_MEASURE_NUMBER),
        ("Reset measure number", RightClickOption.RESET_MEASURE_NUMBER),
        ("Distribute beats", RightClickOption.DISTRIBUTE_BEATS),
        ("Change beats in measure", RightClickOption.CHANGE_BEATS_IN_MEASURE),
        ("", RightClickOption.SEPARATOR),
        ("Delete", RightClickOption.DELETE),
    ]

    @log_object_creation
    def __init__(
        self,
        timeline_component: Beat,
        timeline_ui: BeatTimelineUI,
        canvas: tk.Canvas,
        **_,
    ):

        super().__init__(
            tl_component=timeline_component, timeline_ui=timeline_ui, canvas=canvas
        )

        self.beat_proper_id = self.draw_beat_proper()
        self._label = ""
        self.label_id = self.draw_label()

        self.drag_data = {}
        self.is_first_in_measure = False

    def __str__(self) -> str:
        return f"UI->{self.tl_component}"

    @classmethod
    def create(
        cls,
        beat: Beat,
        timeline_ui: BeatTimelineUI,
        canvas: TimelineCanvas,
        **kwargs,
    ) -> BeatUI:

        return BeatUI(beat, timeline_ui, canvas, **kwargs)

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, value):
        self._label = value
        self.canvas.itemconfig(self.label_id, text=value)

    @property
    def time(self):
        return self.tl_component.time

    @property
    def x(self):
        return self.timeline_ui.get_x_by_time(self.time)

    @property
    def seek_time(self):
        return self.time

    @property
    def measure_number(self):
        return self.timeline_ui.get_measure_number(self)

    @property
    def canvas_drawings_ids(self):
        return self.beat_proper_id, self.label_id

    def update_position(self):

        logger.debug(f"Updating {self} canvas drawings positions...")

        coords = (
            self.get_beat_coords()
            if not self.is_first_in_measure
            else self.get_first_beat_in_measure_coords()
        )

        # update beat proper
        self.canvas.coords(
            self.beat_proper_id,
            *coords,
        )

        # update label
        self.canvas.coords(self.label_id, *self.get_label_coords())

    def update_drawing_as_first_in_measure(self, is_first_in_measure: bool) -> None:
        if is_first_in_measure:
            self.canvas.coords(
                self.beat_proper_id, *self.get_first_beat_in_measure_coords()
            )
            self.canvas.itemconfig(self.beat_proper_id, fill=self.FIRST_IN_MEASURE_FILL)
            self.is_first_in_measure = True
        else:
            self.canvas.coords(self.beat_proper_id, *self.get_beat_coords())
            self.canvas.itemconfig(self.beat_proper_id, fill=self.FILL)
            self.is_first_in_measure = False

    def draw_beat_proper(self) -> int:
        coords = self.get_beat_coords()
        logger.debug(f"Drawing beat proper with {coords}")
        return self.canvas.create_rectangle(
            *coords,
            tags=(CAN_DRAG_HORIZONTALLY, CURSOR_ARROWS),
            fill=self.FILL,
            outline="",
            width=3,
        )

    def draw_label(self):
        coords = self.get_label_coords()
        logger.debug(f"Drawing beat label with {coords=}")
        return self.canvas.create_text(*coords, text=self.label, anchor="n")

    def get_beat_coords(self):

        x0 = self.x - self.WIDTH / 2
        y0 = self.HEIGHT
        x1 = self.x + self.WIDTH / 2
        y1 = 0

        return x0, y0, x1, y1

    def get_first_beat_in_measure_coords(self):

        x0 = self.x - self.FIRST_IN_MEASURE_WIDTH / 2
        y0 = self.FIRST_IN_MEASURE_HEIGHT
        x1 = self.x + self.FIRST_IN_MEASURE_WIDTH / 2
        y1 = 0

        return x0, y0, x1, y1

    def get_label_coords(self):
        return self.x, self.FIRST_IN_MEASURE_HEIGHT + self.LABEL_PADX

    @log_object_deletion
    def delete(self):
        logger.debug(f"Deleting beat proper '{self.beat_proper_id}'")
        self.canvas.delete(self.beat_proper_id)
        logger.debug(f"Deleting label '{self.label_id}'")
        self.canvas.delete(self.label_id)
        unsubscribe_from_all(self)

    @property
    def selection_triggers(self) -> tuple[int, ...]:
        return self.beat_proper_id, self.label_id

    @property
    def left_click_triggers(self) -> tuple[int, ...]:
        return (self.beat_proper_id,)

    def on_left_click(self, _) -> None:
        self.make_drag_data()
        subscribe(self, Event.TIMELINE_LEFT_BUTTON_DRAG, self.drag)
        subscribe(self, Event.TIMELINE_LEFT_BUTTON_RELEASE, self.end_drag)

    @property
    def double_left_click_triggers(self) -> tuple[int, ...]:
        return self.beat_proper_id, self.label_id

    def on_double_left_click(self, _) -> None:
        events.post(Event.PLAYER_REQUEST_TO_SEEK, self.time)

    @property
    def right_click_triggers(self) -> tuple[int, ...]:
        return self.beat_proper_id, self.label_id

    def on_right_click(self, x: float, y: float, _) -> None:
        self.timeline_ui.display_right_click_menu_for_element(
            x, y, self.RIGHT_CLICK_OPTIONS
        )
        self.timeline_ui.listen_for_uielement_rightclick_options(self)

    def make_drag_data(self):
        self.drag_data = {
            "max_x": self.get_drag_right_limit(),
            "min_x": self.get_drag_left_limit(),
            "dragged": False,
            "x": None,
        }

    def get_drag_left_limit(self):
        previous_beat = self.timeline_ui.get_previous_beat(self)
        if not previous_beat:
            return self.timeline_ui.get_left_margin_x() + self.DRAG_PROXIMITY_LIMIT
        return (
            self.timeline_ui.get_x_by_time(previous_beat.time)
            + self.DRAG_PROXIMITY_LIMIT
        )

    def get_drag_right_limit(self):
        next_beat = self.timeline_ui.get_next_beat(self)
        if not next_beat:
            return self.timeline_ui.get_right_margin_x() - self.DRAG_PROXIMITY_LIMIT
        return (
            self.timeline_ui.get_x_by_time(next_beat.time) - self.DRAG_PROXIMITY_LIMIT
        )

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
            events.post(Event.REQUEST_RECORD_STATE, Action.BEAT_DRAG)
            events.post(Event.ELEMENT_DRAG_END)

        self.drag_data = {}

    def on_select(self) -> None:
        self.display_as_selected()

    def on_deselect(self) -> None:
        self.display_as_deselected()

    def display_as_selected(self) -> None:
        self.canvas.itemconfig(self.beat_proper_id, width=1, outline="black")

    def display_as_deselected(self) -> None:
        self.canvas.itemconfig(self.beat_proper_id, width=3, outline="")

    def request_delete_to_component(self):
        self.tl_component.receive_delete_request_from_ui()

    def get_inspector_dict(self) -> dict:
        return {"Time": format_media_time(self.time), "Measure": self.measure_number}
