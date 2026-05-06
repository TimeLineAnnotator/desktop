from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
)

from tilia.settings import settings
from tilia.ui.color import get_tinted_color, get_untinted_color
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.copy_paste import CopyAttributes
from tilia.ui.timelines.cursors import CursorMixIn
from tilia.ui.timelines.labels import elide_text
from tilia.ui.timelines.range.context_menu import RangeContextMenu
from tilia.ui.timelines.range.drag import start_body_drag, start_drag
from tilia.ui.timelines.range.handles import RangeBodyHandle, RangeFrameHandle
from tilia.ui.windows.inspect import InspectRowKind


class RangeUI(TimelineUIElement):
    CONTEXT_MENU_CLASS = RangeContextMenu

    INSPECTOR_FIELDS = [
        ("Label", InspectRowKind.SINGLE_LINE_EDIT, None),
        ("Start / end", InspectRowKind.LABEL, None),
        ("Length", InspectRowKind.LABEL, None),
        ("Pre-start / post-end", InspectRowKind.LABEL, None),
        ("Comments", InspectRowKind.MULTI_LINE_EDIT, None),
    ]

    FIELD_NAMES_TO_ATTRIBUTES = {
        "Label": "label",
        "Comments": "comments",
    }

    DEFAULT_COPY_ATTRIBUTES = CopyAttributes(
        values=["label", "color", "comments"],
        # `id` and `joined_right` go through context so paste can reconstruct
        # joins between pasted siblings.
        context=["start", "end", "id", "joined_right"],
    )

    UPDATE_TRIGGERS = [
        "start",
        "end",
        "row_id",
        "label",
        "color",
        "comments",
        "joined_right",
        "pre_start",
        "post_end",
    ]

    JOIN_SEPARATOR_INSET = 2  # px inset from row top/bottom

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._setup_body()
        self._setup_label()
        self._setup_handles()
        self._setup_frame_handles()
        self._setup_join_separator()
        self._setup_comments_icon()

        self.dragged = False
        self.drag_manager = None
        self.drag_extremity: str | None = None

    @property
    def seek_time(self) -> float:
        return self.get_data("start")

    @property
    def row_index(self) -> int | None:
        return self.timeline_ui.row_index(self.get_data("row_id"))

    @property
    def row_height(self) -> int:
        # Per-row height: each row may carry its own; rows without an
        # explicit height fall back to the timeline's default_row_height.
        row = self.timeline_ui.get_row_by_id(self.get_data("row_id"))
        return self.timeline_ui.row_height_for(row)

    @property
    def row_color(self) -> str | None:
        row = self.timeline_ui.get_row_by_id(self.get_data("row_id"))
        return row.color if row is not None else None

    @property
    def default_color(self) -> str:
        return settings.get("range_timeline", "default_range_color")

    @property
    def handle_color(self) -> str:
        return settings.get("range_timeline", "handle_color")

    @property
    def handle_width(self) -> int:
        return settings.get("range_timeline", "handle_width")

    @property
    def ui_color(self) -> str:
        base_color = self.get_data("color") or self.row_color or self.default_color
        return (
            base_color
            if not self.is_selected()
            else get_tinted_color(base_color, TINT_FACTOR_ON_SELECTION)
        )

    @property
    def pre_start_x(self) -> float:
        from tilia.ui.coords import time_x_converter

        return time_x_converter.get_x_by_time(self.get_data("pre_start"))

    @property
    def post_end_x(self) -> float:
        from tilia.ui.coords import time_x_converter

        return time_x_converter.get_x_by_time(self.get_data("post_end"))

    @property
    def has_pre_start(self) -> bool:
        return self.get_data("pre_start") != self.get_data("start")

    @property
    def has_post_end(self) -> bool:
        return self.get_data("post_end") != self.get_data("end")

    def update_position(self) -> None:
        if self.row_index is None:
            # The row this element references no longer exists.
            # This is a transient state during undo/redo; the element will
            # be deleted by the subsequent component-restoration step.
            return

        start_x = self.start_x
        end_x = self.end_x

        y = self.timeline_ui.row_y(self.row_index)

        self.body.set_position(start_x, end_x, y, self.row_height)
        self.label.set_position(
            start_x, end_x, y, self.row_height, self.timeline_ui.label_alignment
        )

        self.start_handle.set_position(
            start_x, self.handle_width, self.row_height, y + self.row_height
        )
        self.end_handle.set_position(
            end_x, self.handle_width, self.row_height, y + self.row_height
        )
        self._update_join_separator_position(end_x, y)
        self._update_frame_handles_geometry(start_x, end_x, y)
        self._update_comments_icon_position(start_x, end_x, y)

    def update_color(self) -> None:
        self.body.set_fill(self.ui_color)
        # Handle color is configured separately via the handle_color setting;
        # refresh both handles and re-apply join transparency in case the
        # underlying base color changed.
        self.start_handle.set_fill(self.handle_color)
        self.end_handle.set_fill(self.handle_color)
        self._update_handle_visibility()

    def update_label(self) -> None:
        self.label.set_text(self.get_data("label"))
        # The label x-position depends on the rendered text width under
        # center/right alignment, so it must be recomputed after a text
        # change. set_text alone leaves the label at its old x.
        self.label.set_position(
            self.start_x,
            self.end_x,
            self.timeline_ui.row_y(self.row_index),
            self.row_height,
            self.timeline_ui.label_alignment,
        )

    def update_start(self) -> None:
        self.update_position()

    def update_end(self) -> None:
        self.update_position()

    def update_row_id(self) -> None:
        self.update_position()
        self.update_color()  # Row ID change might change color

    def update_comments(self) -> None:
        self._update_comments_icon_visibility()

    def update_pre_start(self) -> None:
        self.update_position()
        self._update_frame_handle_visibility("pre_start")

    def update_post_end(self) -> None:
        self.update_position()
        self._update_frame_handle_visibility("post_end")

    def update_joined_right(self) -> None:
        # A joined_right change affects this range AND its partner (current or
        # previous). Refresh handle visibility timeline-wide so both ends of a
        # join transition correctly.
        for elem in self.timeline_ui:
            elem._update_handle_visibility()
        self._update_join_separator_visibility()

    def child_items(self) -> list[QGraphicsItem]:
        return [
            self.body,
            self.label,
            self.start_handle,
            self.end_handle,
            self.pre_start_handle,
            self.pre_start_handle.horizontal_line,
            self.pre_start_handle.vertical_line,
            self.post_end_handle,
            self.post_end_handle.horizontal_line,
            self.post_end_handle.vertical_line,
            self.join_separator,
            self.comments_icon,
        ]

    def _setup_comments_icon(self) -> None:
        # Small "💬" pip near the top-right of the body, shown only when
        # `comments` is non-empty and there's enough room. Mirrors the
        # hierarchy timeline.
        y = self.timeline_ui.row_y(self.row_index) if self.row_index is not None else 0
        self.comments_icon = RangeCommentsIcon(self.end_x, y, self.row_height)
        self.scene.addItem(self.comments_icon)
        self._update_comments_icon_visibility()

    def _update_comments_icon_position(
        self, start_x: float, end_x: float, y: float
    ) -> None:
        self.comments_icon.set_position(end_x, y, self.row_height)
        self._update_comments_icon_visibility()

    def _update_comments_icon_visibility(self) -> None:
        text_width = self.comments_icon.boundingRect().width()
        visible = (
            bool(self.get_data("comments"))
            and text_width < self.end_x - self.start_x
            and self.comments_icon.fits_in_height(self.row_height)
        )
        self.comments_icon.setVisible(visible)

    def _setup_frame_handles(self) -> None:
        # Whiskers indicating pre_start / post_end. Each is a dashed
        # horizontal line at the row's vertical centre with a small
        # vertical "grab" at the far end (the drag handle). Hidden by
        # default — shown on selection or when the always-show toggle
        # is enabled.
        y_mid = self._frame_handle_y()
        self.pre_start_handle = RangeFrameHandle(self.start_x, self.pre_start_x, y_mid)
        self.scene.addItem(self.pre_start_handle)

        self.post_end_handle = RangeFrameHandle(self.end_x, self.post_end_x, y_mid)
        self.scene.addItem(self.post_end_handle)

        self._update_frame_handles_visibility()

    def _frame_handle_y(self) -> float:
        if self.row_index is None:
            return 0.0
        return self.timeline_ui.row_y(self.row_index) + self.row_height / 2

    def _update_frame_handles_geometry(
        self, start_x: float, end_x: float, y: float
    ) -> None:
        y_mid = y + self.row_height / 2
        self.pre_start_handle.set_position(start_x, self.pre_start_x, y_mid)
        self.post_end_handle.set_position(end_x, self.post_end_x, y_mid)
        self._update_frame_handles_visibility()

    def _should_show_frame_handles(self) -> bool:
        if settings.get("range_timeline", "always_show_extensions"):
            return True
        return self.is_selected()

    def _update_frame_handle_visibility(self, extremity: str) -> None:
        handle = (
            self.pre_start_handle if extremity == "pre_start" else self.post_end_handle
        )
        exists = self.has_pre_start if extremity == "pre_start" else self.has_post_end
        handle.setVisible(exists and self._should_show_frame_handles())

    def _update_frame_handles_visibility(self) -> None:
        self._update_frame_handle_visibility("pre_start")
        self._update_frame_handle_visibility("post_end")

    def _setup_body(self) -> None:
        self.body = RangeBody(
            self.start_x,
            self.end_x,
            self.timeline_ui.row_y(self.row_index),
            self.row_height,
            self.ui_color,
        )
        self.scene.addItem(self.body)

    def _setup_label(self) -> None:
        self.label = RangeLabel(
            self.start_x,
            self.end_x,
            self.timeline_ui.row_y(self.row_index),
            self.row_height,
            self.get_data("label"),
            self.timeline_ui.label_alignment,
        )
        self.scene.addItem(self.label)

    def _setup_handles(self) -> None:
        y = self.timeline_ui.row_y(self.row_index) + self.row_height
        self.start_handle = RangeBodyHandle(
            self.start_x, self.handle_width, self.row_height, y, self.handle_color
        )
        self.end_handle = RangeBodyHandle(
            self.end_x, self.handle_width, self.row_height, y, self.handle_color
        )

        self.scene.addItem(self.start_handle)
        self.scene.addItem(self.end_handle)
        self._update_handle_visibility()

    def _update_handle_visibility(self) -> None:
        # Hide handles at joined edges so the dashed separator is visible.
        # The handles remain clickable for dragging the shared edge.
        has_outgoing_join = self.get_data("joined_right") is not None
        has_incoming_join = any(
            elem.id != self.id and elem.get_data("joined_right") == self.id
            for elem in self.timeline_ui
        )
        self.end_handle.set_transparent(has_outgoing_join)
        self.start_handle.set_transparent(has_incoming_join)

        # On file load, elements are created one at a time. If our partner was
        # created before us, its `has_incoming_join` check missed us and its
        # start_handle stayed opaque — covering the dashed separator. Refresh
        # it now that we know it's the right side of a join with us.
        if has_outgoing_join:
            partner = self.timeline_ui.id_to_element.get(self.get_data("joined_right"))
            if partner is not None and partner is not self:
                partner.start_handle.set_transparent(True)

    def _setup_join_separator(self) -> None:
        # A vertical dashed line drawn on the shared edge of two joined
        # ranges, indicating that they are joined (rather than merely
        # adjacent). Owned by the left range; visible only when this range
        # has a `joined_right` partner.
        self.join_separator = QGraphicsLineItem()
        pen = QPen(QColor("black"))
        pen.setWidth(1)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.join_separator.setPen(pen)
        self.join_separator.setZValue(20)  # above body, above handles
        self.join_separator.ignore_right_click = True
        self.scene.addItem(self.join_separator)
        self._update_join_separator_visibility()

    def _update_join_separator_visibility(self) -> None:
        is_joined = self.get_data("joined_right") is not None
        self.join_separator.setVisible(is_joined)
        if is_joined and self.row_index is not None:
            self._update_join_separator_position(
                self.end_x, self.timeline_ui.row_y(self.row_index)
            )

    def _update_join_separator_position(self, end_x: float, y: float) -> None:
        self.join_separator.setLine(
            end_x,
            y + self.JOIN_SEPARATOR_INSET,
            end_x,
            y + self.row_height - self.JOIN_SEPARATOR_INSET,
        )

    def selection_triggers(self) -> list[QGraphicsItem]:
        # Whisker V-lines are included so grabbing a whisker keeps the
        # range selected — otherwise on_left_click's deselect-all clears
        # the selection mid-drag and the whisker (visible only when
        # selected) vanishes from under the cursor.
        return [
            self.body,
            self.label,
            self.comments_icon,
            self.pre_start_handle.vertical_line,
            self.post_end_handle.vertical_line,
        ]

    def on_select(self) -> None:
        self.body.on_select()
        self._update_frame_handles_visibility()

    def on_deselect(self) -> None:
        self.body.on_deselect()
        self._update_frame_handles_visibility()

    def left_click_triggers(self) -> list[QGraphicsItem]:
        # The join separator sits on top of the shared edge (z=20). A click
        # exactly on it would otherwise miss both handles and fall through
        # to the timeline scene, starting a rubber-band selection. Treat a
        # click on the separator as a click on the end handle of this range
        # — its drag partner (this range's `joined_right`) gets picked up
        # by `start_drag` and both edges move together.
        # Body / label trigger a body drag (move the whole range).
        return [
            self.start_handle,
            self.end_handle,
            self.pre_start_handle.vertical_line,
            self.post_end_handle.vertical_line,
            self.join_separator,
            self.body,
            self.label,
            self.comments_icon,
        ]

    def double_left_click_triggers(self) -> list[QGraphicsItem]:
        return [self.body, self.label, self.comments_icon]

    def on_double_left_click(self, _: QGraphicsItem) -> None:
        # Single-click seeking is gated by `if_playing=False`, so seeking
        # during playback only happens through this double-click path.
        from tilia.ui import commands

        commands.execute("media.seek", self.seek_time)

    def handle_to_extremity(self, item: QGraphicsItem) -> str | None:
        if item is self.start_handle:
            return "start"
        elif item is self.end_handle or item is self.join_separator:
            return "end"
        elif item is self.pre_start_handle.vertical_line:
            return "pre_start"
        elif item is self.post_end_handle.vertical_line:
            return "post_end"
        return None

    def on_left_click(self, item: QGraphicsItem) -> None:
        if item is self.body or item is self.label or item is self.comments_icon:
            start_body_drag(self)
        else:
            start_drag(self, item)

    def get_inspector_dict(self) -> dict[str, Any]:
        import tilia.ui.format

        if not self.has_pre_start and not self.has_post_end:
            pre_post_value = "-"
        else:
            pre_str = (
                tilia.ui.format.format_media_time(self.get_data("pre_start"))
                if self.has_pre_start
                else "-"
            )
            post_str = (
                tilia.ui.format.format_media_time(self.get_data("post_end"))
                if self.has_post_end
                else "-"
            )
            pre_post_value = f"{pre_str} / {post_str}"

        return {
            "Label": self.get_data("label"),
            "Start / end": f"{tilia.ui.format.format_media_time(self.get_data('start'))} / {tilia.ui.format.format_media_time(self.get_data('end'))}",
            "Length": tilia.ui.format.format_media_time(
                self.get_data("end") - self.get_data("start")
            ),
            "Pre-start / post-end": pre_post_value,
            "Comments": self.get_data("comments"),
        }


