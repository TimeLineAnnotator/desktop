from tilia.requests import post, Post


def _display_copy_error(reason: str):
    post(
        Post.DISPLAY_ERROR,
        "Paste failed",
        "Copy failed: " + reason,
    )


def _validate_copy_cardinality(elements):
    if len(elements) > 1:
        return False, "Can't copy more than one hierarchy at once."
    return True, ""


def _validate_paste_complete_cardinality(components):
    if len(components) > 1:
        post(
            Post.DISPLAY_ERROR,
            "Paste failed",
            "Paste complete failed:",
        )
        return False, "can't paste more than one Hierarchy at once."
    return True, ""


def _validate_paste_complete_level(target, data):
    if target.get_data("level") != data["support_by_component_value"]["level"]:
        return False, "can't paste complete into different level"

    return True, ""


def _display_paste_complete_error(reason: str):
    post(
        Post.DISPLAY_ERROR,
        "Paste failed",
        "Paste complete failed: " + reason,
    )
