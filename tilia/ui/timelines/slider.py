from __future__ import annotations
from typing import TYPE_CHECKING, Literal
import logging

from tilia.requests import get, Get, post
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui import coords
from tilia.ui.modifier_enum import ModifierEnum
from tilia import settings
from tilia.requests import Post, listen
from tilia.timelines.base.component import TimelineComponent
from tilia.ui.timelines.timeline import TimelineUI, TimelineUIElementManager
from tilia.ui.timelines.drag import DragManager

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tilia.ui.timelines.common import (
        TimelineCanvas,
    )
    from tilia.ui.timelines.collection import TimelineUIs


class SliderTimelineUI(TimelineUI):
    TOOLBAR_CLASS = None

    TROUGH_RADIUS = settings.get("slider_timeline", "trough_radius")
    TROUGH_DEFAULT_COLOR = settings.get("slider_timeline", "trough_color")
    LINE_DEFAULT_COLOR = settings.get("slider_timeline", "line_color")
    LINE_WEIGHT = settings.get("slider_timeline", "line_weight")

    TIMELINE_KIND = TimelineKind.SLIDER_TIMELINE

    def __init__(
        self,
        id: str,
        collection: TimelineUIs,
        element_manager: TimelineUIElementManager,
        canvas: TimelineCanvas,
        toolbar: Literal[None],
    ):
        super().__init__(
            id=id,
            collection=collection,
            element_manager=element_manager,
            canvas=canvas,
            toolbar=toolbar,
        )

        listen(self, Post.PLAYER_MEDIA_TIME_CHANGE, self.on_audio_time_change)

        self._x = get(Get.LEFT_MARGIN_X)

        self.line = self.canvas.create_line(
            *self.get_line_coords(),
            fill=self.LINE_DEFAULT_COLOR,
            width=self.LINE_WEIGHT,
        )

        self.trough = self.canvas.create_oval(
            *self.get_trough_coords(), fill=self.TROUGH_DEFAULT_COLOR, width=0
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

    def get_line_coords(self) -> tuple:
        x1 = get(Get.LEFT_MARGIN_X)
        x2 = get(Get.RIGHT_MARGIN_X)
        y = self.height / 2
        return x1, y, x2, y

    def get_trough_coords(self) -> tuple:
        r = self.TROUGH_RADIUS
        mid_y = self.height / 2
        x = self._x
        return x - r, mid_y - r, x + r, mid_y + r

    def on_left_click(self, item_id: int, modifier: ModifierEnum, double: bool) -> None:
        logger.debug(f"Processing click on {self}...")

        if not item_id:
            logger.debug("No canvas item was clicked.")
        elif item_id == self.line:
            logger.debug("Line was cliked. Nothing to do.")
        elif item_id == self.trough:
            self.setup_drag()

        logger.debug(f"Processed click on {self}.")

    def setup_drag(self) -> None:
        post(Post.SLIDER_DRAG_START)
        DragManager(
            get_min_x=lambda: get(Get.LEFT_MARGIN_X),
            get_max_x=lambda: get(Get.RIGHT_MARGIN_X),
            before_each=self.before_each_drag,
            after_each=self.after_each_drag,
            on_release=self.on_drag_end,
        )

    def before_each_drag(self):
        self.dragging = True

    def after_each_drag(self, x: int):
        self.x = x
        post(Post.PLAYER_REQUEST_TO_SEEK, coords.get_time_by_x(self._x))
        self._update_trough_position()

    def on_drag_end(self):
        post(Post.PLAYER_REQUEST_TO_SEEK, coords.get_time_by_x(self._x))  # maybe not necessary
        self.dragging = False
        post(Post.SLIDER_DRAG_END)

    def on_audio_time_change(self, time: float) -> None:
        if not self.dragging:
            self._x = coords.get_x_by_time(time)
            self._update_trough_position()

    def get_ui_for_component(
        self, component_kind: ComponentKind, component: TimelineComponent, **kwargs
    ):
        """No components in SliderTimeline. Must implement abstract method."""

    def update_elements_position(self):
        self.x = coords.get_x_by_time(get(Get.CURRENT_PLAYBACK_TIME))
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
        return "Slider Timeline"



