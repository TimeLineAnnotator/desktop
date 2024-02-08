import sys
from typing import Any

from tilia.exceptions import TiliaException
from tilia.requests import Post, post

NEEDS_POST_PROCESSING = [
    Post.TIMELINE_ELEMENT_COPY,
    Post.TIMELINE_DELETE_DONE,
]


class PostProcessingError(TiliaException):
    pass


def _post_process_timeline_element_copy(results):
    if not any([bool(r) for r in results]):
        return

    components = []
    for rsl in results:
        components += [data["components"] for data in rsl]
    post(
        Post.TIMELINE_ELEMENT_COPY_DONE,
        {"components": components, "timeline_kind": results[0][0]["timeline_kind"]},
    )


def post_process_request(request: Post, result: list[Any]):
    if request not in NEEDS_POST_PROCESSING:
        return

    func_name = "_post_process_" + request.name.lower()

    if not hasattr(sys.modules[__name__], func_name):
        raise PostProcessingError(
            f"Request {request} needs post-processing,"
            f" but no post-processor func was found."
        )

    return getattr(sys.modules[__name__], func_name)(result)
