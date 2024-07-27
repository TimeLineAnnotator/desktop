"""
Defines the ui corresponding to a Hierarchy object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPen, QFont, QFontMetrics, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
)

from .context_menu import HierarchyContextMenu
from .drag import start_drag
from .extremity import Extremity
from .handles import HierarchyBodyHandle, HierarchyFrameHandle
from ..cursors import CursorMixIn
from ... import coords
from ...color import get_tinted_color, get_untinted_color
from ...consts import TINT_FACTOR_ON_SELECTION
from ...windows.inspect import HIDE_FIELD, InspectRowKind

if TYPE_CHECKING:
    from .timeline import HierarchyTimelineUI

import tilia.ui.format

from tilia.requests import (
    Post,
    post,
    stop_listening_to_all,
    get,
    Get,
)
from tilia.ui.timelines.copy_paste import CopyAttributes
from tilia.settings import settings

from tilia.ui.timelines.base.element import TimelineUIElement


class HierarchyUI(TimelineUIElement):
    Y_OFFSET = 0
    X_OFFSET = 1

    LABEL_BOTTOM_MARGIN = 10

    HANDLE_Y_MARGIN = 0
    HANDLE_WIDTH = 2

    MARKER_OUTLINE_WIDTH = 0

    INSPECTOR_FIELDS = [
        ("Label", InspectRowKind.SINGLE_LINE_EDIT, None),
        ("Start / end", InspectRowKind.LABEL, None),
        ("Start / end (metric)", InspectRowKind.LABEL, None),
        ("Pre-start / post-end", InspectRowKind.LABEL, None),
        ("Length", InspectRowKind.LABEL, None),
        ("Formal type", InspectRowKind.SINGLE_LINE_EDIT, None),
        ("Formal function", InspectRowKind.SINGLE_LINE_EDIT, None),
        ("Comments", InspectRowKind.MULTI_LINE_EDIT, None),
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

    NAME_WHEN_UNLABELED = "Unnamed"
    FULL_NAME_SEPARATOR = "-"

    UPDATE_TRIGGERS = [
        "start",
        "end",
        "pre_start",
        "post_end",
        "label",
        "level",
        "comments",
        "color",
    ]
    CONTEXT_MENU_CLASS = HierarchyContextMenu

    def __init__(
        self,
        id: int,
        timeline_ui: HierarchyTimelineUI,
        scene: QGraphicsScene,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)

        self.previous_width = 0
        self.timeline_ui = timeline_ui
        self.scene = scene

        self.label_substrings_widths: list[int] = []

        self._setup_body()
        self._setup_label()
        self._setup_comments_icon()
        self._setup_loop_icon()
        self._setup_body_handles()
        self._setup_frame_handles()

        self.dragged = False
        self.drag_extremity = None
        self.drag_manager = None

    @property
    def base_height(self):
        return settings.get("hierarchy_timeline", "base_height")

    @property
    def x_increment_per_lvl(self):
        return settings.get("hierarchy_timeline", "level_height_diff")

    @property
    def handle_height(self):
        return settings.get("hierarchy_timeline", "divider_height")

    @property
    def colors(self):
        return settings.get("hierarchy_timeline", "default_colors")

    @property
    def start_x(self):
        return coords.get_x_by_time(self.get_data("start"))

    @property
    def end_x(self):
        return coords.get_x_by_time(self.get_data("end"))

    @property
    def has_pre_start(self):
        return self.get_data("pre_start") != self.get_data("start")

    @property
    def has_post_end(self):
        return self.get_data("post_end") != self.get_data("end")

    @property
    def pre_start_x(self):
        return coords.get_x_by_time(self.get_data("pre_start"))

    @property
    def post_end_x(self):
        return coords.get_x_by_time(self.get_data("post_end"))

    @property
    def frame_handle_y(self):
        return self.timeline_ui.get_data("height") - (
            self.base_height + (self.get_data("level") - 1.5) * self.x_increment_per_lvl
        )

    @property
    def ui_color(self):
        base_color = self.get_data("color") or self.level_color
        return (
            base_color
            if not self.is_selected()
            else get_tinted_color(base_color, TINT_FACTOR_ON_SELECTION)
        )

    @property
    def level_color(self):
        return self.colors[(self.get_data("level") - 1) % len(self.colors)]

    @property
    def seek_time(self):
        return self.get_data("pre_start")

    @property
    def cropped_label(self):
        """
        Returns largest substring of self.label that fits inside body
        """

        if not self.get_data("label"):
            return ""

        max_width = self.end_x - self.start_x

        for i, width in enumerate(self.label_substrings_widths):
            if width > max_width:
                return self.get_data("label")[:i]

        return self.get_data("label")

    @property
    def full_name(self) -> str:
        partial_name = self.get_data("label") or self.NAME_WHEN_UNLABELED

        next_parent = self.get_data("parent")

        while next_parent:
            parent_name = next_parent.get_data("label") or self.NAME_WHEN_UNLABELED
            partial_name = parent_name + self.FULL_NAME_SEPARATOR + partial_name
            next_parent = next_parent.parent

        full_name = (
            self.timeline_ui.get_data("name") + self.FULL_NAME_SEPARATOR + partial_name
        )

        return full_name

    def child_items(self):
        return [
            self.body,
            self.label,
            self.comments_icon,
            self.loop_icon,
            self.start_handle,
            self.end_handle,
            self.pre_start_handle,
            self.pre_start_handle.vertical_line,
            self.pre_start_handle.horizontal_line,
            self.post_end_handle,
            self.post_end_handle.vertical_line,
            self.post_end_handle.horizontal_line,
        ]

    def update_label_substrings_widths(self):
        """
        Calculates length of substrings of label and stores it in self.label_measures
        """
        font_metrics = QFontMetrics(QFont("Arial", 10))
        self.label_substrings_widths = [
            font_metrics.horizontalAdvance(self.get_data("label")[: i + 1])
            for i in range(len(self.get_data("label")))
        ]

    def update_color(self):
        self.body.set_fill(self.ui_color)

    def update_comments(self):
        self.comments_icon.setVisible(bool(self.get_data("comments")))

    def update_label(self):
        self.update_label_substrings_widths()
        self.label.set_text(self.cropped_label)
        self.update_label_position()

    def update_level(self):
        self.update_position()
        self.update_color()

    def update_end(self):
        self.update_position()

    def update_start(self):
        self.update_position()

    def update_pre_start(self):
        self.update_frame_handle_position(Extremity.PRE_START)
        if self.is_selected():
            self.update_frame_handle_visibility(Extremity.PRE_START)

    def update_post_end(self):
        self.update_frame_handle_position(Extremity.POST_END)
        if self.is_selected():
            self.update_frame_handle_visibility(Extremity.POST_END)

    def update_position(self):
        self.update_body_position()
        self.update_comments_icon_position()
        self.update_loop_icon_position()
        self.update_label_position()
        self.update_label()
        self.update_body_handles_position()
        self.update_frame_handles_position()

    def update_body_position(self):
        self.body.set_position(
            self.get_data("level"),
            self.start_x,
            self.end_x,
            self.timeline_ui.get_data("height"),
        )

    def update_comments_icon_position(self):
        self.comments_icon.set_position(
            self.end_x, self.timeline_ui.get_data("height"), self.get_data("level")
        )

    def update_loop_icon_position(self):
        self.loop_icon.set_position(
            self.start_x, self.timeline_ui.get_data("height"), self.get_data("level")
        )

    def update_label_position(self):
        self.label.set_position(
            (self.start_x + self.end_x) / 2,
            self.timeline_ui.get_data("height"),
            self.get_data("level"),
        )

    def update_body_handles_position(self):
        for extremity in [Extremity.START, Extremity.END]:
            self.extremity_to_handle(extremity).set_position(
                self.extremity_to_x(extremity),
                self.HANDLE_WIDTH,
                self.handle_height,
                self.timeline_ui.get_data("height"),
                self.HANDLE_Y_MARGIN,
            )

    def update_frame_handles_position(self):
        self.update_frame_handle_position(Extremity.PRE_START)
        self.update_frame_handle_position(Extremity.POST_END)

    def update_frame_handle_position(self, extremity: Extremity):
        if extremity == Extremity.PRE_START:
            self.pre_start_handle.set_position(
                self.start_x, self.pre_start_x, self.frame_handle_y
            )
        elif extremity == Extremity.POST_END:
            self.post_end_handle.set_position(
                self.end_x, self.post_end_x, self.frame_handle_y
            )
        else:
            raise ValueError("Unrecognized extremity")

    def update_frame_handles_visibility(self):
        self.update_frame_handle_visibility(Extremity.PRE_START)
        self.update_frame_handle_visibility(Extremity.POST_END)

    def update_frame_handle_visibility(self, extremity: Extremity):
        handle, exists = {
            Extremity.PRE_START: (self.pre_start_handle, self.has_pre_start),
            Extremity.POST_END: (self.post_end_handle, self.has_post_end),
        }[extremity]

        if not handle.isVisible() and exists:
            handle.setVisible(True)
        elif handle.isVisible() and not exists:
            handle.setVisible(False)

    def _setup_body(self):
        self.body = HierarchyBody(
            self.get_data("level"),
            self.start_x,
            self.end_x,
            self.timeline_ui.get_data("height"),
            self.ui_color,
        )
        self.scene.addItem(self.body)

    def _setup_label(self):
        self.update_label_substrings_widths()
        self.label = HierarchyLabel(
            (self.start_x + self.end_x) / 2,
            self.timeline_ui.get_data("height"),
            self.get_data("level"),
            self.cropped_label,
        )
        self.scene.addItem(self.label)

    def _setup_comments_icon(self):
        self.comments_icon = HierarchyCommentsIcon(
            self.end_x, self.timeline_ui.get_data("height"), self.get_data("level")
        )
        self.scene.addItem(self.comments_icon)
        self.comments_icon.setVisible(bool(self.get_data("comments")))

    def _setup_loop_icon(self):
        self.loop_icon = HierarchyLoopIcon(
            self.start_x, self.timeline_ui.get_data("height"), self.get_data("level")
        )
        self.scene.addItem(self.loop_icon)
        self.loop_icon.setVisible(False)

    def _setup_body_handles(self):
        """If there are already markers at start or end position,
        uses them instead"""

        self.start_handle = self.timeline_ui.get_handle_by_x(self.start_x)
        if not self.start_handle:
            self.start_handle = self._setup_handle(Extremity.START)
            self.scene.addItem(self.start_handle)

        self.end_handle = self.timeline_ui.get_handle_by_x(self.end_x)
        if not self.end_handle:
            self.end_handle = self._setup_handle(Extremity.END)
            self.scene.addItem(self.end_handle)

    def _setup_frame_handles(self):
        y = self.frame_handle_y
        self.pre_start_handle = HierarchyFrameHandle(self.start_x, self.pre_start_x, y)
        self.scene.addItem(self.pre_start_handle)

        self.post_end_handle = HierarchyFrameHandle(self.end_x, self.post_end_x, y)
        self.scene.addItem(self.post_end_handle)

    def extremity_to_handle(
        self, extremity: Extremity
    ) -> HierarchyBodyHandle | HierarchyFrameHandle:
        try:
            return {
                Extremity.START: self.start_handle,
                Extremity.END: self.end_handle,
                Extremity.PRE_START: self.pre_start_handle,
                Extremity.POST_END: self.post_end_handle,
            }[extremity]
        except KeyError:
            raise ValueError("Unrecognized extremity")

    @staticmethod
    def frame_to_body_extremity(
        extremity: Literal[Extremity.PRE_START, Extremity.POST_END]
    ):
        try:
            return {
                Extremity.PRE_START: Extremity.START,
                Extremity.POST_END: Extremity.END,
            }[extremity]
        except KeyError:
            raise ValueError("Unrecognized extremity")

    def handle_to_extremity(self, handle: HierarchyBodyHandle | HierarchyFrameHandle):
        try:
            return {
                self.start_handle: Extremity.START,
                self.end_handle: Extremity.END,
                self.pre_start_handle: Extremity.PRE_START,
                self.post_end_handle: Extremity.POST_END,
            }[handle]
        except KeyError:
            raise ValueError(f"{handle} if not a handle of {self}")

    def extremity_to_x(self, extremity: Extremity):
        if extremity == Extremity.START:
            return self.start_x
        elif extremity == Extremity.END:
            return self.end_x
        else:
            raise ValueError("Unrecognized extremity")

    def _setup_handle(self, extremity: Extremity):
        return HierarchyBodyHandle(
            self.extremity_to_x(extremity),
            self.HANDLE_WIDTH,
            self.handle_height,
            self.timeline_ui.get_data("height"),
            self.HANDLE_Y_MARGIN,
        )

    def selection_triggers(self):
        return self.body, self.label, self.comments_icon

    def left_click_triggers(self):
        triggers = [
            self.start_handle,
            self.end_handle,
            self.pre_start_handle.vertical_line,
            self.post_end_handle.vertical_line,
        ]

        return triggers

    def on_left_click(
        self, item: HierarchyBodyHandle | HierarchyFrameHandle.VLine
    ) -> None:
        start_drag(self, item)

    def double_left_click_triggers(self):
        return [self.body, self.comments_icon, self.label] + self.left_click_triggers()

    def on_double_left_click(self, _) -> None:
        if self.drag_manager:
            self.drag_manager.on_release()
            self.drag_manager = None
        post(Post.PLAYER_SEEK, self.seek_time)

    def right_click_triggers(self):
        return self.body, self.label, self.comments_icon

    def on_select(self) -> None:
        self.body.on_select()

        if not self.selected_ascendants():
            self.update_frame_handle_visibility(Extremity.PRE_START)
            self.update_frame_handle_visibility(Extremity.POST_END)

        if selected_descendants := self.selected_descendants():
            for ui in selected_descendants:
                ui.pre_start_handle.setVisible(False)
                ui.post_end_handle.setVisible(False)
        post(Post.HIERARCHY_SELECTED)

    def on_deselect(self) -> None:
        self.body.on_deselect()
        self.pre_start_handle.setVisible(False)
        self.post_end_handle.setVisible(False)
        post(Post.HIERARCHY_DESELECTED)

    def selected_ascendants(self) -> list[HierarchyUI]:
        """Returns hierarchies in the same branch that
        are both selected and higher-leveled than self"""
        uis_at_start = self.timeline_ui.get_elements_by_attr("start_x", self.start_x)
        selected_uis = self.timeline_ui.selected_elements

        return [
            ui
            for ui in uis_at_start
            if ui in selected_uis and ui.get_data("level") > self.get_data("level")
        ]

    def selected_descendants(self) -> list[HierarchyUI]:
        """Returns hierarchies in the same branch that are both
        selected and lower-leveled than self"""
        uis_at_start = self.timeline_ui.get_elements_by_attr("start_x", self.start_x)
        selected_uis = self.timeline_ui.selected_elements

        return [
            ui
            for ui in uis_at_start
            if ui in selected_uis and ui.get_data("level") < self.get_data("level")
        ]

    def is_handle_shared(self, handle: HierarchyBodyHandle) -> bool:
        units_with_marker = self.timeline_ui.get_units_sharing_handle(handle)
        if len(units_with_marker) > 1:
            return True
        else:
            return False

    def _delete_handles_if_not_shared(self) -> None:
        for handle in [self.start_handle, self.end_handle]:
            if not self.is_handle_shared(handle):
                self.scene.removeItem(handle)

    def on_loop_set(self, is_looping: bool) -> None:
        self.loop_icon.setVisible(is_looping)

    @property
    def start_and_end_formatted(self) -> str:
        return (
            f"{tilia.ui.format.format_media_time(self.get_data('start'))} /"
            f" {tilia.ui.format.format_media_time(self.get_data('end'))}"
        )

    @property
    def length_formatted(self) -> str:
        return tilia.ui.format.format_media_time(
            self.get_data("end") - self.get_data("start")
        )

    @property
    def pre_start_formatted(self) -> str:
        return tilia.ui.format.format_media_time(self.get_data("pre_start"))

    @property
    def post_end_formatted(self) -> str:
        return tilia.ui.format.format_media_time(self.get_data("post_end"))

    @property
    def frame_times_for_inspector(self):
        if not self.has_pre_start and not self.has_post_end:
            return HIDE_FIELD
        elif self.has_pre_start and self.has_post_end:
            return f"{self.pre_start_formatted} / {self.post_end_formatted}"
        elif self.has_pre_start:
            return f"{self.pre_start_formatted} / -"
        else:
            return f"- / {self.post_end_formatted}"

    @property
    def start_metric_position(self):
        return get(Get.METRIC_POSITION, self.get_data("start"))

    @property
    def end_metric_position(self):
        return get(Get.METRIC_POSITION, self.get_data("end"))

    @property
    def metric_position_formatted(self):
        start_measure, start_beat = self.start_metric_position
        end_measure, end_beat = self.end_metric_position
        if start_measure is None:
            return "-"
        return f"{start_measure}.{start_beat} / {end_measure}.{end_beat}"

    def get_inspector_dict(self) -> dict:
        data = {
            "Label": self.get_data("label"),
            "Start / end": self.start_and_end_formatted,
            "Pre-start / post-end": self.frame_times_for_inspector,
            "Length": self.length_formatted,
            "Formal type": self.get_data("formal_type"),
            "Formal function": self.get_data("formal_function"),
            "Comments": self.get_data("comments"),
        }

        if self.start_metric_position:
            data["Start / end (metric)"] = self.metric_position_formatted

        return data

    def delete(self):
        for item in self.child_items():
            if item.parentItem():
                continue  # item will be removed with parent
            if isinstance(item, HierarchyBodyHandle) and self.is_handle_shared(item):
                continue
            self.scene.removeItem(item)

        stop_listening_to_all(self)


class HierarchyBody(CursorMixIn, QGraphicsRectItem):
    def __init__(
        self,
        level: int,
        start_x: float,
        end_x: float,
        tl_height: float,
        color: str,
    ):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.set_position(level, start_x, end_x, tl_height)
        self.set_pen_style_no_pen()
        self.set_fill(color)

    @property
    def base_height(self):
        return settings.get("hierarchy_timeline", "base_height")

    @property
    def x_increment_per_lvl(self):
        return settings.get("hierarchy_timeline", "level_height_diff")

    def set_fill(self, color: str):
        self.setBrush(QColor(color))

    def set_pen_style_solid(self):
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.SolidLine)
        self.setPen(pen)

    def set_pen_style_no_pen(self):
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.NoPen)
        self.setPen(pen)

    def set_position(self, level: int, start_x: float, end_x: float, tl_height: float):
        self.setRect(self.get_rect(level, start_x, end_x, tl_height))
        self.setZValue(-level)

    def on_select(self):
        self.set_pen_style_solid()
        self.setBrush(
            QColor(get_tinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )

    def on_deselect(self):
        self.set_pen_style_no_pen()
        self.setBrush(
            QColor(get_untinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )

    def get_rect(self, level: int, start_x: float, end_x: float, tl_height: float):
        x0 = start_x + HierarchyUI.X_OFFSET
        y0 = (
            tl_height
            - HierarchyUI.Y_OFFSET
            - (self.base_height + ((level - 1) * self.x_increment_per_lvl))
        )
        x1 = end_x - HierarchyUI.X_OFFSET

        y1 = tl_height - HierarchyUI.Y_OFFSET
        return QRectF(QPointF(x0, y0), QPointF(x1, y1))


class HierarchyLabel(CursorMixIn, QGraphicsTextItem):
    def __init__(self, x: float, tl_height: int, level: int, text: str):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.setup_font()
        self.set_text(text)
        self.set_position(x, tl_height, level)

    @property
    def base_height(self):
        return settings.get("hierarchy_timeline", "base_height")

    @property
    def x_increment_per_lvl(self):
        return settings.get("hierarchy_timeline", "level_height_diff")

    def setup_font(self):
        font = QFont("Arial", 10)
        self.setFont(font)
        self.setDefaultTextColor(QColor("black"))

    def get_point(self, x: float, tl_height, level):
        x = x - self.boundingRect().width() / 2
        y = (
            tl_height
            - HierarchyUI.Y_OFFSET
            - (self.base_height + ((level - 1) * self.x_increment_per_lvl))
        )
        return QPointF(x, y)

    def set_position(self, x, tl_height, level):
        self.setPos(self.get_point(x, tl_height, level))
        self.setZValue(level + 1)

    def set_text(self, value: str):
        self.setPlainText(value)


class HierarchyCommentsIcon(CursorMixIn, QGraphicsTextItem):
    ICON = "💬"
    BOTTOM_MARGIN = 3
    LEFT_MARGIN = -15

    def __init__(self, end_x: float, tl_height: int, level: int):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.setup_font()
        self.setPlainText(self.ICON)
        self.set_position(end_x, tl_height, level)

    @property
    def base_height(self):
        return settings.get("hierarchy_timeline", "base_height")

    @property
    def x_increment_per_lvl(self):
        return settings.get("hierarchy_timeline", "level_height_diff")

    def setup_font(self):
        font = QFont("Arial", 6)
        self.setFont(font)
        self.setDefaultTextColor(QColor("black"))

    def get_point(self, end_x: float, tl_height, level):
        x = end_x + self.LEFT_MARGIN
        y = (
            tl_height
            - HierarchyUI.Y_OFFSET
            - (self.base_height + ((level - 1) * self.x_increment_per_lvl))
            - self.BOTTOM_MARGIN
        )
        return QPointF(x, y)

    def set_position(self, end_x, tl_height, level):
        self.setPos(self.get_point(end_x, tl_height, level))
        self.setZValue(level + 1)


class HierarchyLoopIcon(QGraphicsPixmapItem):
    ICON = str(Path("ui", "img", "loop15.png"))
    TOP_MARGIN = 1
    LEFT_MARGIN = 3

    def __init__(self, start_x: float, tl_height: int, level: int):
        super().__init__()
        self.setPixmap(QPixmap(self.ICON))
        self.set_position(start_x, tl_height, level)

    @property
    def base_height(self):
        return settings.get("hierarchy_timeline", "base_height")

    @property
    def x_increment_per_lvl(self):
        return settings.get("hierarchy_timeline", "level_height_diff")

    def get_point(self, start_x: float, tl_height, level):
        x = start_x + self.LEFT_MARGIN
        y = (
            tl_height
            - HierarchyUI.Y_OFFSET
            - (self.base_height + ((level - 1) * self.x_increment_per_lvl))
            + self.TOP_MARGIN
        )
        return QPointF(x, y)

    def set_position(self, start_x, tl_height, level):
        self.setPos(self.get_point(start_x, tl_height, level))
        self.setZValue(level + 1)
