"""
Tkinter ui for the SliderTimeline interface.
Pretty simple, so it doesn't need its own package.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.ui.timelines.common import (
        TimelineUICollection,
        TimelineUIElementManager,
        TimelineCanvas,
    )

from tilia import events
from tilia.events import Event, subscribe, unsubscribe
from tilia.timelines.common import TimelineComponent
from tilia.ui.element_kinds import UIElementKind
from tilia.ui.timelines.common import TimelineUI

import logging

logger = logging.getLogger(__name__)


class SliderTimelineUI(TimelineUI):

    TOOLBAR_CLASS = None
    ELEMENT_KINDS_TO_ELEMENT_CLASSES = {}
    COMPONENT_KIND_TO_UIELEMENT_KIND = {}

    DEFAULT_HEIGHT = 25

    TROUGH_HEIGHT = 10
    TROUGH_WIDTH = 10
    LINE_WEIGHT = 3

    TROUGH_DEFAULT_COLOR = "#FF0000"

    LINE_DEFAULT_COLOR = "#000000"

    TIMELINE_KIND = TimelineKind.SLIDER_TIMELINE

    def __init__(
        self,
        *args,
        timeline_ui_collection: TimelineUICollection,
        element_manager: TimelineUIElementManager,
        canvas: TimelineCanvas,
        toolbar: None,
        name: str,
        height: int = DEFAULT_HEIGHT,
        is_visible: bool = True,
        **kwargs,
    ):
        super().__init__(
            *args,
            timeline_ui_collection=timeline_ui_collection,
            timeline_ui_element_manager=element_manager,
            component_kinds_to_classes=[],
            component_kinds_to_ui_element_kinds=[],
            canvas=canvas,
            toolbar=toolbar,
            name=name,
            height=height,
            is_visible=is_visible,
            **kwargs,
        )

        subscribe(self, Event.PLAYER_MEDIA_TIME_CHANGE, self.on_audio_time_change)

        self._x = self.get_left_margin_x()

        self.line = self.canvas.create_line(
            *self.get_line_coords(),
            fill=self.LINE_DEFAULT_COLOR,
            width=self.LINE_WEIGHT,
        )

        self.trough = self.canvas.create_oval(
            *self.get_trough_coords(),
            fill=self.TROUGH_DEFAULT_COLOR,
            tags="canHDrag",
            width=0,
        )

        self.dragging = False

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, value):
        logger.debug(f"Setting slider timeline slider to x={value}")
        self._x = value

    def _update_trough_position(self) -> None:
        self.canvas.coords(self.trough, *self.get_trough_coords())

    def _update_line_position(self) -> None:
        self.canvas.coords(self.line, *self.get_line_coords())

    def get_trough_coords(self) -> tuple:
        return (
            self._x - self.TROUGH_WIDTH / 2,
            self.height / 2 - (self.TROUGH_HEIGHT - self.LINE_WEIGHT) / 2,
            self._x + self.TROUGH_WIDTH / 2,
            self.height / 2 + (self.LINE_WEIGHT + self.TROUGH_HEIGHT) / 2,
        )

    def on_click(self, x: int, _, clicked_item_id: int, **_kw) -> None:

        logger.debug(f"Processing click on {self}...")

        if not clicked_item_id:
            logger.debug(f"No canvas item was clicked.")
        elif clicked_item_id == self.line:
            logger.debug(f"Line was cliked. Nothing to do.")
        elif clicked_item_id == self.trough:
            self.prepare_to_drag()

        logger.debug(f"Processed click on {self}.")

    def get_line_coords(self) -> tuple:
        return (
            self.get_left_margin_x(),
            self.height / 2 + self.LINE_WEIGHT / 2,
            self.get_right_margin_x(),
            self.height / 2 + self.LINE_WEIGHT / 2,
        )

    def prepare_to_drag(self):
        subscribe(self, Event.TIMELINE_LEFT_BUTTON_DRAG, self.drag)
        subscribe(self, Event.TIMELINE_LEFT_BUTTON_RELEASE, self.end_drag)
        events.post(Event.SLIDER_DRAG_START)

    def drag(self, x: int, _) -> None:
        logger.debug(f"Dragging {self} trough...")
        self.dragging = True

        max_x = self.get_right_margin_x()
        min_x = self.get_left_margin_x()

        drag_x = x
        if x > max_x:
            logger.debug(
                f"Mouse is beyond right drag limit. Dragging to max x='{max_x}'"
            )
            drag_x = max_x
        elif x < min_x:
            logger.debug(
                f"Mouse is beyond left drag limit. Dragging to min x='{min_x}'"
            )
            drag_x = min_x
        else:
            logger.debug(f"Dragging to x='{drag_x}'.")

        self.x = drag_x
        events.post(Event.PLAYER_REQUEST_TO_SEEK, self.get_time_by_x(self._x))
        self._update_trough_position()

    def end_drag(self):
        logger.debug(f"Ending drag of {self}.")
        self.dragging = False
        events.post(Event.PLAYER_REQUEST_TO_SEEK, self.get_time_by_x(self._x))
        unsubscribe(self, Event.TIMELINE_LEFT_BUTTON_DRAG)
        unsubscribe(self, Event.TIMELINE_LEFT_BUTTON_RELEASE)
        events.post(Event.SLIDER_DRAG_END)

    def on_audio_time_change(self, time: float) -> None:
        if not self.dragging:
            self._x = self.get_x_by_time(time)
            self._update_trough_position()

    def get_ui_for_component(
        self, kind: UIElementKind, component: TimelineComponent, *args, **kwargs
    ):
        """No components in SliderTimeline. Must implement abstract method."""

    def update_elements_position(self):
        self.x = self.get_x_by_time(self.timeline.get_current_playback_time())
        self._update_trough_position()
        self._update_line_position()

    @property
    def has_selected_elements(self):
        return False

    def draw_playback_line(self) -> None:
        """Slider timeline does not have a playback line (as it has a slider trough)."""

    def change_playback_line_position(self, time: float) -> None:
        """Slider timeline does not have a playback line (as it has a slider trough)."""

    def __str__(self):
        return f"{self.TIMELINE_KIND.value.capitalize()} Timeline"
