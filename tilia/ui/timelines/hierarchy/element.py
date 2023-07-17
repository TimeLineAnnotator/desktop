"""
Defines the ui corresponding to a Hierarchy object.
"""

from __future__ import annotations

import tkinter as tk
import logging
from enum import Enum

from typing import TYPE_CHECKING, TypedDict, Optional

from ..drag import DragManager
from ... import coords
from ...windows.inspect import HIDE_FIELD

if TYPE_CHECKING:
    from .timeline import HierarchyTimelineUI
    from tilia.ui.timelines.common import TimelineCanvas

import tilia.utils.color
from tilia.requests import (
    Post,
    listen,
    stop_listening,
    stop_listening_to_all,
    post,
    get,
    Get,
)
from ..copy_paste import CopyAttributes
from ..timeline import RightClickOption
from ...canvas_tags import CAN_DRAG_HORIZONTALLY, CURSOR_ARROWS
from ...common import format_media_time
from tilia import settings
from tilia.timelines.common import (
    log_object_deletion,
)

from tilia.ui.timelines.common import TimelineUIElement

logger = logging.getLogger(__name__)


class Extremity(Enum):
    START = "start"
    END = "end"
    PRE_START = 'pre_start'
    POST_END = 'post_end'


class HierarchyUI(TimelineUIElement):
    WIDTH = 0
    BASE_HEIGHT = settings.get("hierarchy_timeline", "hierarchy_base_height")
    YOFFSET = 0
    XOFFSET = 1
    LVL_HEIGHT_INCR = settings.get("hierarchy_timeline", "hierarchy_level_height_diff")

    COMMENTS_INDICATOR_CHAR = "💬"
    COMMENTS_INDICATOR_YOFFSET = 5
    COMMENTS_INDICATOR_XOFFSET = -7

    LABEL_YOFFSET = 10

    MARKER_YOFFSET = 0
    MARKER_WIDTH = 2
    MARKER_LINE_HEIGHT = settings.get("hierarchy_timeline", "hierarchy_marker_height")

    MARKER_OUTLINE_WIDTH = 0

    INSPECTOR_FIELDS = [
        ("Label", "entry"),
        ("Start / end", "label"),
        ("Pre-start / post-end", "label"),
        ("Length", "label"),
        ("Formal type", "entry"),
        ("Formal function", "entry"),
        ("Comments", "scrolled_text"),
    ]

    FIELD_NAMES_TO_ATTRIBUTES = {
        "Label": "label",
        "Time": "time",
        "Comments": "comments",
        "Formal function": "formal_function",
        "Formal type": "formal_type",
    }

    DEFAULT_COPY_ATTRIBUTES = CopyAttributes(
        by_element_value=[],
        by_component_value=[
            "formal_type",
            "formal_function",
            "comments",
            "label",
            "color",
        ],
        support_by_element_value=[],
        support_by_component_value=["start", "pre_start", "end", "level"],
    )

    DEFAULT_RIGHT_CLICK_OPTIONS = [
        ("Edit...", RightClickOption.EDIT),
        ("", RightClickOption.SEPARATOR),
        ("Increase level", RightClickOption.INCREASE_LEVEL),
        ("Decrease level", RightClickOption.DECREASE_LEVEL),
        ("Change color...", RightClickOption.CHANGE_COLOR),
        ("Reset color", RightClickOption.RESET_COLOR),
        ("", RightClickOption.SEPARATOR),
        ("Copy", RightClickOption.COPY),
        ("Paste", RightClickOption.PASTE),
        ("Paste w/ all attributes", RightClickOption.PASTE_WITH_ALL_ATTRIBUTES),
        ("", RightClickOption.SEPARATOR),
        ("Export audio...", RightClickOption.EXPORT_TO_AUDIO),
        ("Delete", RightClickOption.DELETE),
    ]

    NAME_WHEN_UNLABELED = "Unnamed"
    FULL_NAME_SEPARATOR = "-"

    def __init__(
            self,
            id: str,
            timeline_ui: HierarchyTimelineUI,
            canvas: tk.Canvas,
            color: str = "",
            **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, canvas=canvas)

        self.previous_width = 0
        self.timeline_ui = timeline_ui
        self.canvas = canvas

        self.label_measures: list[int] = []
        self._setup_label()

        self._setup_color(color)

        self.body_id = self.draw_body()
        self.label_id = self.draw_label()
        self.comments_ind_id = self.draw_comments_indicator()
        self.start_marker, self.end_marker = self.draw_markers()
        self.pre_start_ind_id = None
        self.post_end_ind_id = None

        self.dragged = False
        self.drag_extremity = None

    @classmethod
    def create(
            cls,
            id: str,
            timeline_ui: HierarchyTimelineUI,
            canvas: TimelineCanvas,
            **kwargs,
    ) -> HierarchyUI:
        return HierarchyUI(id, timeline_ui, canvas, **kwargs)

    @property
    def start(self):
        return self.tl_component.start

    @property
    def start_x(self):
        return coords.get_x_by_time(self.start)

    @property
    def end(self):
        return self.tl_component.end

    @property
    def end_x(self):
        return coords.get_x_by_time(self.end)

    @property
    def pre_start(self):
        return self.tl_component.pre_start

    @property
    def has_pre_start(self):
        return self.pre_start != self.start

    @property
    def has_post_end(self):
        return self.post_end != self.end

    @property
    def pre_start_x(self):
        return coords.get_x_by_time(self.pre_start)

    @property
    def post_end(self):
        return self.tl_component.post_end

    @property
    def post_end_x(self):
        return coords.get_x_by_time(self.post_end)

    @property
    def seek_time(self):
        return self.tl_component.pre_start

    @property
    def level(self):
        return self.tl_component.level

    @property
    def label(self):
        return self.tl_component.label

    @label.setter
    def label(self, value):
        self.tl_component.label = value
        self.update_label()

    @property
    def display_label(self):
        """
        Returns largest substring of self.label that fits inside its HierarchyUI
        """

        if not self.label:
            return ""

        max_width = self.end_x - self.start_x

        for i, measure in enumerate(self.label_measures):
            if measure > max_width:
                return self.label[:i]

        return self.label

    @property
    def comments(self):
        return self.tl_component.comments

    @comments.setter
    def comments(self, value):
        logger.debug(
            f"{self} is setting the value of attribute 'comments' of its timeline"
            " component..."
        )
        logger.debug(f"... to '{value}'.")
        self.tl_component.comments = value

    @property
    def formal_function(self):
        return self.tl_component.formal_function

    @formal_function.setter
    def formal_function(self, value):
        logger.debug(
            f"{self} is setting the value of attribute 'formal_function' of its"
            " timeline component..."
        )
        logger.debug(f"... to '{value}'.")
        self.tl_component.formal_function = value

    @property
    def formal_type(self):
        return self.tl_component.formal_type

    @formal_type.setter
    def formal_type(self, value):
        logger.debug(
            f"{self} is setting the value of attribute 'formal_type' of its timeline"
            " component..."
        )
        logger.debug(f"... to '{value}'.")
        self.tl_component.formal_type = value

    @property
    def parent(self):
        return self.tl_component.parent

    @property
    def children(self):
        return self.tl_component.children

    @property
    def color(self):
        return self.tl_component.color

    # noinspection PyAttributeOutsideInit
    @color.setter
    def color(self, value):
        logger.debug(f"Setting {self} color to {value}")
        self.tl_component.color = value
        self.canvas.itemconfig(self.body_id, fill=value)

    @property
    def shaded_color(self):
        return tilia.utils.color.hex_to_shaded_hex(self.color)

    @property
    def full_name(self) -> str:
        partial_name = self.label if self.label else self.NAME_WHEN_UNLABELED

        next_parent = self.parent

        while next_parent:
            parent_name = (
                next_parent.label if next_parent.label else self.NAME_WHEN_UNLABELED
            )
            partial_name = parent_name + self.FULL_NAME_SEPARATOR + partial_name
            next_parent = next_parent.parent

        full_name = self.timeline_ui.name + self.FULL_NAME_SEPARATOR + partial_name

        return full_name

    def _setup_label(self):
        self.update_label_measures()

    def update_label_measures(self):
        """
        Calculates length of substrings of label and stores it in self.label_measures
        """
        tk_font = tk.font.Font()
        self.label_measures = [
            tk_font.measure(self.label[: i + 1]) for i in range(len(self.label))
        ]

    @staticmethod
    def get_default_color(level: int) -> str:
        logger.debug(f"Getting default color for level '{level}'")
        colors = settings.get("hierarchy_timeline", "hierarchy_default_colors")
        color = colors[level % len(colors)]
        logger.debug(f"Got color '{color}'")
        return color

    def _setup_color(self, color: str):
        logger.debug(f"Setting up unit color with {color=}")
        if not color:
            self._color = self.get_default_color(self.level)
        else:
            self._color = color

    def reset_color(self) -> None:
        self.color = self.get_default_color(self.level)

    # noinspection PyTypeChecker
    def update_color(self, prev_level: int, new_level: int) -> None:
        logger.debug("Updating unit ui color...")

        if self.color != self.get_default_color(prev_level):
            logger.debug("Unit has custom color, don't apply new level color.")
        else:
            logger.debug("Changing unit color to new level color.")
            self.color = self.get_default_color(new_level)

    @property
    def canvas_drawings_ids(self) -> list[int]:
        ids = [
            self.body_id,
            self.label_id,
            self.comments_ind_id,
            self.start_marker,
            self.end_marker,
        ]

        if self.pre_start_ind_id:
            ids += list(self.pre_start_ind_id)

        if self.post_end_ind_id:
            ids += list(self.post_end_ind_id)

        return ids

    def update_label(self):
        """
        Recalculates label widths and updates displayed label according
        to label attr of timeline component.
        """

        self.update_label_measures()
        self.canvas.itemconfig(self.label_id, text=self.display_label)

    def update_position(self):
        logger.debug(f"Updating {self} canvas drawings positions...")

        self.update_rectangle_position()
        self.update_comments_indicator_position()
        self.update_label_position()
        self.update_displayed_label()
        self.update_markers_position()
        self.update_pre_start_position()
        self.update_post_end_position()

    def update_rectangle_position(self):
        self.canvas.coords(
            self.body_id,
            *self.get_body_coords(),
        )

    def update_comments_indicator_position(self):
        self.canvas.coords(
            self.comments_ind_id,
            *self.get_comments_indicator_coords(),
        )

    def update_label_position(self):
        self.canvas.coords(self.label_id, *self.get_label_coords())

    def update_displayed_label(self):
        self.canvas.itemconfig(self.label_id, text=self.display_label)

    def update_markers_position(self):
        self.canvas.coords(self.start_marker, *self.get_marker_coords(Extremity.START))
        self.canvas.coords(self.end_marker, *self.get_marker_coords(Extremity.END))

    def update_pre_start_position(self):
        if self.has_pre_start and self.pre_start_ind_id:
            self.canvas.coords(
                self.pre_start_ind_id[0], *self.get_pre_start_indicator_vline_coords()
            )
            self.canvas.coords(
                self.pre_start_ind_id[1], *self.get_pre_start_indicator_hline_coords()
            )

    def update_post_end_position(self):
        if self.has_post_end and self.post_end_ind_id:
            self.canvas.coords(
                self.post_end_ind_id[0], *self.get_post_end_indicator_vline_coords()
            )
            self.canvas.coords(
                self.post_end_ind_id[1], *self.get_post_end_indicator_hline_coords()
            )

    def update_pre_start_existence(self):
        if not self.pre_start_ind_id and self.has_pre_start:
            self.pre_start_ind_id = self.draw_pre_start_indicator()
        elif self.pre_start_ind_id and not self.has_pre_start:
            self.delete_pre_start_indicator()

    def update_post_end_existence(self):
        if not self.post_end_ind_id and self.has_post_end:
            self.post_end_ind_id = self.draw_post_end_indicator()
        elif self.post_end_ind_id and not self.has_post_end:
            self.delete_post_end_indicator()

    def draw_body(self) -> int:
        coords = self.get_body_coords()
        logger.debug(f"Drawing hierarchy rectangle with {coords} ans {self.color=}")
        return self.canvas.create_rectangle(
            *coords,
            width=self.WIDTH,
            fill=self.color,
        )

    def draw_label(self):
        coords = self.get_label_coords()
        logger.debug(f"Drawing hierarchy label with {coords=} and {self.label=}")

        return self.canvas.create_text(*coords, text=self.display_label)

    def draw_comments_indicator(self) -> int:
        coords = self.get_comments_indicator_coords()
        logger.debug(
            f"Drawing hierarchy comments indicator with {coords=} and {self.comments=}"
        )
        return self.canvas.create_text(
            *self.get_comments_indicator_coords(),
            text=self.COMMENTS_INDICATOR_CHAR if self.comments else "",
        )

    def draw_pre_start_indicator(self) -> tuple[int, int] | None:
        vline_coords = self.get_pre_start_indicator_vline_coords()
        hline_coords = self.get_pre_start_indicator_hline_coords()

        vline_id = self.canvas.create_line(
            *vline_coords, tags=(CAN_DRAG_HORIZONTALLY, CURSOR_ARROWS), width=3
        )
        hline_id = self.canvas.create_line(*hline_coords, dash=(2, 2))

        return vline_id, hline_id

    def draw_post_end_indicator(self) -> tuple[int, int] | None:
        vline_coords = self.get_post_end_indicator_vline_coords()
        hline_coords = self.get_post_end_indicator_hline_coords()

        vline_id = self.canvas.create_line(
            *vline_coords, tags=(CAN_DRAG_HORIZONTALLY, CURSOR_ARROWS), width=3
        )
        hline_id = self.canvas.create_line(*hline_coords, dash=(2, 2))

        return vline_id, hline_id

    def draw_markers(self) -> tuple[int, int]:
        """If there are already markers at start or end position,
        uses them instead"""

        logger.debug("Drawing hierarchys markers...")

        start_marker = self.timeline_ui.get_markerid_at_x(self.start_x)
        if not start_marker:
            logger.debug(f"No marker at start_x '{self.start_x}'. Drawing new marker.")
            start_marker = self.draw_marker(Extremity.START)
        else:
            logger.debug(f"Got existing marker '{start_marker}' as start marker.")
            self.canvas.tag_raise(start_marker, self.body_id)

        end_marker = self.timeline_ui.get_markerid_at_x(self.end_x)
        if not end_marker:
            logger.debug(f"No marker at end_x '{self.start_x}'. Drawing new marker.")
            end_marker = self.draw_marker(Extremity.END)
        else:
            logger.debug(f"Got existing marker '{end_marker}' as end marker.")
            self.canvas.tag_raise(end_marker, self.body_id)

        return start_marker, end_marker

    def draw_marker(self, marker_extremity: Extremity):
        return self.canvas.create_rectangle(
            *self.get_marker_coords(marker_extremity),
            outline="black",
            width=self.MARKER_OUTLINE_WIDTH,
            fill="black",
            tags=(CAN_DRAG_HORIZONTALLY, CURSOR_ARROWS),
        )

    def delete_pre_start_indicator(self) -> None:
        self.canvas.delete(*self.pre_start_ind_id)
        self.pre_start_ind_id = None

    def delete_post_end_indicator(self) -> None:
        self.canvas.delete(*self.post_end_ind_id)
        self.post_end_ind_id = None

    def get_pre_start_indicator_vline_coords(self):
        _, body_y0, _, body_y1 = self.get_body_coords()
        body_mid_y = (body_y0 + body_y1) // 2
        segment_height = 7

        x = self.pre_start_x
        y0 = body_mid_y - segment_height
        y1 = body_mid_y + segment_height + 1  # why do we need this + 1

        return x, y0, x, y1

    def get_pre_start_indicator_hline_coords(self):
        _, body_y0, _, body_y1 = self.get_body_coords()

        x0 = self.pre_start_x
        y = (body_y0 + body_y1) // 2
        x1 = self.start_x + self.XOFFSET

        return x0, y, x1, y

    def get_post_end_indicator_vline_coords(self):
        _, body_y0, _, body_y1 = self.get_body_coords()
        body_mid_y = (body_y0 + body_y1) // 2
        segment_height = 7

        x = self.post_end_x
        y0 = body_mid_y - segment_height
        y1 = body_mid_y + segment_height + 1  # why do we need this + 1

        return x, y0, x, y1

    def get_post_end_indicator_hline_coords(self):
        _, body_y0, _, body_y1 = self.get_body_coords()

        x0 = self.end_x + self.XOFFSET
        y = (body_y0 + body_y1) // 2
        x1 = self.post_end_x

        return x0, y, x1, y

    def get_unit_coords(self):
        tl_height = self.timeline_ui.height

        x0 = self.start_x + self.XOFFSET
        y0 = (
                tl_height
                - self.YOFFSET
                - (self.BASE_HEIGHT + ((self.level - 1) * self.LVL_HEIGHT_INCR))
        )
        x1 = self.end_x - self.XOFFSET

        y1 = tl_height - self.YOFFSET
        return x0, y0, x1, y1

    def get_body_coords(self):
        tl_height = self.timeline_ui.height

        x0 = self.start_x + self.XOFFSET
        y0 = (
                tl_height
                - self.YOFFSET
                - (self.BASE_HEIGHT + ((self.level - 1) * self.LVL_HEIGHT_INCR))
        )
        x1 = self.end_x - self.XOFFSET

        y1 = tl_height - self.YOFFSET
        return x0, y0, x1, y1

    def get_comments_indicator_coords(self):
        _, y0, x1, _ = self.get_body_coords()

        return (
            x1 + self.COMMENTS_INDICATOR_XOFFSET,
            y0 + self.COMMENTS_INDICATOR_YOFFSET,
        )

    def get_label_coords(self):
        x0, y0, x1, _ = self.get_body_coords()
        return (x0 + x1) / 2, y0 + self.LABEL_YOFFSET

    @log_object_deletion
    def delete(self):
        logger.debug(f"Deleting rectangle '{self.body_id}'")
        self.canvas.delete(self.body_id)
        logger.debug(f"Deleting label '{self.label_id}'")
        self.canvas.delete(self.label_id)
        logger.debug(f"Deleting comments indicator '{self.comments_ind_id}'")
        self.canvas.delete(self.comments_ind_id)
        self._delete_markers_if_not_shared()
        stop_listening_to_all(self)

    def get_marker_coords(
            self, marker_extremity: Extremity
    ) -> tuple[float, float, float, float]:
        draw_h = self.timeline_ui.height - self.MARKER_YOFFSET

        if marker_extremity == Extremity.START:
            marker_x = self.start_x
        elif marker_extremity == Extremity.END:
            marker_x = self.end_x
        else:
            raise ValueError(
                f"Can't create marker: Invalid marker extremity '{marker_extremity}"
            )

        return (
            marker_x - (self.MARKER_WIDTH / 2),
            draw_h - self.MARKER_LINE_HEIGHT,
            marker_x + (self.MARKER_WIDTH / 2),
            draw_h,
        )

    MIN_DRAG_GAP = 4
    DRAG_PROXIMITY_LIMIT = MARKER_WIDTH / 2 + MIN_DRAG_GAP

    @property
    def selection_triggers(self) -> tuple[int, ...]:
        return self.body_id, self.label_id, self.comments_ind_id

    @property
    def left_click_triggers(self) -> list[int]:
        triggers = [self.start_marker, self.end_marker]

        if self.pre_start_ind_id:
            triggers += list(self.pre_start_ind_id)

        if self.post_end_ind_id:
            triggers += list(self.post_end_ind_id)

        return triggers

    def on_left_click(self, id: int) -> None:
        if id in (self.start_marker, self.end_marker):
            self.start_marker_drag(id)
        elif self.pre_start_ind_id and id in self.pre_start_ind_id:
            self.start_pre_start_drag()
        elif self.post_end_ind_id and id in self.post_end_ind_id:
            self.start_post_end_drag()

    @property
    def double_left_click_triggers(self) -> tuple[int, ...]:
        return self.body_id, self.comments_ind_id, self.label_id

    def on_double_left_click(self, _) -> None:
        post(Post.PLAYER_REQUEST_TO_SEEK, self.seek_time)

    @property
    def right_click_triggers(self) -> tuple[int, ...]:
        return self.body_id, self.label_id, self.comments_ind_id

    def on_right_click(self, x: int, y: int, _) -> None:
        options = self.DEFAULT_RIGHT_CLICK_OPTIONS.copy()

        if not self.has_pre_start:
            options.insert(6, ("Add pre-start...", RightClickOption.ADD_PRE_START))

        if not self.has_post_end:
            options.insert(6, ("Add post-end...", RightClickOption.ADD_POST_END))

        self.timeline_ui.display_right_click_menu_for_element(x, y, options)

        self.timeline_ui.listen_for_uielement_rightclick_options(self)

    def _get_extremity_from_marker_id(self, marker_id: int):
        if marker_id == self.start_marker:
            return Extremity.START
        elif marker_id == self.end_marker:
            return Extremity.END
        else:
            raise ValueError(
                f"Can't get extremity: '{marker_id} is not marker id in {self}"
            )

    def make_marker_drag_data(self, extremity: Extremity):
        logger.debug(f"{self} is preparing to drag {extremity} marker...")

    def start_marker_drag(self, marker_id: int) -> None:
        self.drag_extremity = self._get_extremity_from_marker_id(marker_id)
        min_x, max_x = self.get_drag_limit(self.drag_extremity)

        DragManager(
            get_min_x=lambda: min_x,
            get_max_x=lambda: max_x,
            before_each=self.before_each_drag,
            after_each=self.after_each_drag,
            on_release=self.on_drag_end,
        )

    def get_reference_x_for_drag(self, extremity: Extremity):
        logger.debug(f"Getting drag limitis for {extremity} marker.")

        if extremity == Extremity.START:
            reference_x = self.start_x
        elif extremity == Extremity.END:
            reference_x = self.end_x
        else:
            raise ValueError(f"Extremity must be StartOrEnd. Got {extremity}")

        return reference_x

    def get_drag_limit(self, extremity: Extremity) -> tuple[int, int]:
        reference_x = self.get_reference_x_for_drag(extremity)
        prev_mrk_x = self.timeline_ui.get_previous_marker_x_by_x(reference_x)
        nxt_mrk_x = self.timeline_ui.get_next_marker_x_by_x(reference_x)

        min_x = prev_mrk_x + self.DRAG_PROXIMITY_LIMIT if prev_mrk_x else get(Get.LEFT_MARGIN_X)
        max_x = nxt_mrk_x - self.DRAG_PROXIMITY_LIMIT if nxt_mrk_x else get(Get.RIGHT_MARGIN_X)

        return min_x, max_x

    def before_each_drag(self):
        if not self.dragged:
            post(Post.ELEMENT_DRAG_START)
            self.dragged = True

    def after_each_drag(self, x: int) -> None:
        # update timeline component value
        setattr(
            self.tl_component,
            self.drag_extremity.value,
            coords.get_time_by_x(x),
        )
        self.update_position()

    def on_drag_end(self):
        if self.dragged:
            drag_x = getattr(self, self.drag_extremity.value)
            post(
                Post.REQUEST_RECORD_STATE,
                "hierarchy drag",
                no_repeat=True,
                repeat_identifier=f'{self.timeline_ui}_drag_to_{drag_x}',
            )
            post(Post.ELEMENT_DRAG_END)
            self.dragged = False
            self.drag_extremity = None

        if self.pre_start_ind_id:
            self.delete_pre_start_indicator()

        if self.post_end_ind_id:
            self.delete_post_end_indicator()

    def start_pre_start_drag(self) -> None:
        self.drag_extremity = Extremity.PRE_START
        post(Post.ELEMENT_DRAG_START)
        DragManager(
            get_min_x=lambda: get(Get.LEFT_MARGIN_X),
            get_max_x=lambda: self.start_x,
            before_each=self.before_each_drag,
            after_each=self.after_each_frame_drag,
            on_release=self.on_frame_drag_end,
        )

    def start_post_end_drag(self) -> None:
        self.drag_extremity = Extremity.POST_END
        post(Post.ELEMENT_DRAG_START)
        DragManager(
            get_min_x=lambda: self.end_x,
            get_max_x=lambda: get(Get.RIGHT_MARGIN_X),
            before_each=self.before_each_drag,
            after_each=self.after_each_frame_drag,
            on_release=self.on_frame_drag_end,
        )

    def after_each_frame_drag(self, x: int):
        # update timeline component value
        setattr(
            self.tl_component,
            self.drag_extremity.value,
            coords.get_time_by_x(x),
        )
        self.update_position()

    def on_frame_drag_end(self):
        if self.dragged:
            post(Post.REQUEST_RECORD_STATE, f"hierarchy {self.drag_extremity} drag")
            post(Post.ELEMENT_DRAG_END)
            self.dragged = False
            self.drag_extremity = None

    def on_select(self) -> None:
        self.display_as_selected()

    def on_deselect(self) -> None:
        self.display_as_deselected()

    def display_as_selected(self) -> None:
        self.canvas.itemconfig(
            self.body_id, fill=self.shaded_color, width=1, outline="black"
        )
        self.update_pre_start_existence()
        self.update_post_end_existence()

    def display_as_deselected(self) -> None:
        self.canvas.itemconfig(self.body_id, fill=self.color, width=0, outline="black")
        if self.pre_start_ind_id:
            self.delete_pre_start_indicator()

        if self.post_end_ind_id:
            self.delete_post_end_indicator()

    def marker_is_shared(self, marker_id: int) -> bool:
        units_with_marker = self.timeline_ui.get_units_using_marker(marker_id)
        if len(units_with_marker) > 1:
            return True
        else:
            return False

    def request_delete_to_component(self):
        self.tl_component.receive_delete_request_from_ui()

    def _delete_markers_if_not_shared(self) -> None:
        logger.debug("Deleting markers if they aren't shared...")

        if not self.marker_is_shared(self.start_marker):
            logger.debug(f"Deleting start marker '{self.start_marker}'")
            self.canvas.delete(self.start_marker)
        else:
            logger.debug(
                f"Start marker '{self.start_marker}' is shared, will not delete"
            )

        if not self.marker_is_shared(self.end_marker):
            logger.debug(f"Deleting end marker '{self.end_marker}'")
            self.canvas.delete(self.end_marker)
        else:
            logger.debug(f"End marker '{self.end_marker}' is shared, will not delete")

    @property
    def start_and_end_formatted(self) -> str:
        return (
            f"{format_media_time(self.tl_component.start)} /"
            f" {format_media_time(self.tl_component.end)}"
        )

    @property
    def length_formatted(self) -> str:
        return format_media_time(self.tl_component.end - self.tl_component.start)

    @property
    def pre_start_formatted(self) -> str:
        return format_media_time(self.pre_start)

    @property
    def post_end_formatted(self) -> str:
        return format_media_time(self.post_end)

    @property
    def inspector_pre_start_post_end(self):
        if not self.has_pre_start and not self.has_post_end:
            return HIDE_FIELD
        elif self.has_pre_start and self.has_post_end:
            return f"{self.pre_start_formatted} / {self.post_end_formatted}"
        elif self.has_pre_start:
            return f"{self.pre_start_formatted} / -"
        else:
            return f"- / {self.post_end_formatted}"

    def get_inspector_dict(self) -> dict:
        return {
            "Label": self.label,
            "Start / end": self.start_and_end_formatted,
            "Pre-start / post-end": self.inspector_pre_start_post_end,
            "Length": self.length_formatted,
            "Formal type": self.tl_component.formal_type,
            "Formal function": self.tl_component.formal_function,
            "Comments": self.tl_component.comments,
        }
