import os
import weakref
from enum import Enum, auto
from typing import Any, Callable

from tilia.log import logger


class Post(Enum):
    UI_EXIT = auto()
    APP_CLEAR = auto()
    APP_FILE_LOADED = auto()
    APP_MEDIA_LOAD = auto()
    APP_SETUP_FILE = auto()
    APP_STATE_RECORD = auto()
    APP_STATE_RECOVER = auto()
    APP_STATE_RESTORE = auto()
    APP_STATE_UNDO_OR_REDO_DONE = auto()
    BEAT_TIMELINE_COMPONENTS_DESERIALIZED = auto()
    BEAT_TIMELINE_MEASURE_NUMBER_CHANGE_DONE = auto()
    DISPLAY_ERROR = auto()
    ELEMENT_DRAG_END = auto()
    ELEMENT_DRAG_START = auto()
    FILE_MEDIA_DURATION_CHANGED = auto()
    HARMONY_TIMELINE_COMPONENTS_DESERIALIZED = auto()
    HIERARCHY_DESELECTED = auto()
    HIERARCHY_MERGE_SPLIT_DONE = auto()
    HIERARCHY_SELECTED = auto()
    IMPORT_CSV = auto()
    IMPORT_MUSICXML = auto()
    INSPECTABLE_ELEMENT_DESELECTED = auto()
    INSPECTABLE_ELEMENT_SELECTED = auto()
    INSPECTOR_FIELD_EDITED = auto()
    LOOP_IGNORE_COMPONENT = auto()
    MEDIA_METADATA_FIELD_ADD = auto()
    MEDIA_METADATA_FIELD_SET = auto()
    METADATA_UPDATE_FIELDS = auto()
    PLAYBACK_AREA_SET_WIDTH = auto()
    PLAYER_CANCEL_LOOP = auto()
    PLAYER_CURRENT_LOOP_CHANGED = auto()
    PLAYER_CURRENT_TIME_CHANGED = auto()
    PLAYER_DURATION_AVAILABLE = auto()
    PLAYER_EXPORT_AUDIO = auto()
    PLAYER_PLAYBACK_RATE_TRY = auto()
    PLAYER_SEEK = auto()
    PLAYER_SEEK_IF_NOT_PLAYING = auto()
    PLAYER_STOPPED = auto()
    PLAYER_TOGGLE_LOOP = auto()
    PLAYER_TOGGLE_PLAY_PAUSE = auto()
    PLAYER_UI_UPDATE = auto()
    PLAYER_UPDATE_CONTROLS = auto()
    PLAYER_URL_CHANGED = auto()
    PLAYER_VOLUME_CHANGE = auto()
    PLAYER_VOLUME_MUTE = auto()
    REQUEST_CLEAR_UI = auto()
    REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH = auto()
    REQUEST_SAVE_TO_PATH = auto()
    SCORE_TIMELINE_CLEAR_DONE = auto()
    SCORE_TIMELINE_COMPONENTS_DESERIALIZED = auto()
    SELECTION_BOX_DESELECT_ITEM = auto()
    SELECTION_BOX_SELECT_ITEM = auto()
    SETTINGS_UPDATED = auto()
    SLIDER_DRAG = auto()
    SLIDER_DRAG_END = auto()
    SLIDER_DRAG_START = auto()
    TIMELINES_AUTO_SCROLL_UPDATE = auto()
    TIMELINES_CROP_DONE = auto()
    TIMELINE_COMPONENT_CREATED = auto()
    TIMELINE_COMPONENT_DELETED = auto()
    TIMELINE_COMPONENT_DESELECTED = auto()
    TIMELINE_COMPONENT_SELECTED = auto()
    TIMELINE_COMPONENT_SET_DATA_DONE = auto()
    TIMELINE_COMPONENT_SET_DATA_FAILED = auto()
    TIMELINE_CREATE_DONE = auto()
    TIMELINE_DELETE_FROM_CLI = auto()
    TIMELINE_DELETE_DONE = auto()
    TIMELINE_ELEMENT_COPY_DONE = auto()
    TIMELINE_KEY_PRESS_DOWN = auto()
    TIMELINE_KEY_PRESS_LEFT = auto()
    TIMELINE_KEY_PRESS_RIGHT = auto()
    TIMELINE_KEY_PRESS_UP = auto()
    TIMELINE_KIND_INSTANCED = auto()
    TIMELINE_KIND_NOT_INSTANCED = auto()
    TIMELINE_SET_DATA_DONE = auto()
    TIMELINE_VIEW_DOUBLE_LEFT_CLICK = auto()
    TIMELINE_VIEW_LEFT_BUTTON_DRAG = auto()
    TIMELINE_VIEW_LEFT_BUTTON_RELEASE = auto()
    TIMELINE_VIEW_LEFT_CLICK = auto()
    TIMELINE_VIEW_RIGHT_CLICK = auto()
    TIMELINE_WIDTH_SET_DONE = auto()
    UNDO_MANAGER_SET_IS_RECORDING = auto()
    WINDOW_OPEN = auto()
    WINDOW_OPEN_DONE = auto()
    WINDOW_CLOSE = auto()
    WINDOW_CLOSE_DONE = auto()
    WINDOW_UPDATE_REQUEST = auto()
    WINDOW_UPDATE_STATE = auto()