class RangeBody(CursorMixIn, QGraphicsRectItem):
    def __init__(
        self, start_x: float, end_x: float, y: float, height: float, color: str
    ):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.set_position(start_x, end_x, y, height)
        self.set_pen_style_no_pen()
        self.set_fill(color)

    @property
    def alpha_(self) -> int:
        return settings.get("range_timeline", "range_alpha")

    def set_fill(self, color: str | QColor) -> None:
        color = QColor(color)
        color.setAlpha(self.alpha_)
        self.setBrush(color)

    def set_pen_style_no_pen(self) -> None:
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.NoPen)
        self.setPen(pen)

    def set_pen_style_solid(self) -> None:
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.SolidLine)
        self.setPen(pen)

    def set_position(
        self, start_x: float, end_x: float, y: float, height: float
    ) -> None:
        self.setRect(QRectF(QPointF(start_x, y), QPointF(end_x, y + height)))

    def on_select(self) -> None:
        self.set_pen_style_solid()
        color = QColor(get_tinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        color.setAlpha(self.alpha_)
        self.setBrush(color)

    def on_deselect(self) -> None:
        self.set_pen_style_no_pen()
        color = QColor(
            get_untinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION)
        )
        color.setAlpha(self.alpha_)
        self.setBrush(color)


class RangeLabel(CursorMixIn, QGraphicsTextItem):
    LEFT_PADDING = 5
    RIGHT_PADDING = 4

    def __init__(
        self,
        start_x: float,
        end_x: float,
        y: float,
        height: float,
        text: str,
        alignment: str = "left",
    ):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.setup_font()
        self._raw_text = text
        self._max_width = max(
            end_x - start_x - self.LEFT_PADDING - self.RIGHT_PADDING, 0
        )
        self._reflow()
        self.set_position(start_x, end_x, y, height, alignment)

    def setup_font(self) -> None:
        font = QFont("Arial", 8)
        self.setFont(font)
        self.setDefaultTextColor(QColor("black"))

    def set_position(
        self,
        start_x: float,
        end_x: float,
        y: float,
        height: float,
        alignment: str = "left",
    ) -> None:
        self._max_width = max(
            end_x - start_x - self.LEFT_PADDING - self.RIGHT_PADDING, 0
        )
        self._reflow()
        text_width = self.boundingRect().width()
        if alignment == "center":
            x = (start_x + end_x - text_width) / 2
        elif alignment == "right":
            x = end_x - text_width - self.RIGHT_PADDING
        else:
            x = start_x + self.LEFT_PADDING
        self.setPos(
            x,
            y + (height - self.boundingRect().height()) / 2,
        )
        self.setZValue(1)

    def set_text(self, value: str) -> None:
        if value == self._raw_text:
            return
        self._raw_text = value
        self._reflow()

    def _reflow(self) -> None:
        elided = elide_text(self._raw_text, self.font(), self._max_width)
        if elided != self.toPlainText():
            self.setPlainText(elided)


