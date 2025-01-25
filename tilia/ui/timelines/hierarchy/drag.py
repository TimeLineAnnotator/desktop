import functools
import math

from tilia.requests import get, Get, post, Post
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.drag import DragManager
from tilia.ui.timelines.hierarchy.handles import (
    HierarchyBodyHandle,
    HierarchyFrameHandle,
)
from tilia.ui.timelines.hierarchy.extremity import Extremity

MIN_DRAG_GAP = 4
DRAG_PROXIMITY_LIMIT = 4


def start_drag(
    hierarchy_ui, item: HierarchyBodyHandle | HierarchyFrameHandle.VLine
) -> None:
    if isinstance(item, HierarchyFrameHandle.VLine):
        item = item.parentItem()
    extremity = hierarchy_ui.handle_to_extremity(item)
    hierarchy_ui.drag_extremity = extremity

    min_x, max_x = get_drag_limits(hierarchy_ui, extremity)
    hierarchy_ui.drag_manager = DragManager(
        get_min_x=lambda: min_x,
        get_max_x=lambda: max_x,
        before_each=functools.partial(before_each_drag, hierarchy_ui),
        after_each=get_after_each_drag_func(hierarchy_ui, extremity),
        on_release=functools.partial(on_drag_end, hierarchy_ui),
    )


def get_after_each_drag_func(hierarchy_ui, extremity):
    if extremity in [Extremity.START, Extremity.END]:
        return functools.partial(after_each_body_handle_drag, hierarchy_ui, extremity)
    elif extremity in [Extremity.PRE_START, Extremity.POST_END]:
        extremity_x = extremity.value + "_x"
        uis_that_share_handle = hierarchy_ui.timeline_ui.get_elements_by_attr(
            extremity_x, getattr(hierarchy_ui, extremity_x)
        )
        return functools.partial(
            after_each_frame_handle_drag, extremity, uis_that_share_handle
        )
    else:
        raise ValueError("Unrecognized extremity")


def get_drag_limits(hierarchy_ui, extremity):
    if extremity in [Extremity.START, Extremity.END]:
        return get_body_handle_drag_limits(hierarchy_ui, extremity)
    elif extremity in [Extremity.PRE_START, Extremity.POST_END]:
        return get_frame_handles_drag_limits(hierarchy_ui, extremity)
    else:
        raise ValueError("Unrecognized extremity")


def get_body_handle_drag_limits(
    hierarchy_ui,
    extremity: Extremity,
) -> tuple[int, int]:
    handle_x = hierarchy_ui.extremity_to_x(
        extremity, hierarchy_ui.start_x, hierarchy_ui.end_x
    )
    prev_handle_x = hierarchy_ui.timeline_ui.get_previous_handle_x_by_x(handle_x)
    next_handle_x = hierarchy_ui.timeline_ui.get_next_handle_x_by_x(handle_x)

    min_x = (
        prev_handle_x + DRAG_PROXIMITY_LIMIT
        if prev_handle_x
        else get(Get.LEFT_MARGIN_X)
    )
    max_x = (
        next_handle_x - DRAG_PROXIMITY_LIMIT
        if next_handle_x
        else get(Get.RIGHT_MARGIN_X)
    )

    return min_x, max_x


def get_frame_handles_drag_limits(hierarchy_ui, extremity):
    if extremity == Extremity.PRE_START:
        return get(Get.LEFT_MARGIN_X), hierarchy_ui.start_x
    elif extremity == Extremity.POST_END:
        return hierarchy_ui.end_x, get(Get.RIGHT_MARGIN_X)


def before_each_drag(hierarchy_ui):
    if not hierarchy_ui.dragged:
        post(Post.ELEMENT_DRAG_START)
        hierarchy_ui.dragged = True
        hierarchy_ui.update_frame_handles_visibility()


def after_each_body_handle_drag(hierarchy_ui, extremity, x: int) -> None:
    hierarchy_ui.set_data(extremity.value, time_x_converter.get_time_by_x(x))


def after_each_frame_handle_drag(extremity, uis, x: int):
    body_extremity = {
        Extremity.PRE_START: Extremity.START,
        Extremity.POST_END: Extremity.END,
    }[extremity]
    if math.isclose(
        time := time_x_converter.get_time_by_x(x),
        body_extremity_time := uis[0].get_data(body_extremity.value),
    ):
        time = body_extremity_time
    for ui in uis:
        ui.set_data(extremity.value, time)


def on_drag_end(hierarchy_ui):
    if hierarchy_ui.dragged:
        drag_x = hierarchy_ui.get_data(hierarchy_ui.drag_extremity.value)
        post(
            Post.APP_RECORD_STATE,
            f"hierarchy {hierarchy_ui.drag_extremity} drag",
            no_repeat=True,
            repeat_identifier=f"{hierarchy_ui.timeline_ui}_drag_to_{drag_x}",
        )
        post(Post.ELEMENT_DRAG_END)
        hierarchy_ui.dragged = False
        if not hierarchy_ui.is_selected():
            hierarchy_ui.pre_start_handle.setVisible(False)
            hierarchy_ui.post_end_handle.setVisible(False)
        hierarchy_ui.drag_extremity = None
