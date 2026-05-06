from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Literal

from PySide6.QtWidgets import QGraphicsItem

import tilia.errors
from tilia.requests import Get, Post, get, listen, post, stop_listening
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.drag import DragManager

if TYPE_CHECKING:
    from tilia.ui.timelines.range.element import RangeUI

MIN_DRAG_GAP = 4

Extremity = Literal["start", "end", "pre_start", "post_end"]
BodyExtremity = Literal["start", "end"]


def _find_joined_partner(
    range_ui: RangeUI, extremity: BodyExtremity
) -> tuple[RangeUI | None, BodyExtremity | None]:
    """
    Returns (partner_ui, partner_extremity) if the dragged edge is shared
    with another range via a join, else (None, None).
    """
    timeline_ui = range_ui.timeline_ui

    if extremity == "end":
        partner_id = range_ui.get_data("joined_right")
        if partner_id is None:
            return None, None
        partner_ui = timeline_ui.id_to_element.get(partner_id)
        return (partner_ui, "start") if partner_ui else (None, None)

    for other in timeline_ui:
        if other.get_data("joined_right") == range_ui.id:
            return other, "end"
    return None, None


def start_drag(range_ui: RangeUI, item: QGraphicsItem) -> None:
    extremity = range_ui.handle_to_extremity(item)
    if extremity is None:
        tilia.errors.display(tilia.errors.RANGE_DRAG_INVALID_HANDLE)
        return
    range_ui.drag_extremity = extremity

    if extremity in ("pre_start", "post_end"):
        _start_frame_drag(range_ui, extremity)
        return

    partner_ui, partner_extremity = _find_joined_partner(range_ui, extremity)

    range_ui.drag_manager = DragManager(
        get_min_x=lambda: _get_min_x(
            range_ui, extremity, partner_ui, partner_extremity
        ),
        get_max_x=lambda: _get_max_x(
            range_ui, extremity, partner_ui, partner_extremity
        ),
        before_each=functools.partial(before_each_drag, range_ui),
        after_each=functools.partial(
            after_each_drag, range_ui, extremity, partner_ui, partner_extremity
        ),
        on_release=functools.partial(on_drag_end, range_ui),
    )


def _start_frame_drag(range_ui: RangeUI, extremity: Extremity) -> None:
    is_pre_start = extremity == "pre_start"

    def get_min_x() -> float:
        return get(Get.LEFT_MARGIN_X) if is_pre_start else range_ui.end_x

    def get_max_x() -> float:
        return range_ui.start_x if is_pre_start else get(Get.RIGHT_MARGIN_X)

    range_ui.drag_manager = DragManager(
        get_min_x=get_min_x,
        get_max_x=get_max_x,
        before_each=functools.partial(before_each_drag, range_ui),
        after_each=functools.partial(_after_each_frame_drag, range_ui, extremity),
        on_release=functools.partial(on_drag_end, range_ui),
    )


def _after_each_frame_drag(range_ui: RangeUI, extremity: Extremity, x: int) -> None:
    range_ui.set_data(extremity, time_x_converter.get_time_by_x(x))


def _get_min_x(
    range_ui: RangeUI,
    extremity: Extremity,
    partner_ui: RangeUI | None,
    partner_extremity: Extremity | None,
) -> float:
    # When joined, the shared edge constraint is the union of both sides'.
    # For min_x: the dragged side's start (when extremity == "end") OR
    # the partner's start (when extremity == "start" and partner is on the left).
    if extremity == "start":
        if partner_ui and partner_extremity == "end":
            return partner_ui.start_x + MIN_DRAG_GAP
        return get(Get.LEFT_MARGIN_X)
    return range_ui.start_x + MIN_DRAG_GAP


def _get_max_x(
    range_ui: RangeUI,
    extremity: Extremity,
    partner_ui: RangeUI | None,
    partner_extremity: Extremity | None,
) -> float:
    if extremity == "end":
        if partner_ui and partner_extremity == "start":
            return partner_ui.end_x - MIN_DRAG_GAP
        return get(Get.RIGHT_MARGIN_X)
    return range_ui.end_x - MIN_DRAG_GAP


def before_each_drag(range_ui: RangeUI) -> None:
    if not range_ui.dragged:
        post(Post.ELEMENT_DRAG_START)
        range_ui.dragged = True


def after_each_drag(
    range_ui: RangeUI,
    extremity: Extremity,
    partner_ui: RangeUI | None,
    partner_extremity: Extremity | None,
    x: int,
) -> None:
    time = time_x_converter.get_time_by_x(x)
    range_ui.set_data(extremity, time)
    if partner_ui:
        partner_ui.set_data(partner_extremity, time)


def on_drag_end(range_ui: RangeUI) -> None:
    if range_ui.dragged:
        post(
            Post.APP_STATE_RECORD,
            f"range {range_ui.drag_extremity} drag",
            no_repeat=True,
        )
        post(Post.ELEMENT_DRAG_END)
        range_ui.dragged = False
        range_ui.drag_extremity = None