class RangeCommentsIcon(CursorMixIn, QGraphicsTextItem):
    ICON = "💬"
    TOP_MARGIN = 1
    RIGHT_MARGIN = 15
    DEFAULT_PIXEL_SIZE = 8
    MIN_PIXEL_SIZE = 4
    VERTICAL_MARGIN = 4

    def __init__(self, end_x: float, y: float, height: float):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        # QTextDocument adds a 4 px margin on every side by default; without
        # this it's the dominant contribution to the icon's bounding rect.
        self.document().setDocumentMargin(0)
        self.setDefaultTextColor(QColor("black"))
        self.setPlainText(self.ICON)
        self.set_position(end_x, y, height)

    def _font_for_height(self, row_height: float) -> QFont:
        target = max(
            self.MIN_PIXEL_SIZE,
            min(self.DEFAULT_PIXEL_SIZE, int(row_height) - self.VERTICAL_MARGIN),
        )
        font = QFont("Arial")
        font.setPixelSize(target)
        return font

    def set_position(self, end_x: float, y: float, height: float) -> None:
        # Scale the font down with the row; the visibility check on the
        # element side hides the icon entirely if it still doesn't fit.
        self.setFont(self._font_for_height(height))
        x = end_x - self.RIGHT_MARGIN
        self.setPos(x, y + self.TOP_MARGIN)
        self.setZValue(2)

    def fits_in_height(self, row_height: float) -> bool:
        return self.boundingRect().height() + self.TOP_MARGIN <= row_height
