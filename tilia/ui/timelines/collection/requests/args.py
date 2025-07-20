import sys

from tilia.requests import Post
from tilia.ui.timelines.base.timeline import TimelineUI

FINALLY YOU CAN DELETE THIS MODULE!!!!

def get_args_for_request(request: Post, timeline_uis: list[TimelineUI], *_, **__):
    try:
        return getattr(sys.modules[__name__], "_get_args_for_" + request.name.lower())(
            timeline_uis
        )
    except AttributeError:
        return tuple(), {}
