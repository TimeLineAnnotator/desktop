import sys

import tilia.errors
from tilia.exceptions import UserCancelledDialog
from tilia.requests import get, Get, Post, post
from tilia.ui import dialogs
import tilia.ui.dialogs.basic
from tilia.ui.dialogs.harmony_params import SelectHarmonyParams
from tilia.ui.dialogs.mode_params import SelectModeParams
from tilia.ui.timelines.base.timeline import TimelineUI


def _get_args_for_timeline_element_color_set(_):
    color = dialogs.basic.ask_for_color("#000")
    if not color.isValid():
        raise UserCancelledDialog
    return (color,), {}


def _get_args_for_timeline_name_set(timeline_uis):
    timeline_ui = timeline_uis[0]
    name, accept = dialogs.basic.ask_for_string(
        "Change timeline name",
        "Choose new name",
        get(Get.TIMELINE, timeline_ui.id).name,
    )
    if not accept:
        raise UserCancelledDialog
    return (name,), {}


def _get_media_duration_valid_for_add_timeline():
    if get(Get.MEDIA_DURATION) == 0:
        return False
    return True


def _get_timeline_name():
    name, confirmed = get(
        Get.FROM_USER_STRING,
        title="New timeline",
        prompt="Choose name for new timeline",
    )

    return (confirmed, name), {}


def _get_args_for_timeline_add_hierarchy_timeline(_):
    if not _get_media_duration_valid_for_add_timeline():
        post(Post.DISPLAY_ERROR, *tilia.errors.CREATE_TIMELINE_WITHOUT_MEDIA)
        return (False, ""), {}
    return _get_timeline_name()


def _get_args_for_timeline_add_marker_timeline(_):
    if not _get_media_duration_valid_for_add_timeline():
        post(Post.DISPLAY_ERROR, *tilia.errors.CREATE_TIMELINE_WITHOUT_MEDIA)
        return (False, ""), {}
    return _get_timeline_name()


def _get_args_for_timeline_add_beat_timeline(_):
    if not _get_media_duration_valid_for_add_timeline():
        post(Post.DISPLAY_ERROR, *tilia.errors.CREATE_TIMELINE_WITHOUT_MEDIA)
        return (False, ""), {}
    (confirmed, name), _ = _get_timeline_name()
    if not confirmed:
        return (False, "", []), {}

    confirmed, beat_pattern = get(Get.FROM_USER_BEAT_PATTERN)

    return (confirmed, name, beat_pattern), {}


def _get_args_for_timeline_add_harmony_timeline(_):
    if not _get_media_duration_valid_for_add_timeline():
        post(Post.DISPLAY_ERROR, *tilia.errors.CREATE_TIMELINE_WITHOUT_MEDIA)
        return (False, ""), {}
    return _get_timeline_name()


def _get_args_for_timeline_height_set(timeline_uis):
    timeline_ui = timeline_uis[0]
    height, accept = dialogs.basic.ask_for_int(
        "Change timeline height",
        "Insert new timeline height",
        initial=timeline_ui.get_data("height"),
    )
    if not accept:
        raise UserCancelledDialog
    return (height,), {}


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


def _get_args_for_timeline_delete_from_manage_timelines(_):
    confirmed = get(
        Get.FROM_USER_YES_OR_NO,
        "Delete timeline",
        "Are you sure you want to delete the selected timeline? This can be undone later.",
    )
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
    number, accept = dialogs.basic.ask_for_int(
        "Change measure number",
        "Insert measure number",
    )
    if not accept:
        raise UserCancelledDialog
    return (number,), {}


def _get_args_for_beat_set_amount_in_measure(_):
    number, accept = dialogs.basic.ask_for_int(
        "Change beats in measure",
        "Insert amount of beats in measure",
    )
    if not accept:
        raise UserCancelledDialog
    return (number,), {}


def _get_args_for_hierarchy_add_pre_start(_):
    number, accept = dialogs.basic.ask_for_float("Add pre-start", "Pre-start length")
    if not accept:
        raise UserCancelledDialog
    return (number,), {}


def _get_args_for_hierarchy_add_post_end(_):
    number, accept = dialogs.basic.ask_for_float("Add post-end", "Post-end length")
    if not accept:
        raise UserCancelledDialog
    return (number,), {}


def _get_args_for_harmony_add(timeline_uis):
    current_key = timeline_uis[0].get_key_by_time(get(Get.MEDIA_CURRENT_TIME))
    dialog = SelectHarmonyParams(current_key)
    accept = dialog.exec()
    return (accept,), dialog.result()


def _get_args_for_mode_add(_):
    dialog = SelectModeParams()
    accept = dialog.exec()
    return (accept,), dialog.result()


def get_args_for_request(request: Post, timeline_uis: list[TimelineUI], *_, **__):
    try:
        return getattr(sys.modules[__name__], "_get_args_for_" + request.name.lower())(
            timeline_uis
        )
    except AttributeError:
        return tuple(), {}
