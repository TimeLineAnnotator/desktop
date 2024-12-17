import sys

from tilia.exceptions import UserCancelledDialog
from tilia.requests import get, Get, Post
from tilia.ui.timelines.base.timeline import TimelineUI


def _get_args_for_timeline_element_color_set(_):
    success, color = get(Get.FROM_USER_COLOR)
    if not success or not color.isValid():
        raise UserCancelledDialog
    return (color,), {}


def _get_args_for_timeline_name_set(timeline_uis):
    timeline_ui = timeline_uis[0]
    accepted, name = get(
        Get.FROM_USER_STRING,
        "Change timeline name",
        "Choose new name",
        text=get(Get.TIMELINE, timeline_ui.id).name,
    )
    if not accepted:
        raise UserCancelledDialog
    return (name,), {}


def _get_args_for_timeline_height_set(timeline_uis):
    timeline_ui = timeline_uis[0]
    accepted, height = get(
        Get.FROM_USER_INT,
        "Change timeline height",
        "Insert new timeline height",
        value=timeline_ui.get_data("height"),
        min=10,
    )
    if not accepted:
        raise UserCancelledDialog
    return (height,), {}


def _get_args_for_timeline_ordinal_increase_from_context_menu(timelines):
    return _get_args_for_timeline_ordinal_permute_from_context_menu(timelines, 1)


def _get_args_for_timeline_ordinal_decrease_from_context_menu(timelines):
    return _get_args_for_timeline_ordinal_permute_from_context_menu(timelines, -1)


def _get_args_for_timeline_ordinal_permute_from_context_menu(*_):
    tlui1, tlui2 = get(Get.CONTEXT_MENU_TIMELINE_UIS_TO_PERMUTE)
    return (
        {tlui1.id: tlui2.get_data("ordinal"), tlui2.id: tlui1.get_data("ordinal")},
    ), {}


def _get_args_for_timeline_is_visible_set_from_manage_timelines(_):
    is_visible = not (
        get(Get.WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_CURRENT).get_data("is_visible")
    )
    return (is_visible,), {}


def _get_args_for_timeline_ordinal_increase_from_manage_timelines(timelines):
    return _get_args_for_timeline_ordinal_permute_from_manage_timelines(timelines, 1)


def _get_args_for_timeline_ordinal_decrease_from_manage_timelines(timelines):
    return _get_args_for_timeline_ordinal_permute_from_manage_timelines(timelines, -1)


def _get_args_for_timeline_ordinal_permute_from_manage_timelines(*_):
    tlui1, tlui2 = get(Get.WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_TO_PERMUTE)
    return (
        {tlui1.id: tlui2.get_data("ordinal"), tlui2.id: tlui1.get_data("ordinal")},
    ), {}


def _confirm_delete_timeline():
    return get(
        Get.FROM_USER_YES_OR_NO,
        "Delete timeline",
        "Are you sure you want to delete the selected timeline? This can be undone later.",
    )


def _get_args_for_timeline_delete_from_manage_timelines(_):
    confirmed = _confirm_delete_timeline()
    return (confirmed,), {}


def _get_args_for_timeline_delete_from_context_menu(_):
    confirmed = _confirm_delete_timeline()
    return (confirmed,), {}


def _get_args_for_timeline_clear_from_manage_timelines(_):
    confirmed = get(
        Get.FROM_USER_YES_OR_NO,
        "Clear timeline",
        "Are you sure you want to clear the selected timeline? This can be undone later.",
    )
    return (confirmed,), {}


def _get_args_for_timelines_clear(_):
    confirmed = get(
        Get.FROM_USER_YES_OR_NO,
        "Clear timelines",
        "Are you sure you want to clear ALL timelines? This can be undone later.",
    )
    return (confirmed,), {}


def _get_args_for_beat_set_measure_number(_):
    accepted, number = get(
        Get.FROM_USER_INT,
        "Change measure number",
        "Insert measure number",
    )
    if not accepted:
        raise UserCancelledDialog
    return (number,), {}


def _get_args_for_beat_set_amount_in_measure(_):
    accepted, number = get(
        Get.FROM_USER_INT,
        "Change beats in measure",
        "Insert amount of beats in measure",
        min=1,
    )
    if not accepted:
        raise UserCancelledDialog
    return (number,), {}


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
