import weakref
from enum import Enum, auto
from typing import Callable, Any

from tilia.settings import settings
from tilia.exceptions import NoReplyToRequest, NoCallbackAttached


class Get(Enum):
    APP_STATE = auto()
    TIMELINE_ELEMENTS_SELECTED = auto()
    CLIPBOARD_CONTENTS = auto()
    CONTEXT_MENU_TIMELINE_UIS_TO_PERMUTE = auto()
    CONTEXT_MENU_TIMELINE_UI = auto()
    FIRST_TIMELINE_UI_IN_SELECT_ORDER = auto()
    FROM_USER_BEAT_PATTERN = auto()
    FROM_USER_COLOR = auto()
    FROM_USER_DIR = auto()
    FROM_USER_FILE_PATH = auto()
    FROM_USER_FLOAT = auto()
    FROM_USER_HARMONY_PARAMS = auto()
    FROM_USER_INT = auto()
    FROM_USER_MEDIA_PATH = auto()
    FROM_USER_PDF_PATH = auto()
    FROM_USER_RETRY_PDF_PATH = auto()
    FROM_USER_MODE_PARAMS = auto()
    FROM_USER_SAVE_PATH_OGG = auto()
    FROM_USER_SAVE_PATH_TILIA = auto()
    FROM_USER_SHOULD_SAVE_CHANGES = auto()
    FROM_USER_STRING = auto()
    FROM_USER_TILIA_FILE_PATH = auto()
    FROM_USER_YES_OR_NO = auto()
    ID = auto()
    LEFT_MARGIN_X = auto()
    LOOP_TIME = auto()
    MEDIA_CURRENT_TIME = auto()
    MEDIA_DURATION = auto()
    MEDIA_METADATA = auto()
    MEDIA_METADATA_REQUIRED_FIELDS = auto()
    MEDIA_PATH = auto()
    MEDIA_TITLE = auto()
    MEDIA_TYPE = auto()
    METRIC_POSITION = auto()
    PLAYBACK_AREA_WIDTH = auto()
    PLAYER_CLASS = auto()
    RIGHT_MARGIN_X = auto()
    SELECTED_TIME = auto()
    TIMELINE = auto()
    TIMELINES = auto()
    TIMELINES_BY_ATTR = auto()
    TIMELINE_BY_ATTR = auto()
    TIMELINE_COLLECTION = auto()
    TIMELINE_ORDINAL = auto()
    TIMELINE_ORDINAL_FOR_NEW = auto()
    TIMELINE_UI = auto()
    TIMELINE_UIS = auto()
    TIMELINE_UIS_BY_ATTR = auto()
    TIMELINE_UI_BY_ATTR = auto()
    TIMELINE_UI_ELEMENT = auto()
    TIMELINE_WIDTH = auto()
    TIMELINES_FROM_CLI = auto()
    WINDOW_GEOMETRY = auto()
    WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_CURRENT = auto()
    WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_TO_PERMUTE = auto()
    WINDOW_STATE = auto()


_requests_to_callbacks: weakref.WeakKeyDictionary[
    Get, Callable
] = weakref.WeakKeyDictionary()
_servers_to_requests: weakref.WeakKeyDictionary[
    Any, set[Get]
] = weakref.WeakKeyDictionary()


def get(request: Get, *args, **kwargs) -> Any:
    """
    Calls the callback specified by the replier when attaching to the request.
    Raises a NoReplyToRequest() if no callback is attached.
    """

    try:
        return _requests_to_callbacks[request](*args, **kwargs)
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

    _requests_to_callbacks[request] = callback
    if replier not in _servers_to_requests.keys():
        _servers_to_requests[replier] = set()

    _servers_to_requests[replier].add(request)


def server(request: Get) -> tuple[Any | None, Callable | None]:
    for replier, request_set in _servers_to_requests.items():
        if request in request_set:
            return replier, _requests_to_callbacks[request]

    return None, None


def stop_serving(replier: Any, request: Get) -> None:
    """
    Detaches a calback from a request.
    """
    try:
        _requests_to_callbacks.pop(request)
    except KeyError:
        raise NoCallbackAttached()

    _servers_to_requests[replier].remove(request)
    if not _servers_to_requests[replier]:
        _servers_to_requests.pop(replier)


def stop_serving_all(replier: Any) -> None:
    if replier not in _servers_to_requests:
        return

    for request in _servers_to_requests[replier].copy():
        stop_serving(replier, request)


def reset() -> None:
    global _requests_to_callbacks, _servers_to_requests

    _requests_to_callbacks.clear()
    _servers_to_requests.clear()
