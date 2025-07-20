import sys

from tilia.exceptions import UserCancelledDialog
from tilia.requests import get, Get, Post
from tilia.ui.timelines.base.timeline import TimelineUI


def _get_args_for_timeline_element_color_set(_):
    success, color = get(Get.FROM_USER_COLOR)
    if not success or not color.isValid():
        raise UserCancelledDialog
    return (color,), {}


def _get_args_for_timelines_clear(_):
    confirmed = get(
        Get.FROM_USER_YES_OR_NO,
        "Clear timelines",
        "Are you sure you want to clear ALL timelines? This can be undone later.",
    )
    return (confirmed,), {}


def _get_args_for_hierarchy_add_pre_start(_):
    accept, number = get(Get.FROM_USER_FLOAT, "Add pre-start", "Pre-start length")
    if not accept:
        raise UserCancelledDialog
    return (number,), {}


def _get_args_for_hierarchy_add_post_end(_):
    accept, number = get(Get.FROM_USER_FLOAT, "Add post-end", "Post-end length")
    if not accept:
        raise UserCancelledDialog
    return (number,), {}


def get_args_for_request(request: Post, timeline_uis: list[TimelineUI], *_, **__):
    try:
        return getattr(sys.modules[__name__], "_get_args_for_" + request.name.lower())(
            timeline_uis
        )
    except AttributeError:
        return tuple(), {}