_posts_to_listeners: weakref.WeakKeyDictionary[Post, Any] = weakref.WeakKeyDictionary(
    {post: {} for post in Post}
)
_listeners_to_posts: weakref.WeakKeyDictionary[
    Any, list[Post]
] = weakref.WeakKeyDictionary()


EXCLUDED_POSTS = [
    Post[post] for post in os.environ.get("EXCLUDE_FROM_LOG", "").split(";")
]
LOG_REQUESTS = os.environ.get("LOG_REQUESTS", 0)


def _log_post(post, *args, **kwargs):
    try:
        listeners = list(_posts_to_listeners.get(post, ""))
        log_message = f"{post.name:<40} {str((args, kwargs)):<100} {listeners}"
    except RuntimeError as e:
        # Protects from the Internal C++ object already deleted,
        # which happens when C++ listeners leak.
        logger.warning(f"RuntimeError when creating log message for {post}: {e}")
        return

    if post is Post.DISPLAY_ERROR:
        logger.warning(log_message)
        return
    if post is Post.SETTINGS_UPDATED and "dev" in args[0][0]:
        logger.on_settings_updated()
    else:
        logger.info(log_message)


def post(post: Post, *args, **kwargs) -> None:
    if LOG_REQUESTS and post not in EXCLUDED_POSTS:
        try:
            _log_post(post, args, kwargs)
        except Exception as e:
            # Errors in logging should never cause crashes,
            # so catch them and print a warning.
            logger.warning(f"Exception when creating log message for {post}: {e}")
    # Returning a result is an experimental feature.
    # This can be very useful to check if the request was successful.
    # Should be used only when a single listener is expected.
    # If there are multiple listeners, the result of the last listener is returned.
    result = None
    for callback in _posts_to_listeners[post].copy().values():
        result = callback(*args, **kwargs)
    return result


def listen(listener: Any, post: Post, callback: Callable) -> None:
    _posts_to_listeners[post][listener] = callback

    if listener not in _listeners_to_posts.keys():
        _listeners_to_posts[listener] = [post]
    else:
        _listeners_to_posts[listener].append(post)


def listen_to_multiple(
    listener: Any, posts_and_callbacks: list[tuple[Post, Callable]]
) -> None:
    for post, callback in posts_and_callbacks:
        listen(listener, post, callback)


def stop_listening(listener: Any, post: Post) -> None:
    try:
        _posts_to_listeners[post].pop(listener)
    except KeyError:
        return

    _listeners_to_posts[listener].remove(post)

    if not _listeners_to_posts[listener]:
        _listeners_to_posts.pop(listener)


def stop_listening_to_all(listener: Any) -> None:
    if listener not in _listeners_to_posts.keys():
        return

    for post in _listeners_to_posts[listener].copy():
        stop_listening(listener, post)


def reset() -> None:
    global _posts_to_listeners
    _posts_to_listeners = weakref.WeakKeyDictionary({post: {} for post in Post})
    _listeners_to_posts.clear()