def start_body_drag(range_ui: RangeUI) -> None:
    """Drag the range body horizontally, keeping its duration constant.

    The first drag event captures the cursor's offset within the range so the
    range follows the cursor without snapping. When the range is joined, the
    whole chain moves together (preserving the same-row, edge-shared
    invariants). Limits clamp the chain within `[LEFT_MARGIN_X, RIGHT_MARGIN_X]`.
    """
    timeline_ui = range_ui.timeline_ui
    chain_ids = timeline_ui._joined_chain_ids(range_ui.id)
    chain_members = [timeline_ui.id_to_element[cid] for cid in chain_ids]

    original_starts = {m.id: m.get_data("start") for m in chain_members}
    original_ends = {m.id: m.get_data("end") for m in chain_members}
    original_pre_starts = {m.id: m.get_data("pre_start") for m in chain_members}
    original_post_ends = {m.id: m.get_data("post_end") for m in chain_members}

    # Chain extremes include any extensions (pre_start / post_end) so the
    # whiskers can't be dragged past the timeline margin either.
    chain_leftmost_x = min(
        time_x_converter.get_x_by_time(original_pre_starts[m.id]) for m in chain_members
    )
    chain_rightmost_x = max(
        time_x_converter.get_x_by_time(original_post_ends[m.id]) for m in chain_members
    )

    dragged_start_x = range_ui.start_x
    duration_x = range_ui.end_x - dragged_start_x
    # When joined, the dragged range may sit anywhere in the chain. The chain
    # extremes — not the dragged range itself — must stay inside the margins.
    left_buffer = dragged_start_x - chain_leftmost_x
    right_buffer = chain_rightmost_x - range_ui.end_x

    state = {"click_offset_x": None}

    def get_min_x() -> float:
        offset = state["click_offset_x"] or 0
        return get(Get.LEFT_MARGIN_X) + left_buffer + offset

    def get_max_x() -> float:
        offset = state["click_offset_x"] or 0
        return get(Get.RIGHT_MARGIN_X) - duration_x - right_buffer + offset

    def before_each() -> None:
        if not range_ui.dragged:
            post(Post.ELEMENT_DRAG_START)
            range_ui.dragged = True

    def after_each(x: int) -> None:
        if state["click_offset_x"] is None:
            state["click_offset_x"] = x - dragged_start_x
            return
        new_dragged_start_x = x - state["click_offset_x"]
        new_dragged_start = time_x_converter.get_time_by_x(new_dragged_start_x)
        delta = new_dragged_start - original_starts[range_ui.id]
        for m in chain_members:
            new_start = original_starts[m.id] + delta
            new_end = original_ends[m.id] + delta
            new_pre_start = original_pre_starts[m.id] + delta
            new_post_end = original_post_ends[m.id] + delta
            # Set in the order that avoids a transient start >= end state.
            # Setting pre_start before start (and post_end after end) avoids
            # the start.setter from auto-collapsing pre_start back to start
            # (it does so when pre_start > new_start).
            if new_start > m.get_data("start"):
                m.set_data("post_end", new_post_end)
                m.set_data("end", new_end)
                m.set_data("start", new_start)
                m.set_data("pre_start", new_pre_start)
            else:
                m.set_data("pre_start", new_pre_start)
                m.set_data("start", new_start)
                m.set_data("end", new_end)
                m.set_data("post_end", new_post_end)

    def track_y(_x: int, y: int) -> None:
        target_row = _row_at_y(timeline_ui, y)
        if target_row is None:
            return
        current_row_id = chain_members[0].get_data("row_id")
        if target_row.id != current_row_id:
            for m in chain_members:
                m.set_data("row_id", target_row.id)

    listen(range_ui, Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, track_y)

    def on_release() -> None:
        stop_listening(range_ui, Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG)
        on_body_drag_end(range_ui)

    range_ui.drag_manager = DragManager(
        get_min_x=get_min_x,
        get_max_x=get_max_x,
        before_each=before_each,
        after_each=after_each,
        on_release=on_release,
    )


def _row_at_y(timeline_ui, y: float):
    """Snap a y coordinate to a row, clamping at the timeline edges.

    Walks the rows in order with cumulative height so per-row heights
    are honoured.
    """
    if not timeline_ui.rows:
        return None
    if y < 0:
        return timeline_ui.rows[0]
    running_y = 0.0
    for row in timeline_ui.rows:
        running_y += timeline_ui.row_height_for(row)
        if y < running_y:
            return row
    return timeline_ui.rows[-1]


def on_body_drag_end(range_ui: RangeUI) -> None:
    if range_ui.dragged:
        post(Post.APP_STATE_RECORD, "range body drag", no_repeat=True)
        post(Post.ELEMENT_DRAG_END)
        range_ui.dragged = False
