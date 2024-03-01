from tilia.requests import Post, post, Get, get


def has_validator(request: Post):
    return request in request_to_validator


def validate_timeline_element_copy(timeline_uis, *_, **__):
    if len(timeline_uis) == 0:
        # Can't copy: there are no selected elements.
        return False
    elif len(get(Get.TIMELINE_UIS_BY_ATTR, "has_selected_elements", True)) > 1:
        post(
            Post.DISPLAY_ERROR,
            "Copy error",
            "Can't copy components from more than one timeline.",
        )
        return False
    return True


def validate(request, timeline_uis, *args, **kwargs):
    if not has_validator(request):
        return True

    return request_to_validator[request](timeline_uis, *args, **kwargs)


request_to_validator = {Post.TIMELINE_ELEMENT_COPY: validate_timeline_element_copy}
