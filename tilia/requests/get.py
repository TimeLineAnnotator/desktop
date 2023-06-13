import logging
from enum import Enum, auto
from typing import Callable, Any

from tilia import settings
from tilia.exceptions import NoReplyToRequest, NoCallbackAttached

logger = logging.getLogger(__name__)


class Get(Enum):
    FILE_PATH_FROM_USER = auto()
    TIMELINES_BY_ATTR = auto()
    TIMELINE_BY_ATTR = auto()
    ORDINAL_FOR_NEW_TIMELINE = auto()
    APP_STATE = auto()
    COLOR_FROM_USER = auto()
    BEAT_PATTERN_FROM_USER = auto()
    DIR_FROM_USER = auto()
    TILIA_FILE_PATH_FROM_USER = auto()
    FLOAT_FROM_USER = auto()
    INT_FROM_USER = auto()
    SAVE_PATH_FROM_USER = auto()
    STRING_FROM_USER = auto()
    SHOULD_SAVE_CHANGES_FROM_USER = auto()
    YES_OR_NO_FROM_USER = auto()
    CURRENT_PLAYBACK_TIME = auto()
    FILE_SAVE_PARAMETERS = auto()
    CLIPBOARD = auto()
    ID = auto()
    LEFT_MARGIN_X = auto()
    MEDIA_DURATION = auto()
    MEDIA_METADATA = auto()
    MEDIA_PATH = auto()
    MEDIA_TITLE = auto()
    RIGHT_MARGIN_X = auto()
    TIMELINE = auto()
    TIMELINES = auto()
    TIMELINE_ORDINAL = auto()
    TIMELINE_FRAME_WIDTH = auto()
    TIMELINE_WIDTH = auto()


requests_to_callbacks: dict[Get, Callable] = {}
servers_to_requests: dict[Any, set[Get]] = {}

log_requests = settings.get("dev", "log_requests")


def get(request: Get, *args, **kwargs) -> Any:
    """
    Calls the callback specified by the replier when attaching to the request.
    Raises a NoReplyToRequest() if no callback is attached.
    """
    logging_level = 10

    if log_requests:
        logger.log(logging_level, f"Posting {request} with {args=} and {kwargs=}.")
    try:
        return requests_to_callbacks[request](*args, **kwargs)
    except KeyError:
        raise NoReplyToRequest(f"{request} has no repliers attached.")
    except Exception as exc:
        raise Exception(
            f"Exception when processing {request} with {args=}, {kwargs=}"
        ) from exc


def serve(replier: Any, request: Get, callback: Callable) -> None:
    """
    Attaches a callback to a request.
    """

    requests_to_callbacks[request] = callback
    if replier not in servers_to_requests.keys():
        servers_to_requests[replier] = set()
    else:
        servers_to_requests[replier].add(request)


def stop_serving(replier: Any, request: Get) -> None:
    """
    Detaches a calback from a request.
    """
    try:
        requests_to_callbacks.pop(request)
    except KeyError:
        raise NoCallbackAttached()

    servers_to_requests[replier].remove(request)
    if not servers_to_requests[replier]:
        servers_to_requests.pop(replier)


def stop_serving_all(replier: Any) -> None:
    if replier not in servers_to_requests:
        return

    for request in servers_to_requests[replier].copy():
        stop_serving(replier, request)
