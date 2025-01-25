import tilia.errors


def _display_copy_error(reason: str):
    tilia.errors.display(tilia.errors.COMPONENTS_COPY_ERROR, f"Copy failed:\n{reason}")


def _validate_copy_cardinality(elements):
    if len(elements) > 1:
        return False, "Cannot copy more than one hierarchy at once."
    return True, ""


def _validate_paste_complete_cardinality(components):
    if len(components) > 1:
        return False, "Cannot paste more than one Hierarchy at once."
    return True, ""


def _validate_paste_complete_level(target, data):
    if target.get_data("level") != data["support_by_component_value"]["level"]:
        return False, "Cannot paste complete into different level"

    return True, ""


def _display_paste_complete_error(reason: str):
    tilia.errors.display(
        tilia.errors.COMPONENTS_PASTE_ERROR, f"Paste complete failed:\n{reason}"
    )
